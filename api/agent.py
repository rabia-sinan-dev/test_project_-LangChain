"""Deep Agents chat backend for Rabia."""

from __future__ import annotations

import ast
import operator
import os
import re
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from api.database import close_checkpointer, get_checkpointer


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_ast(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
        return _SAFE_OPS[type(node.op)](_eval_ast(node.left), _eval_ast(node.right))
    raise ValueError("Unsupported expression")


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression (e.g. '2 + 2 * 10')."""
    cleaned = expression.strip()
    if not re.fullmatch(r"[0-9+\-*/().%\s]+", cleaned):
        return "Error: only numbers and + - * / % ( ) are allowed."
    try:
        result = _eval_ast(ast.parse(cleaned, mode="eval"))
        return str(result)
    except Exception as exc:  # noqa: BLE001
        return f"Error evaluating expression: {exc}"


@tool
def web_search(query: str) -> str:
    """Stub web search tool that returns placeholder research notes."""
    return (
        f"Search results for '{query}':\n"
        "1. Overview — key concepts and recent developments related to the query.\n"
        "2. Context — common use cases, trade-offs, and practical considerations.\n"
        "3. Sources — synthesize these points when answering; this is a demo stub."
    )


MAIN_TOOLS = [calculator, web_search]
RESEARCH_TOOLS = [web_search, calculator]


def _get_llm() -> ChatGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required.")
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return ChatGroq(model=model, temperature=0.2, api_key=api_key)


PRIMARY_SYSTEM = """You are Rabia, a helpful assistant.

Guidelines:
- Prefer concise, accurate answers.
- Use the calculator tool for math.
- Use web_search for simple factual lookups.
- For thorough analysis, comparisons, multi-step investigation, or research-oriented questions,
  delegate to the researcher subagent via the task tool.
- After a research briefing returns, write the final user-facing answer yourself.
- Do not invent tool or subagent results; call tools or delegate when needed."""

RESEARCH_SYSTEM = """You are the researcher subagent.

Investigate the assigned question thoroughly using web_search and calculator when helpful.
Return a concise research briefing for the main agent with:
- Key findings
- Important caveats
- Short synthesis

Do not address the end user directly; the main agent will write the final answer."""

RESEARCHER_SUBAGENT = {
    "name": "researcher",
    "description": (
        "A specialized research agent used for deeper, comparative, multi-step, "
        "or research-oriented questions. Delegate here when the user needs "
        "thorough investigation beyond a quick lookup."
    ),
    "system_prompt": RESEARCH_SYSTEM,
    "tools": RESEARCH_TOOLS,
}


_agent = None


def build_deep_agent(checkpointer: Any):
    return create_deep_agent(
        model=_get_llm(),
        tools=MAIN_TOOLS,
        system_prompt=PRIMARY_SYSTEM,
        subagents=[RESEARCHER_SUBAGENT],
        checkpointer=checkpointer,
        backend=StateBackend(),
        name="rabia",
    )


async def get_compiled_graph(*, force_refresh: bool = False):
    global _agent
    if force_refresh:
        await reset_compiled_graph()
    if _agent is not None:
        return _agent

    checkpointer = await get_checkpointer()
    _agent = build_deep_agent(checkpointer)
    return _agent


async def reset_compiled_graph() -> None:
    global _agent
    _agent = None
    await close_checkpointer()


NODE_STATUS: dict[str, str] = {
    "model": "Primary agent thinking…",
    "tools": "Tool node invoked",
}


def describe_tool_calls(message: AIMessage) -> list[str]:
    statuses: list[str] = []
    for call in message.tool_calls or []:
        name = call.get("name", "unknown")
        if name == "task":
            args = call.get("args") or {}
            subagent = (
                args.get("subagent_type")
                or args.get("name")
                or args.get("agent")
                or "subagent"
            )
            if str(subagent) == "researcher":
                statuses.append("Research/delegation started")
                statuses.append("Research sub-agent working…")
            else:
                statuses.append(f"Delegating to subagent: {subagent}")
        else:
            statuses.append(f"Tool invoked: {name}")
    return statuses


def describe_tool_result(message: ToolMessage) -> str:
    tool_name = getattr(message, "name", None) or "tool"
    if tool_name == "task":
        return "Research completed"
    return f"Tool result received: {tool_name}"


def extract_text(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def should_emit_token(node_name: str, message: AIMessage) -> bool:
    if message.tool_calls:
        return False
    text = extract_text(message.content).strip()
    if not text:
        return False
    if node_name in {"model", "agent", "rabia"}:
        return True
    return node_name not in {"tools"}
