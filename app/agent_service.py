# agent_service.py - Deliverable 4: a LangChain agent that consumes the
# MCP server's tools (mcp_server/logistics_mcp.py) through the official
# langchain-mcp-adapters bridge, run in a think/act/observe loop by
# LangGraph's prebuilt ReAct agent. app/main.py's POST /ask-logistics wraps
# run_logistics_agent() behind app.auth.current_user, so the agent shares
# exactly the same authentication as every other route in this service.
#
# A fresh MultiServerMCPClient + agent is built per call rather than kept
# as a long-lived global: no stale-tool-list risk, no child process to
# manage across requests, and it keeps a lab-scale service simple. The
# tradeoff (one subprocess spin-up per request) is documented in
# docs/STAKEHOLDER_MEMO.md's risk section.
#
# Run it standalone (needs a real OPENAI_API_KEY in .env):
#   python -m app.agent_service

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

REPO_ROOT = Path(__file__).resolve().parent.parent

# The agent must say "I don't know" rather than invent an answer when the
# tools genuinely cannot help — see evidence/agent_transcript.md's honest
# failure case (asking for prices, which no tool here provides).
SYSTEM_CONTEXT = (
    "You are the AfyaPlus logistics assistant. You can check medical stock "
    "levels, plan delivery routes, estimate delivery times, and plan "
    "reorders across partner clinics. If the tools available to you cannot "
    "answer part or all of a question — for example anything about price "
    "or cost, which no tool here provides — say so plainly instead of "
    "guessing or inventing data."
)

SERVERS = {
    "logistics": {
        "command": "python",
        "args": ["mcp_server/logistics_mcp.py"],
        "transport": "stdio",
        "cwd": str(REPO_ROOT),
    }
}


async def build_agent():
    """Start the MCP server as a child process, wrap its tools for a real
    LLM, and compile the think/act/observe loop."""
    client = MultiServerMCPClient(SERVERS)
    tools = await client.get_tools()
    model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return create_react_agent(model, tools)


async def run_logistics_agent(question: str, trace_id: str | None = None) -> str:
    """Ask the logistics agent one question and return its final answer.

    trace_id is accepted so app/main.py's /ask-logistics can correlate this
    call with its own API-level log line — see docs/TRACE_RECONSTRUCTION.md
    for exactly how a request is followed from there into
    mcp_server/logistics_mcp.py's per-tool log lines by timestamp
    correlation (MCP's tool-call protocol does not carry a caller-supplied
    trace id through to the tool function itself, so exact propagation
    would need a custom tool interceptor — out of scope for this capstone,
    and documented as such rather than silently overclaimed).
    """
    agent = await build_agent()
    messages = [("system", SYSTEM_CONTEXT), ("user", question)]
    result = await agent.ainvoke(
        {"messages": messages},
        {"recursion_limit": 8},  # loop budget: stop a confused agent from running up the bill
    )
    if trace_id:
        logging.getLogger("agent_service").info("trace=%s agent call complete", trace_id)
    return result["messages"][-1].content


async def main() -> None:
    answer = await run_logistics_agent(
        "Which clinics need an amoxicillin reorder, and what's the ETA "
        "from Kisumu Central Clinic to the nearest one that needs it?"
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
