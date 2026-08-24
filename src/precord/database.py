"""Database handling bits."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, NewType, cast
from urllib.parse import urlsplit

from asyncpg import Connection, PostgresError, create_pool
from asyncpg.prepared_stmt import PreparedStatement

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import svcs

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 15.0


class DatabaseUnavailableError(RuntimeError):
    """Raised when the database cannot be reached during startup."""


def describe_dsn(dsn: str) -> str:
    """Describe a DSN as host:port/database, discarding any credentials."""
    try:
        parts = urlsplit(dsn)
    except ValueError:
        return "<unparseable DSN>"

    if not parts.scheme:
        return "<malformed DSN>"

    if not parts.hostname:
        return "<local socket>"

    port = f":{parts.port}" if parts.port else ""
    return f"{parts.hostname}{port}{parts.path}"


InsertPending = NewType("InsertPending", PreparedStatement)  # type: ignore[type-arg]
SelectPendingByStateToken = NewType("SelectPendingByStateToken", PreparedStatement)  # type: ignore[type-arg]
DeletePending = NewType("DeletePending", PreparedStatement)  # type: ignore[type-arg]

InsertActive = NewType("InsertActive", PreparedStatement)  # type: ignore[type-arg]
SelectActive = NewType("SelectActive", PreparedStatement)  # type: ignore[type-arg]


async def database_setup(registry: svcs.Registry, dsn: str) -> None:
    """Set up all the database entries we need in our registry.

    Raises DatabaseUnavailableError if the database cannot be reached. The pool
    opens its connections eagerly, so an unreachable database fails here rather
    than on the first request. We let that stop startup deliberately: serving
    with no database would mean turning every attendee away. The error is
    reported as a single explicit line so the cause is visible in the container
    log without reading a traceback.
    """
    target = describe_dsn(dsn)
    try:
        pool = await create_pool(dsn, command_timeout=60, timeout=CONNECT_TIMEOUT)
    except (OSError, PostgresError, TimeoutError) as exc:
        logger.debug("Database connection traceback for %s", target, exc_info=True)
        message = f"FATAL: cannot reach the database at {target}: {exc}"
        raise DatabaseUnavailableError(message) from exc

    if pool is None:  # pragma: no cover - only when create_pool is patched out
        message = f"FATAL: no connection pool was created for {target}"
        raise DatabaseUnavailableError(message)

    logger.info("Connected to the database at %s", target)

    async def acquire_connection() -> AsyncGenerator[Connection, None]:  # type: ignore[type-arg]
        async with pool.acquire() as connection:
            yield cast(Connection, connection)  # type: ignore[type-arg]

    registry.register_factory(Connection, acquire_connection)

    async def prepare_insert_pending(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """INSERT INTO pending
               (order_code, position, state_token, created, nickname, roles)
               VALUES ($1, $2, $3, $4::timestamptz, $5, $6::bigint[])
               ON CONFLICT (order_code, position) DO UPDATE SET
               state_token=$3,
               created=$4::timestamptz,
               nickname=$5,
               roles=$6::bigint[]""",
        )

    registry.register_factory(InsertPending, prepare_insert_pending)

    async def prepare_select_pending_by_state_token(
        container: svcs.Container,
    ) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """SELECT order_code, position, created, nickname, roles
                FROM pending WHERE state_token = $1""",
        )

    registry.register_factory(SelectPendingByStateToken, prepare_select_pending_by_state_token)

    async def prepare_delete_pending(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """DELETE FROM pending WHERE order_code = $1 AND position = $2""",
        )

    registry.register_factory(DeletePending, prepare_delete_pending)

    async def prepare_insert_active(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """INSERT INTO active
               (order_code, position, user_id, created, nickname, roles)
               VALUES ($1, $2, $3, $4::timestamptz, $5, $6::bigint[])
               ON CONFLICT (order_code, position) DO UPDATE SET
               user_id=$3,
               created=$4::timestamptz,
               nickname=$5,
               roles=$6::bigint[]""",
        )

    registry.register_factory(InsertActive, prepare_insert_active)

    async def prepare_select_active(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """SELECT order_code, position, user_id, created, nickname, roles
                FROM active WHERE order_code = $1 AND position = $2""",
        )

    registry.register_factory(SelectActive, prepare_select_active)
