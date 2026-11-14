
from src.docurecon.completion_rules import (
    select_completion_timestamp,
)


def test_937_selects_part_c():
    sections = {
        "part_c": {
            "date": "2026-11-10",
            "time": "12:42",
            "signature_present": True,
        },
        "physician_signatures": [],
    }

    result = select_completion_timestamp(
        "9.37", sections
    )

    assert result["status"] == "complete"
    assert result["timestamp"] == "2026-11-10T12:42"


def test_939_selects_earliest_signature():
    sections = {
        "physician_signatures": [
            {
                "date": "2026-11-12",
                "time": "22:30",
                "signature_present": True,
            },
            {
                "date": "2026-11-12",
                "time": "22:12",
                "signature_present": True,
            },
        ]
    }

    result = select_completion_timestamp(
        "9.39", sections
    )

    assert result["status"] == "complete"
    assert result["timestamp"] == "2026-11-12T22:12"


def test_missing_part_c_signature():
    sections = {
        "part_c": {
            "date": "2026-11-10",
            "time": "12:42",
            "signature_present": False,
        }
    }

    result = select_completion_timestamp(
        "9.37", sections
    )

    assert result["status"] == "incomplete"
    assert result["timestamp"] is None


def test_939_ignores_unsigned_entries():
    sections = {
        "physician_signatures": [
            {
                "date": "2026-11-12",
                "time": "21:00",
                "signature_present": False,
            },
            {
                "date": "2026-11-12",
                "time": "22:12",
                "signature_present": True,
            },
        ]
    }

    result = select_completion_timestamp(
        "9.39", sections
    )

    assert result["timestamp"] == "2026-11-12T22:12"


def test_unsupported_status():
    result = select_completion_timestamp(
        "9.99", {}
    )

    assert result["status"] == "unsupported"
    assert result["timestamp"] is None
