"""Database handling bits."""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType, cast

from asyncpg import Connection, create_pool
from asyncpg.prepared_stmt import PreparedStatement

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import svcs

InsertPending = NewType("InsertPending", PreparedStatement)  # type: ignore[type-arg]
SelectPendingByStateToken = NewType("SelectPendingByStateToken", PreparedStatement)  # type: ignore[type-arg]
DeletePending = NewType("DeletePending", PreparedStatement)  # type: ignore[type-arg]

InsertActive = NewType("InsertActive", PreparedStatement)  # type: ignore[type-arg]
SelectActive = NewType("SelectActive", PreparedStatement)  # type: ignore[type-arg]


async def database_setup(registry: svcs.Registry) -> None:
    """Set up all the database entries we need in our registry."""
    pool = await create_pool(database="precord", command_timeout=60)
    assert pool is not None

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
