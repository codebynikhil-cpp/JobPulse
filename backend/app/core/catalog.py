from enum import StrEnum


class SourceType(StrEnum):
    """Persisted classification only; never an adapter-availability declaration."""

    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    API = "api"
    CUSTOM = "custom"
