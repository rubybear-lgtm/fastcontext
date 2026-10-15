"""Disposable MLX inference worker; one exploration per process."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import mlx.core as mx
from fastcontext.agent.agent import Agent
from fastcontext.agent.llm import Message
from fastcontext.agent.utils import load_system_prompt
from mlx_lm import load
from mlx_lm.generate import stream_generate
from mlx_lm.models.cache import make_prompt_cache

from fastcontext_mcp._shared import parse_response
from fastcontext_mcp.engine import report as _report
from fastcontext_mcp.engine import run_agent
from fastcontext_mcp.sources import SourceTools, find_ripgrep

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
        self._prefix_tokens = []

    def reset_cache(self):
        self._cache = make_prompt_cache(_mlx_model)
        self._n_cached = 0
        self._prefix_tokens = []

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

        # Parsing tool calls and re-rendering the chat template can change token
        # serialization. A length alone cannot establish a reusable KV prefix.
        if all_tokens[:len(self._prefix_tokens)] != self._prefix_tokens:
            self.reset_cache()

        new_tokens = all_tokens[self._n_cached:]
        if len(new_tokens) < 1:
            self.reset_cache()
            new_tokens = all_tokens

        text, generated = await asyncio.to_thread(
            self._generate_cached, new_tokens,
        )

        self._prefix_tokens = all_tokens + generated[:-1]
        self._n_cached = len(self._prefix_tokens)
        return self._parse_response(text)

    def _generate_cached(self, tokens: list[int]) -> tuple[str, list[int]]:
        prompt = mx.array(tokens)
        text = ""
        generated = []
        for response in stream_generate(
            _mlx_model, _tokenizer, prompt,
            max_tokens=2048,
            prompt_cache=self._cache,
        ):
            text += response.text
            generated.append(response.token)
        return text, generated

    def _parse_response(self, text: str) -> Message:
        return parse_response(text, self.model)


def _make_agent(work_dir: str, traj_path: str) -> Agent:
    """Create a FastContext agent using the in-process MLX model."""
    llm = MlxLLM(MODEL_NAME)
    system_prompt = load_system_prompt(work_dir) + (
        "\nUse repository-relative tool paths or exact discovered paths. "
        "Only cite source lines actually shown by Read or Grep content. "
        "Return path:start-end citations only inside <final_answer>; omit descriptions."
    )
    toolset = SourceTools(work_dir, Message)

    return Agent(
        name="FastContext",
        system_prompt=system_prompt,
        llm=llm,
        toolset=toolset,
        trajectory_file=traj_path,
        work_dir=work_dir,
    )


async def _run_agent_with_progress(agent, query, max_turns, ctx):
    return await run_agent(agent, query, max_turns, ctx, Message)


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
        try:
            find_ripgrep()
            _mlx_model, _tokenizer = load(MODEL_NAME)
            result = asyncio.run(fastcontext_explore(**request, ctx=Progress()))
        except (ValueError, OSError, TimeoutError) as error:
            emit({"error": str(error)})
        else:
            emit({"result": result})


if __name__ == "__main__":
    main()
