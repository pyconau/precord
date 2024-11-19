"""Database handling bits."""

from __future__ import annotations

from typing import TYPE_CHECKING, NewType, cast

from asyncpg import Connection, create_pool
from asyncpg.prepared_stmt import PreparedStatement

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    import svcs

Insert = NewType("Insert", PreparedStatement)  # type: ignore[type-arg]
SelectByStateToken = NewType("SelectByStateToken", PreparedStatement)  # type: ignore[type-arg]
Delete = NewType("Delete", PreparedStatement)  # type: ignore[type-arg]


async def database_setup(registry: svcs.Registry) -> None:
    """Set up all the database entries we need in our registry."""
    pool = await create_pool(database="precord", command_timeout=60)
    assert pool is not None

    async def acquire_connection() -> AsyncGenerator[Connection, None]:  # type: ignore[type-arg]
        async with pool.acquire() as connection:
            yield cast(Connection, connection)  # type: ignore[type-arg]

    registry.register_factory(Connection, acquire_connection)

    async def prepare_insert(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            """INSERT INTO pending
               VALUES ($1, $2, $3::timestamptz, $4, $5::bigint[])
               ON CONFLICT (order_code) DO UPDATE SET
               state_token=$2, created=$3::timestamptz, nickname=$4, roles=$5::bigint[]""",
        )

    registry.register_factory(Insert, prepare_insert)

    async def prepare_select_by_state_token(
        container: svcs.Container,
    ) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare(
            "SELECT order_code, created, nickname, roles FROM pending WHERE state_token = $1",
        )

    registry.register_factory(SelectByStateToken, prepare_select_by_state_token)

    async def prepare_delete(container: svcs.Container) -> PreparedStatement:  # type: ignore[type-arg]
        connection = await container.aget(Connection)
        return await connection.prepare("DELETE FROM pending WHERE order_code = $1")

    registry.register_factory(Delete, prepare_delete)
