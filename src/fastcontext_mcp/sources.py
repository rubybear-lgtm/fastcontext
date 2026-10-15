"""Repository-scoped search tools and source-backed citation validation."""

import asyncio
import hashlib
import json
import re
import shutil
from pathlib import Path


class ExplorationError(ValueError):
    """Exploration finished without a usable, source-backed result."""


def find_ripgrep():
    command = shutil.which("rg")
    if not command:
        raise ExplorationError("ripgrep is unavailable on PATH; install rg or correct the MCP environment")
    return command


class SourceTools:
    def __init__(self, root, message_factory, *, rg=None):
        self.root = Path(root).resolve()
        self.message_factory = message_factory
        self.rg = rg or find_ripgrep()
        self.evidence = {}

    def path(self, value=None):
        path = Path(value) if value else self.root
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Path is outside the repository. Use repository-relative paths under {self.root}")
        return path

    def schema_list(self):
        definitions = [
            ("Read", "Read existing source with numbered lines (default 200, max 2000). Use offset/limit for more. Paths are relative to the repository root or absolute within it.",
             {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, ["path"]),
            ("Glob", "Find repository files using a glob; results are actual absolute paths. Use these paths in Read.",
             {"pattern": {"type": "string"}, "directory": {"type": "string"}}, ["pattern"]),
            ("Grep", "Search source with ripgrep. Use output_mode=content to inspect matching lines.",
             {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"},
              "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"]},
              "-i": {"type": "boolean"}, "-C": {"type": "integer"}, "head_limit": {"type": "integer"}}, ["pattern"]),
        ]
        return [{"type": "function", "function": {"name": name, "description": description,
                 "parameters": {"type": "object", "properties": props, "required": required}}}
                for name, description, props, required in definitions]

    async def _rg(self, *args):
        process = await asyncio.create_subprocess_exec(
            self.rg, *args, cwd=self.root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        # Drain stderr concurrently. Bound search output, terminate rather than
        # retain a giant repository scan in memory, and always reap the child.
        stderr_task = asyncio.create_task(process.stderr.read(8192))
        try:
            async with asyncio.timeout(8):
                data = await process.stdout.read(256 * 1024 + 1)
                if len(data) > 256 * 1024:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    data = data[:256 * 1024].rsplit(b"\n", 1)[0]
                else:
                    # read(n) may return early; keep draining to the same limit.
                    while chunk := await process.stdout.read(256 * 1024 + 1 - len(data)):
                        data += chunk
                        if len(data) > 256 * 1024:
                            try:
                                process.terminate()
                            except ProcessLookupError:
                                pass
                            data = data[:256 * 1024].rsplit(b"\n", 1)[0]
                            break
                status = await process.wait()
                error = await stderr_task
                if status not in (0, 1, -15):
                    raise ValueError(error.decode(errors="replace").strip() or f"rg exited {status}")
                return data.decode(errors="replace")
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            stderr_task.cancel()
            await asyncio.gather(stderr_task, return_exceptions=True)

    def _source(self, path):
        path = self.path(path)
        if not path.is_file():
            raise ValueError(f"Source file does not exist: {path}. Use Glob to discover actual files.")
        with path.open("rb") as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024 or b"\x00" in data:
            raise ValueError("Source is binary or exceeds the 2 MiB read limit; narrow the search")
        return path, data.decode(errors="replace").splitlines(), hashlib.sha256(data).hexdigest()

    def _record(self, path, digest, numbers):
        previous = self.evidence.get(path)
        if not previous or previous[0] != digest:
            self.evidence[path] = (digest, set())
        self.evidence[path][1].update(numbers)

    async def invoke(self, name, args):
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be a JSON object")
        if name == "Read":
            if not isinstance(args.get("path"), str) or not args["path"]:
                raise ValueError("Read requires path")
            path, lines, digest = self._source(args["path"])
            offset = max(1, int(args.get("offset", 1)))
            limit = min(2000, max(1, int(args.get("limit", 200))))
            shown = lines[offset - 1:offset - 1 + limit]
            if not shown:
                raise ValueError(f"No source lines at offset {offset} in {path}")
            end = offset + len(shown) - 1
            previous = self.evidence.get(path)
            if previous and previous[0] == digest and all(n in previous[1] for n in range(offset, end + 1)):
                return f"Already read {path}:{offset}-{end}; source is unchanged. Use the previously shown content, or inspect a different file."
            self._record(path, digest, range(offset, end + 1))
            return f"{path}:{offset}-{end}\n" + "\n".join(f"{i}|{line[:1000]}" for i, line in enumerate(shown, offset))
        if name == "Glob":
            directory = self.path(args.get("directory"))
            pattern = args.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("Glob requires pattern")
            if Path(pattern).is_absolute():
                pattern = str(self.path(pattern).relative_to(directory))
            output = await self._rg("--files", "-g", pattern, "--", str(directory))
            paths = []
            for line in output.splitlines():
                path = self.path(line)
                if path.is_file():
                    paths.append(str(path))
            return "\n".join(paths[:100]) or "No files found"
        if name == "Grep":
            pattern = args.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("Grep requires pattern")
            path = self.path(args.get("path"))
            command = ["--json", "--max-count", "30", "-C", str(min(10, max(0, int(args.get("-C", 2)))))]
            if args.get("glob"):
                command.extend(["-g", args["glob"]])
            if args.get("-i"):
                command.append("-i")
            command.extend(["-e", pattern, "--", str(path)])
            output = await self._rg(*command)
            mode = args.get("output_mode", "files_with_matches")
            if mode not in ("content", "files_with_matches", "count"):
                raise ValueError("Unknown Grep output_mode")
            limit = min(100, max(1, int(args.get("head_limit", 100))))
            found = {}
            displayed = []
            snapshots = {}
            for raw in output.splitlines():
                event = json.loads(raw)
                if event["type"] not in ("match", "context"):
                    continue
                data = event["data"]
                if "text" not in data["path"] or "text" not in data["lines"]:
                    continue
                filename = data["path"]["text"]
                if filename not in snapshots:
                    try:
                        snapshots[filename] = self._source(filename)
                    except ValueError:
                        # A large/binary match must not discard usable results
                        # from other source files in the same search.
                        snapshots[filename] = None
                if snapshots[filename] is None:
                    continue
                source, lines, digest = snapshots[filename]
                number = data["line_number"]
                text = data["lines"]["text"].rstrip("\r\n")
                if event["type"] == "match":
                    found[source] = found.get(source, 0) + 1
                if mode == "content" and len(displayed) < limit and 1 <= number <= len(lines) and lines[number - 1] == text:
                    self._record(source, digest, [number])
                    displayed.append(f"{source}:{number}:{text[:1000]}")
                    if len(displayed) >= limit:
                        break
            if mode == "content":
                return "\n".join(displayed) or "No matches found"
            return "\n".join(f"{p}:{n}" if mode == "count" else str(p) for p, n in list(found.items())[:limit]) or "No matches found"
        raise ValueError(f"Unknown tool: {name}")

    async def call(self, message):
        results = []
        for call in message.tool_calls:
            try:
                output = await self.invoke(call.name, json.loads(call.arguments or "{}"))
            except (ValueError, TypeError, OSError, TimeoutError) as error:
                output = f"Tool error: {error} Repository root: {self.root}. Discover existing files before retrying."
            results.append(self.message_factory(role="tool", content=output, tool_call_id=call.id))
        return results

    async def orient(self, query):
        output = await self._rg("--files")
        words = set(re.findall(r"[a-z]{3,}", query.lower())) - {
            "the", "and", "find", "trace", "source", "files", "read", "with", "from", "this", "that", "report", "path", "actual", "repository",
        }
        def score(path):
            tokens = re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", path).lower())
            return sum(1 for word in words if any(token == word or (len(word) >= 4 and token.startswith(word[:4])) for token in tokens))
        ranked = sorted(output.splitlines(), key=lambda p: (-score(p), len(p), p))
        selected = []
        directories = {}
        for path in ranked:
            directory = str(Path(path).parent)
            if score(path) > 0 and directories.get(directory, 0) < 3:
                selected.append(path)
                directories[directory] = directories.get(directory, 0) + 1
            if len(selected) == 30:
                break
        if not selected:
            selected = ranked[:20]
        return (f"Repository root: {self.root}\nUse repository-relative tool paths or the exact absolute paths below. "
                "Do not invent a workspace prefix. File listing is discovery only; Read or Grep content before citing.\n"
                + "\n".join(str(self.path(p)) for p in selected)
                + f"\n\n<query>{query}</query>")

    def receipts(self):
        ranges = []
        for path, (_, numbers) in self.evidence.items():
            ordered = sorted(numbers)
            if not ordered:
                continue
            start = end = ordered[0]
            for number in ordered[1:]:
                if number == end + 1:
                    end = number
                else:
                    ranges.append(f"{path}:{start}-{end}")
                    start = end = number
            ranges.append(f"{path}:{start}-{end}")
        return "\n".join(ranges[:40]) or "No source content has been observed."

    def validate(self, answer):
        if not self.evidence:
            raise ExplorationError("No source evidence was observed; citations cannot be verified. Narrow the query or use direct search.")
        block = re.search(r"<final_answer>(.*?)</final_answer>", answer or "", re.S)
        lines = (block[1] if block else answer or "").strip().splitlines()
        citations = []
        for line in lines:
            match = re.fullmatch(r"\s*(.+?):(\d+)(?:-(\d+))?(?:\s+\(.*\))?\s*", line)
            if not match:
                if line.strip():
                    raise ExplorationError("Final answer must contain only source citations, one per line")
                continue
            path, source, digest = self._source(match[1])
            start, end = int(match[2]), int(match[3] or match[2])
            record = self.evidence.get(path)
            if not record or record[0] != digest or not (1 <= start <= end <= len(source)) or any(n not in record[1] for n in range(start, end + 1)):
                raise ExplorationError(f"Citation lacks observed, unchanged source lines: {path}:{start}-{end}")
            citation = f"{path}:{start}-{end}"
            if citation not in citations:
                citations.append(citation)
        if not citations:
            raise ExplorationError("No source-backed citations were produced")
        # Discard model-written explanations: structural citation validation does
        # not establish the truth of arbitrary prose about the referenced code.
        return "\n".join(citations)

    def verified_subset(self, answer):
        """Retain only individually verified citations for an explicit partial result."""
        block = re.search(r"<final_answer>(.*?)</final_answer>", answer or "", re.S)
        lines = (block[1] if block else answer or "").strip().splitlines()
        citations = []
        for line in lines[:100]:
            try:
                citation = self.validate(line)
            except (ValueError, OSError):
                continue
            if citation not in citations:
                citations.append(citation)
        return "\n".join(citations)
