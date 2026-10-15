"""Bounded exploration loop with source-backed output, independent of MLX."""

import json

from fastcontext_mcp.sources import ExplorationError


async def report(ctx, progress, total, message):
    if ctx:
        try:
            await ctx.report_progress(progress, total, message)
        except Exception:
            pass


def summarize(name, args):
    if name == "Read":
        return f"Read {args.get('path', '?')}"
    if name == "Glob":
        return f"Glob {args.get('pattern', '?')}"
    if name == "Grep":
        return f"Grep {args.get('pattern', '?')!r} in {args.get('path', '.')}"
    return name


async def run_agent(agent, query, max_turns, ctx, message_factory):
    steps = []
    await agent.context.add(message_factory(role="system", content=agent.system_prompt))
    orientation = await agent.toolset.orient(query)
    await agent.context.add(message_factory(role="user", content=orientation))
    for turn in range(1, max_turns + 2):
        if turn > max_turns:
            await agent.context.add(message_factory(
                role="user", content="Turn budget reached. Return relevant citations from the observed ranges below, one per line inside <final_answer>. No more tool calls, prose, or guessed ranges.\n" + agent.toolset.receipts(),
            ))
        await report(ctx, min(turn - 1, max_turns), max_turns, f"Turn {turn}/{max_turns}: thinking...")
        message = await agent.llm.acall(messages=agent.context.get_messages(), tools=agent.toolset.schema_list())
        await agent.context.add(message)
        if message.tool_calls:
            for call in message.tool_calls:
                try:
                    args = json.loads(call.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                summary = summarize(call.name, args)
                steps.append(f"[turn {turn}] {summary}")
                await report(ctx, min(turn - 1, max_turns), max_turns, summary)
            if turn > max_turns:
                raise ExplorationError("Exploration exhausted its tool budget without a source-backed final answer")
            await agent.context.add(await agent.toolset.call(message))
        else:
            try:
                result = agent.toolset.validate(message.content)
            except (ValueError, OSError) as error:
                if turn > max_turns:
                    partial = agent.toolset.verified_subset(message.content)
                    if partial:
                        await report(ctx, max_turns, max_turns, "Done")
                        return "Partial exploration: unverified citations were omitted; these source locations do not establish complete coverage.\n" + partial, steps
                    raise ExplorationError(f"Exploration could not verify its final citations: {error}") from error
                await agent.context.add(message_factory(
                    role="user", content=f"Answer rejected: {error}. Use actual files under {agent.work_dir}. Read the cited line ranges first. Return only verified path:start-end citations inside <final_answer>; no prose or descriptions. Observed ranges:\n{agent.toolset.receipts()}",
                ))
                continue
            await report(ctx, max_turns, max_turns, "Done")
            return result, steps
    raise ExplorationError("Exploration ended without source-backed citations")
