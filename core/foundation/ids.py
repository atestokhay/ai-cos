"""Centralized UUIDv7 generation. All callers use this module; uuid6 is not imported elsewhere."""

import uuid

import uuid6


def new_uuid7() -> uuid.UUID:
    """Return a new time-ordered UUIDv7 as a standard uuid.UUID."""
    generated = uuid6.uuid7()
    return uuid.UUID(bytes=generated.bytes)
