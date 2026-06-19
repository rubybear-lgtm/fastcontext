"""MCP server wrapping FastContext with in-process MLX inference.

Loads the fine-tuned exploration model directly via mlx_lm — no external
HTTP server, no env vars, no subprocess management. The model lives in
the same process as the MCP server.
"""

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mlx_lm import load, generate

from fastcontext.agent.agent import Agent
from fastcontext.agent.context import Context
from fastcontext.agent.llm import Message, FunctionCall, RequestyAPIError
from fastcontext.agent.tool.tool import ToolSet
from fastcontext.agent.utils import load_system_prompt, get_final_answer

MODEL_NAME = "mattrobenolt/FastContext-1.0-4B-SFT-mlx-bf16"

print(f"[fastcontext-mcp] Loading model: {MODEL_NAME}")
_mlx_model, _tokenizer = load(MODEL_NAME)
print(f"[fastcontext-mcp] Model loaded.")

mcp = FastMCP("fastcontext")


class MlxLLM:
    """Drop-in replacement for FastContext's LLM that uses mlx_lm directly."""

    def __init__(self, model_name: str):
        self.model = model_name

    async def acall(
        self,
        messages: list[dict | Message],
        tools: list[dict] | None,
    ) -> Message:
        if isinstance(messages[0], Message):
            messages = [m.to_dict(exclude_none=True) for m in messages]

        prompt = _tokenizer.apply_chat_template(
            messages,
            tools=[t["function"] for t in tools] if tools else None,
            add_generation_prompt=True,
            tokenize=False,
        )

        text = await asyncio.to_thread(
            generate,
            _mlx_model,
            _tokenizer,
            prompt=prompt,
            max_tokens=4096,
            verbose=False,
        )

        return self._parse_response(text)

    def _parse_response(self, text: str) -> Message:
        tool_calls = self._extract_tool_calls(text)
        if tool_calls:
            content_before = text[:text.find("<tool_call>")].strip() or None
            return Message(
                role="assistant",
                content=content_before,
                tool_calls=tool_calls,
                tool_call_id=tool_calls[0].id,
                model=self.model,
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
        return Message(
            role="assistant",
            content=text.strip(),
            model=self.model,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )

    def _extract_tool_calls(self, text: str) -> list[FunctionCall]:
        calls = []
        for i, match in enumerate(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)):
            try:
                data = json.loads(match.group(1))
                name = data.get("name", "")
                args = data.get("arguments", {})
                call_id = f"call_{i}"
                calls.append(FunctionCall(
                    id=call_id,
                    name=name,
                    arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return calls


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


@mcp.tool()
async def fastcontext_explore(query: str, max_turns: int = 4) -> str:
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
        result = await agent.run(prompt=query, max_turns=max_turns, citation=True)
        return result or "No results found."
    finally:
        Path(traj_path).unlink(missing_ok=True)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
