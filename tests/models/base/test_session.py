from __future__ import annotations

import anyio
from sqlalchemy import orm

from flask_htmx_template.models.base import Base


async def _capture_task_local_sessions(
    first: orm.Session,
    second: orm.Session,
) -> tuple[orm.Session, orm.Session]:
    """Capture the active ORM session observed by two concurrent tasks.

    Args:
        first: Session bound in the first task
        second: Session bound in the second task

    Returns:
        Sessions observed by the first and second tasks

    """
    first_entered = anyio.Event()
    second_entered = anyio.Event()
    both_entered = anyio.Event()
    first_observed = anyio.Event()
    second_observed = anyio.Event()
    release_tasks = anyio.Event()
    observed: list[orm.Session | None] = [None, None]

    async def capture(
        session: orm.Session,
        index: int,
        entered: anyio.Event,
        session_observed: anyio.Event,
    ) -> None:
        """Capture one task's active session while both contexts overlap."""
        with Base.set_session(session):
            entered.set()
            await both_entered.wait()
            observed[index] = Base.session()
            session_observed.set()
            await release_tasks.wait()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(capture, first, 0, first_entered, first_observed)
        await first_entered.wait()
        task_group.start_soon(capture, second, 1, second_entered, second_observed)
        await second_entered.wait()
        both_entered.set()
        await first_observed.wait()
        await second_observed.wait()
        release_tasks.set()

    observed_first, observed_second = observed
    assert observed_first is not None
    assert observed_second is not None
    return observed_first, observed_second


def test_active_session_is_task_local_under_concurrency(
    session: orm.Session,
) -> None:
    with (
        orm.Session(bind=session.get_bind()) as first,
        orm.Session(bind=session.get_bind()) as second,
    ):
        observed = anyio.run(_capture_task_local_sessions, first, second)

        assert observed == (first, second)
