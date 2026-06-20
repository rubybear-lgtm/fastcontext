#!/usr/bin/env python3
"""Subprocess runner for a single FastContext exploration.

Loads the model, runs the agent, prints JSON to stdout.
Isolated per-process to avoid MLX memory contamination between variants.
"""

import argparse
import asyncio
import json
import sys
import time
import os

# Suppress MLX/HF progress bars on stderr
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def run(model_path: str, work_dir: str, query: str, max_turns: int, traj_path: str):
    import shutil
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.generate import stream_generate
    from mlx_lm.models.cache import make_prompt_cache

    from fastcontext.agent.agent import Agent
    from fastcontext.agent.context import Context
    from fastcontext.agent.llm import Message, FunctionCall, RequestyAPIError
    from fastcontext.agent.tool.tool import ToolSet
    from fastcontext.agent.tool.glob import GlobTool
    from fastcontext.agent.tool.grep import GrepTool
    from fastcontext.agent.tool.read import ReadTool
    from fastcontext.agent.utils import load_system_prompt, get_final_answer

    import re

    rg_path = shutil.which("rg") or "/usr/bin/rg"
    GrepTool._rg_path = rg_path

    def detect_repetition(text: str, min_pattern_len: int = 20, min_repeats: int = 3) -> bool:
        if len(text) < min_pattern_len * min_repeats:
            return False
        tail = text[-min_pattern_len * min_repeats * 2:]
        for plen in range(min_pattern_len, len(tail) // min_repeats + 1):
            pattern = tail[-plen:]
            count = tail.count(pattern)
            if count >= min_repeats:
                return True
        return False

    t_load_start = time.time()
    model, tokenizer = load(model_path)
    t_load = time.time() - t_load_start

    class BenchLLM:
        def __init__(self):
            self.model = model_path
            self._cache = None
            self._n_cached = 0
            self.total_prompt_tokens = 0
            self.total_gen_tokens = 0
            self.total_gen_time = 0.0

        def reset_cache(self):
            self._cache = make_prompt_cache(model)
            self._n_cached = 0

        async def acall(self, messages, tools):
            if isinstance(messages[0], Message):
                messages = [m.to_dict(exclude_none=True) for m in messages]

            all_tokens = tokenizer.apply_chat_template(
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

            self.total_prompt_tokens += len(new_tokens)

            t0 = time.time()
            prompt = mx.array(new_tokens)
            text = ""
            last_response = None
            for response in stream_generate(
                model, tokenizer, prompt,
                max_tokens=2048,
                prompt_cache=self._cache,
            ):
                text += response.text
                last_response = response
                if len(text) > 200 and detect_repetition(text):
                    break

            gen_time = time.time() - t0
            n_gen = (last_response.generation_tokens - 1) if last_response else 0
            self.total_gen_tokens += last_response.generation_tokens if last_response else 0
            self.total_gen_time += gen_time
            self._n_cached = len(all_tokens) + n_gen

            return self._parse_response(text)

        def _parse_response(self, text):
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

        def _extract_tool_calls(self, text):
            calls = []
            for i, match in enumerate(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)):
                try:
                    data = json.loads(match.group(1))
                    name = data.get("name", "")
                    args = data.get("arguments", {})
                    calls.append(FunctionCall(
                        id=f"call_{i}",
                        name=name,
                        arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                    ))
                except (json.JSONDecodeError, KeyError):
                    continue
            return calls

    llm = BenchLLM()
    system_prompt = load_system_prompt(work_dir)
    toolset = ToolSet([ReadTool(), GlobTool(), GrepTool()], work_dir=work_dir)

    agent = Agent(
        name="FastContext",
        system_prompt=system_prompt,
        llm=llm,
        toolset=toolset,
        trajectory_file=traj_path,
        work_dir=work_dir,
    )

    t_run_start = time.time()
    final = asyncio.run(agent.run(query, max_turns=max_turns, verbose=False, citation=True))
    t_run = time.time() - t_run_start

    tok_per_sec = llm.total_gen_tokens / llm.total_gen_time if llm.total_gen_time > 0 else 0

    output = {
        "final_answer": final,
        "stats": {
            "model_load_time": round(t_load, 2),
            "run_time": round(t_run, 2),
            "total_prompt_tokens": llm.total_prompt_tokens,
            "total_gen_tokens": llm.total_gen_tokens,
            "total_gen_time": round(llm.total_gen_time, 2),
            "tokens_per_sec": round(tok_per_sec, 1),
            "n_turns": agent.n_turn,
        },
    }
    print(json.dumps(output))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-turns", type=int, default=6)
    parser.add_argument("--traj", required=True)
    args = parser.parse_args()

    run(args.model, args.work_dir, args.query, args.max_turns, args.traj)


if __name__ == "__main__":
    main()
