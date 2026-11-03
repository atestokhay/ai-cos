"""UUIDv7 generation: time-ordering and DB compatibility."""

import uuid

from core.model_router.domain.ids import new_uuid7


def test_returns_standard_uuid() -> None:
    result = new_uuid7()
    assert isinstance(result, uuid.UUID)


def test_version_is_7() -> None:
    result = new_uuid7()
    assert result.version == 7


def test_time_ordered() -> None:
    ids = [new_uuid7() for _ in range(20)]
    # UUIDv7 encodes a millisecond timestamp; sequential calls should be non-decreasing.
    as_ints = [u.int for u in ids]
    assert as_ints == sorted(as_ints)


def test_string_round_trip() -> None:
    uid = new_uuid7()
    assert uuid.UUID(str(uid)) == uid


def test_bytes_round_trip() -> None:
    uid = new_uuid7()
    assert uuid.UUID(bytes=uid.bytes) == uid


def test_uniqueness() -> None:
    ids = {new_uuid7() for _ in range(100)}
    assert len(ids) == 100
