"""A text UI for monitoring active registration flows."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import psycopg
import typer
from psycopg.rows import class_row
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Self


AEDT = timezone(offset=timedelta(hours=11), name="AEDT")


@dataclass
class Pending:
    """Representation of a pending entry."""

    order_code: str
    position: int
    state_token: str
    created: datetime
    nickname: str | None
    roles: list[int]

    def __post_init__(self) -> None:
        """Perform post-init operations."""
        self.created = self.created.astimezone(AEDT)

    @classmethod
    def tabulate(cls, rows: Iterable[Self]) -> Table:
        """Turn a series of these entries into a table."""
        table = Table()
        table.add_column("Order")
        table.add_column("State Token")
        table.add_column("Created")
        table.add_column("Name")
        table.add_column("Roles")

        for row in rows:
            table.add_row(
                f"{row.order_code}-{row.position}",
                row.state_token,
                row.created.isoformat(sep=" ", timespec="minutes"),
                row.nickname,
                ", ".join(str(r) for r in row.roles),
            )

        return table


@dataclass
class Active:
    """Representation of an active entry."""

    order_code: str
    position: int
    user_id: str
    created: datetime
    nickname: str | None
    roles: list[int]

    def __post_init__(self) -> None:
        """Perform post-init operations."""
        self.created = self.created.astimezone(AEDT)

    @classmethod
    def tabulate(cls, rows: Iterable[Self]) -> Table:
        """Turn a series of these entries into a table."""
        table = Table()
        table.add_column("Order")
        table.add_column("User ID")
        table.add_column("Created")
        table.add_column("Name")
        table.add_column("Roles")

        for row in rows:
            table.add_row(
                f"{row.order_code}-{row.position}",
                row.user_id,
                row.created.isoformat(sep=" ", timespec="minutes"),
                row.nickname,
                ", ".join(str(r) for r in row.roles),
            )

        return table


def monitor() -> None:
    """Show a live display of active registration tokens."""
    with (
        Live(refresh_per_second=4, screen=True) as display,
        psycopg.connect("postgresql:///precord") as db,
    ):
        while True:
            now = datetime.now(AEDT).isoformat(sep=" ", timespec="seconds")

            with db.cursor(row_factory=class_row(Pending)) as cursor:
                cursor.execute("SELECT * FROM pending ORDER BY created DESC LIMIT 10")
                pending = Pending.tabulate(cursor.fetchall())

            with db.cursor(row_factory=class_row(Active)) as cursor:
                cursor.execute("SELECT * FROM active ORDER BY created DESC LIMIT 5")
                active = Active.tabulate(cursor.fetchall())

            now_text = Layout(Text(now, style="bold white", justify="right"), size=1)
            layout = Layout()
            layout.split_column(now_text, pending, Layout(active, size=12))
            display.update(layout)
            time.sleep(1)


if __name__ == "__main__":
    typer.run(monitor)
