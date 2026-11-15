
"""Tests for synthetic MRN extraction patterns."""

import pytest

from docurecon.parsers.paperwork_parser import MRN_RE


@pytest.mark.parametrize(
    "text, expected",
    [
        ("MRN: SYN-939-001", "SYN-939-001"),
        ("MRN: SYN-937-002", "SYN-937-002"),
        ("MRN\nSYN-PILOT-0001", "SYN-PILOT-0001"),
        ("MRN\nSYN-PILOT-0006", "SYN-PILOT-0006"),
        ("No synthetic identifier", None),
    ],
)
def test_synthetic_mrn_patterns(text, expected):
    match = MRN_RE.search(text)

    actual = match.group(0) if match else None

    assert actual == expected
