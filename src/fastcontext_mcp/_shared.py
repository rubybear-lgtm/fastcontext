"""Shared LLM utilities for MlxLLM and BenchLLM.

These functions are extracted from verbatim duplicated methods in
server.py and benchmark/_runner.py to eliminate copy-paste maintenance risk.
"""

import json
import re

from fastcontext.agent.llm import FunctionCall, Message

_ZERO_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def extract_tool_calls(text: str) -> list[FunctionCall]:
    """Extract tool calls from model response XML tags.

    Parses ``<tool_call>{"name": "...", "arguments": {...}}</tool_call>``
    blocks from the model's raw text output.
    """
    calls: list[FunctionCall] = []
    for i, match in enumerate(
        re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
    ):
        try:
            data = json.loads(match.group(1))
            if not isinstance(data, dict):
                continue
            name = data.get("name", "")
            args = data.get("arguments", {})
            call_id = f"call_{i}"
            calls.append(
                FunctionCall(
                    id=call_id,
                    name=name,
                    arguments=json.dumps(args) if isinstance(args, dict) else str(args),
                )
            )
        except (json.JSONDecodeError, AttributeError):
            continue
    return calls


def parse_response(text: str, model: str) -> Message:
    """Parse model response text into a Message, extracting any tool calls.

    If tool calls are found, everything before the first ``<tool_call>`` tag
    is treated as the text content.  Otherwise the entire stripped text is
    returned as a plain assistant message.
    """
    tool_calls = extract_tool_calls(text)
    if tool_calls:
        content_before = text[: text.find("<tool_call>")].strip() or None
        return Message(
            role="assistant",
            content=content_before,
            tool_calls=tool_calls,
            tool_call_id=tool_calls[0].id,
            model=model,
            usage=_ZERO_USAGE,
        )
    return Message(
        role="assistant",
        content=text.strip(),
        model=model,
        usage=_ZERO_USAGE,
    )
