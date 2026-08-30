from __future__ import annotations

from contextvars import Context

import anyio
import pytest
from sqlalchemy import orm

from flask_htmx_template import exceptions as exc
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.mixins.session import SessionMixIn


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


def test_session_mixin_is_public_and_composed_into_base() -> None:
    assert Base.session.__func__ is SessionMixIn.session.__func__


def test_unbound_error() -> None:
    with pytest.raises(exc.UnboundExecutionError):
        Context().run(Base.session)


def test_active_session_is_task_local_under_concurrency(
    session: orm.Session,
) -> None:
    with (
        orm.Session(bind=session.get_bind()) as first,
        orm.Session(bind=session.get_bind()) as second,
    ):
        observed = anyio.run(_capture_task_local_sessions, first, second)

        assert observed == (first, second)
