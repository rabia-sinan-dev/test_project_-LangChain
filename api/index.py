"""FastAPI SSE endpoint for the Rabia agent."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field

from agent import (
    NODE_STATUS,
    describe_tool_calls,
    describe_tool_result,
    extract_text,
    get_compiled_graph,
    reset_compiled_graph,
    should_emit_token,
)
from database import DatabaseConfigError, is_connection_error

app = FastAPI(title="Rabia Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _stream_graph(
    graph: Any,
    message: str,
    thread_id: str,
) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {"messages": [HumanMessage(content=message)]}

    async for event in graph.astream(inputs, config=config, stream_mode="updates"):
        if not isinstance(event, dict):
            continue

        for node_name, update in event.items():
            status = NODE_STATUS.get(node_name)
            if status:
                yield _sse({"type": "status", "content": status})
            elif "researcher" in str(node_name).lower():
                yield _sse({
                    "type": "status",
                    "content": "Research sub-agent working…",
                })

            messages = update.get("messages") if isinstance(update, dict) else None
            if not messages:
                continue

            for msg in messages:
                if isinstance(msg, AIMessage):
                    for tool_status in describe_tool_calls(msg):
                        yield _sse({"type": "status", "content": tool_status})

                    if should_emit_token(node_name, msg):
                        yield _sse({
                            "type": "token",
                            "content": extract_text(msg.content).strip(),
                        })

                elif isinstance(msg, ToolMessage):
                    yield _sse({
                        "type": "status",
                        "content": describe_tool_result(msg),
                    })


async def event_stream(message: str, thread_id: str) -> AsyncIterator[str]:
    yield _sse({"type": "status", "content": "Agent starting…"})

    for attempt in range(2):
        try:
            graph = await get_compiled_graph(force_refresh=(attempt > 0))
            async for chunk in _stream_graph(graph, message, thread_id):
                yield chunk
            yield _sse({"type": "done"})
            return
        except DatabaseConfigError as exc:
            yield _sse({"type": "error", "content": str(exc)})
            yield _sse({"type": "done"})
            return
        except Exception as exc:  # noqa: BLE001
            if attempt == 0 and is_connection_error(exc):
                yield _sse({
                    "type": "status",
                    "content": "Database connection dropped — reconnecting…",
                })
                await reset_compiled_graph()
                continue
            yield _sse({"type": "error", "content": str(exc)})
            yield _sse({"type": "done"})
            return


@app.get("/")
@app.get("/api")
async def health() -> dict:
    return {"status": "ok", "service": "rabia-agent"}


@app.post("/")
@app.post("/api")
@app.post("/chat")
@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    return StreamingResponse(
        event_stream(request.message.strip(), request.thread_id.strip()),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
