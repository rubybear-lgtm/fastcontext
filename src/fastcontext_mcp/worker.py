"""Disposable MLX inference worker; one exploration per process."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import mlx.core as mx
from fastcontext.agent.agent import Agent
from fastcontext.agent.llm import Message, RequestyAPIError
from fastcontext.agent.tool.tool import ToolSet
from fastcontext.agent.utils import get_final_answer, load_system_prompt
from mlx_lm import load
from mlx_lm.generate import stream_generate
from mlx_lm.models.cache import make_prompt_cache

from fastcontext_mcp._shared import parse_response

MODEL_NAME = "rubybear/FastContext-1.0-4B-SFT-mlx-4bit-g32"

_mlx_model = None
_tokenizer = None

class MlxLLM:
    """Drop-in replacement for FastContext's LLM that uses mlx_lm directly.

    Maintains a KV cache across turns so each turn only prefills new tokens
    (tool results) instead of re-processing the entire conversation.
    """

    def __init__(self, model_name: str):
        self.model = model_name
        self._cache = None
        self._n_cached = 0

    def reset_cache(self):
        self._cache = make_prompt_cache(_mlx_model)
        self._n_cached = 0

    async def acall(
        self,
        messages: list[dict | Message],
        tools: list[dict] | None,
    ) -> Message:
        if isinstance(messages[0], Message):
            messages = [m.to_dict(exclude_none=True) for m in messages]

        all_tokens = _tokenizer.apply_chat_template(
            messages,
            tools=[t["function"] for t in tools] if tools else None,
            add_generation_prompt=True,
            tokenize=True,
        )

        if self._cache is None:
            self.reset_cache()

        new_tokens = all_tokens[self._n_cached:]
        if len(new_tokens) < 1:
            self.reset_cache()
            new_tokens = all_tokens

        text, n_gen = await asyncio.to_thread(
            self._generate_cached, new_tokens,
        )

        self._n_cached = len(all_tokens) + n_gen
        return self._parse_response(text)

    def _generate_cached(self, tokens: list[int]) -> tuple[str, int]:
        prompt = mx.array(tokens)
        text = ""
        last_response = None
        for response in stream_generate(
            _mlx_model, _tokenizer, prompt,
            max_tokens=2048,
            prompt_cache=self._cache,
        ):
            text += response.text
            last_response = response
        n_gen = (last_response.generation_tokens - 1) if last_response else 0
        return text, n_gen

    def _parse_response(self, text: str) -> Message:
        return parse_response(text, self.model)


def _make_agent(work_dir: str, traj_path: str) -> Agent:
    """Create a FastContext agent using the in-process MLX model."""
    from fastcontext.agent.tool.glob import GlobTool
    from fastcontext.agent.tool.grep import GrepTool
    from fastcontext.agent.tool.read import ReadTool

    llm = MlxLLM(MODEL_NAME)
    system_prompt = load_system_prompt(work_dir)
    toolset = ToolSet([ReadTool(), GlobTool(), GrepTool()], work_dir=work_dir)

    return Agent(
        name="FastContext",
        system_prompt=system_prompt,
        llm=llm,
        toolset=toolset,
        trajectory_file=traj_path,
        work_dir=work_dir,
    )


async def _report(ctx, progress, total, message):
    if ctx:
        try:
            await ctx.report_progress(progress, total, message)
        except Exception:
            pass


async def _run_agent_with_progress(agent, query, max_turns, ctx):
    """Run the agent loop with MCP progress reporting."""
    steps = []
    await agent.context.add(Message(role="system", content=agent.system_prompt))
    await agent.context.add(Message(role="user", content=query))

    for turn in range(1, max_turns + 2):
        if turn > max_turns:
            await agent.context.add(Message(
                role="user",
                content="Max number of turns reached. Please provide the final answer based on the information you have gathered.",
            ))

        await _report(ctx,turn - 1, max_turns, f"Turn {turn}/{max_turns}: thinking...")

        try:
            step_msg = await agent.llm.acall(
                messages=agent.context.get_messages(),
                tools=agent.toolset.schema_list(),
            )
        except RequestyAPIError as e:
            return f"LLM error: {e}", steps

        await agent.context.add(step_msg)

        if step_msg.tool_calls:
            for tc in step_msg.tool_calls:
                args = json.loads(tc.arguments) if tc.arguments else {}
                summary = _summarize_tool_call(tc.name, args)
                steps.append(f"[turn {turn}] {summary}")
                await _report(ctx,turn - 1, max_turns, f"Turn {turn}/{max_turns}: {summary}")

            tools_result_msg = await agent.toolset.call(step_msg)
            await agent.context.add(tools_result_msg)
        else:
            await _report(ctx,max_turns, max_turns, "Done")
            return get_final_answer(step_msg.content), steps

    return "No final answer after max turns.", steps


def _summarize_tool_call(name, args):
    if name == "Read":
        return f"Read {args.get('file_path', '?')}"
    if name == "Glob":
        return f"Glob {args.get('pattern', '?')}"
    if name == "Grep":
        pattern = args.get("pattern", "?")
        path = args.get("path", "")
        return f"Grep '{pattern}'" + (f" in {path}" if path else "")
    return f"{name}({args})"


async def fastcontext_explore(query: str, max_turns: int = 4, ctx=None) -> str:
    """Explore a codebase using FastContext's parallel search agent.

    Runs Read, Glob, and Grep operations in parallel using a local MLX model,
    returning compact file-path:line-range citations. Use this for broad
    codebase exploration before making targeted edits.

    Args:
        query: Natural-language description of what to find
        max_turns: Maximum exploration turns (default 4, max 10)
    """
    max_turns = min(max(1, max_turns), 10)
    work_dir = os.getcwd()

    with tempfile.NamedTemporaryFile(
        suffix=".jsonl", prefix="fastcontext_", delete=False, dir=tempfile.gettempdir()
    ) as traj:
        traj_path = traj.name

    try:
        agent = _make_agent(work_dir, traj_path)
        if ctx:
            await _report(ctx,0, max_turns, "Starting exploration...")
        result, steps = await _run_agent_with_progress(agent, query, max_turns, ctx)

        output = []
        if steps:
            output.append("## Exploration steps")
            for s in steps:
                output.append(f"- {s}")
            output.append("")
        output.append("## Result")
        output.append(result or "No results found.")
        return "\n".join(output)
    finally:
        Path(traj_path).unlink(missing_ok=True)


def main():
    """One request per process; EOF from the parent also terminates inference."""
    import fcntl
    import json
    import sys
    import threading

    protocol = sys.stdout
    sys.stdout = sys.stderr
    request = json.loads(sys.stdin.readline())

    def watch_parent():
        # Parent keeps stdin open while serving this request. No idle orphan workers.
        sys.stdin.read()
        # Also terminate any tool descendants when launched in an isolated group.
        if os.getpgrp() == os.getpid():
            import signal

            os.killpg(os.getpid(), signal.SIGTERM)
        os._exit(0)

    threading.Thread(target=watch_parent, daemon=True).start()

    def emit(event):
        protocol.write(json.dumps(event) + "\n")
        protocol.flush()

    class Progress:
        async def report_progress(self, progress, total, message):
            emit({"progress": progress, "total": total, "message": message})

    # Multiple MCP clients keep separate connections, but only one loads a model
    # at a time. Kernel releases the lock even if a worker crashes or is killed.
    lock_path = Path.home() / ".cache/fastcontext/inference.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        emit({"progress": 0, "total": request["max_turns"], "message": "Waiting for local inference slot..."})
        fcntl.flock(lock, fcntl.LOCK_EX)
        global _mlx_model, _tokenizer
        emit({"progress": 0, "total": request["max_turns"], "message": "Loading local model..."})
        _mlx_model, _tokenizer = load(MODEL_NAME)
        result = asyncio.run(fastcontext_explore(**request, ctx=Progress()))
        emit({"result": result})


if __name__ == "__main__":
    main()
