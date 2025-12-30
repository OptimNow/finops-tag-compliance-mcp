"""Enumerations for violation types and severity levels."""

from enum import Enum


class ViolationType(str, Enum):
    """Types of tagging policy violations."""

    MISSING_REQUIRED_TAG = "missing_required_tag"
    INVALID_VALUE = "invalid_value"
    INVALID_FORMAT = "invalid_format"


class Severity(str, Enum):
    """Severity levels for violations."""

    ERROR = "error"
    WARNING = "warning"
