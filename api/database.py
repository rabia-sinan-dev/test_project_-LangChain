"""Supabase Postgres helpers for LangGraph checkpointing."""

from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import OperationalError
from psycopg_pool import AsyncConnectionPool, PoolTimeout


class DatabaseConfigError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise DatabaseConfigError(
            "DATABASE_URL is required. Use your Supabase Postgres pooler URI."
        )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_setup_done = False


def is_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, (OperationalError, PoolTimeout)):
        return True
    text = str(exc).lower()
    needles = (
        "server closed the connection",
        "consuming input failed",
        "connection is closed",
        "connection not open",
        "broken pipe",
        "could not receive data",
        "ssl connection has been closed",
        "couldn't get a connection",
    )
    return any(n in text for n in needles)


async def close_checkpointer() -> None:
    global _pool, _checkpointer, _setup_done

    pool = _pool
    _pool = None
    _checkpointer = None
    if pool is not None:
        try:
            await pool.close()
        except Exception:  # noqa: BLE001
            pass


async def get_checkpointer() -> AsyncPostgresSaver:
    global _pool, _checkpointer, _setup_done

    if _checkpointer is not None:
        return _checkpointer

    database_url = get_database_url()
    _pool = AsyncConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=3,
        max_lifetime=300,
        max_idle=60,
        timeout=30,
        reconnect_timeout=5,
        check=AsyncConnectionPool.check_connection,
        kwargs={
            "autocommit": True,
            "prepare_threshold": None,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 3,
        },
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)

    if not _setup_done:
        await _checkpointer.setup()
        _setup_done = True

    return _checkpointer
