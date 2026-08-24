# Partial stub -- only symbols used in this project.

import datetime
from collections.abc import Callable
from typing import Literal

from .mixins import AnonymousUserMixin, UserMixin

current_user: UserMixin | AnonymousUserMixin = ...

def login_user(
    user: UserMixin,
    remember: bool = ...,
    duration: datetime.timedelta = ...,
    force: bool = ...,
    fresh: bool = ...,
) -> bool: ...
def logout_user() -> Literal[True]: ...
def login_required[T: Callable[..., object]](func: T) -> T: ...
