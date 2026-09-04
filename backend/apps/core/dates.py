"""Reference date used by every business rule (status, urgency, alerts).

`today()` returns the local date in `TIME_ZONE`, unless overridden with
`override_today(date)` (used by the Excel import command and the tests).
"""

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

from django.utils import timezone

_today_override: contextvars.ContextVar[date | None] = contextvars.ContextVar(
    "amm_today_override", default=None
)


def today() -> date:
    return _today_override.get() or timezone.localdate()


@contextmanager
def override_today(value: date | None) -> Iterator[None]:
    token = _today_override.set(value)
    try:
        yield
    finally:
        _today_override.reset(token)
