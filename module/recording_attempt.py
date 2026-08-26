"""Shared result contract for one platform recording attempt."""
from __future__ import annotations

from enum import Enum


class RecorderAttemptOutcome(str, Enum):
    COMPLETED = "completed"
    OFFLINE = "offline"
    RETRYABLE_ERROR = "retryable_error"
    USER_STOPPED = "user_stopped"
    DISABLED = "disabled"
    FATAL_ERROR = "fatal_error"
