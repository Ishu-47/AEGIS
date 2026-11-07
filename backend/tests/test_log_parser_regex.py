"""Regression tests for the timestamp + severity plain-text log format."""
import re

PATTERN = re.compile(
    r"^\s*(?P<timestamp>(?:\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\S+))\s+"
    r"(?P<severity>DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL)"
    r"\s+(?P<service>[\w.$-]+)\s*[-:]\s*"
    r"(?P<message>.*)$", re.IGNORECASE)


def test_space_separated_timestamp():
    m = PATTERN.match("2026-10-30 10:00:03 ERROR auth_service.api - Login request failed with status 500")
    assert m and m.group("timestamp") == "2026-10-30 10:00:03"
    assert m.group("service") == "auth_service.api"
    assert m.group("message") == "Login request failed with status 500"


def test_iso_timestamp_with_timezone_and_fraction():
    m = PATTERN.match("2026-10-30T10:00:03.217+00:00 ERROR api - failure")
    assert m and m.group("timestamp") == "2026-10-30T10:00:03.217+00:00"
