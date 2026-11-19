
from datetime import date
from pathlib import Path
from unittest.mock import patch

from docurecon.reconciliation.daily_engine import run_daily


ROOT = Path(__file__).resolve().parents[1] / "sample_data"
DAY = date(2028, 3, 21)


def paper(name, completion_date):
    return {
        "source": f"{name}.pdf",
        "patient_name": name,
        "mrn": "SYN-002-001",
        "form_type": "9.37",
        "completion_date": completion_date,
        "completion_time": "08:00",
        "review_reasons": [],
    }


def run_mock(papers):
    with (
        patch(
            "docurecon.reconciliation.daily_engine.extract_folder",
            return_value=(papers, []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_hl7_folder",
            return_value=([], []),
        ),
        patch(
            "docurecon.reconciliation.daily_engine.parse_ack_folder",
            return_value=([], []),
        ),
    ):
        return run_daily(ROOT, DAY)


def test_daily_rows_exclude_unassigned_paperwork():
    result = run_mock([
        paper("SELECTED", "2028-03-21"),
        paper("UNASSIGNED", ""),
    ])

    assert result["paperwork_count"] == 1
    assert len(result["daily_rows"]) == 1
    assert len(result["unassigned_paperwork"]) == 1

    assert (
        result["daily_rows"][0]["paperwork_file"]
        == "SELECTED.pdf"
    )

    # Original output must remain backward compatible.
    assert len(result["rows"]) == 2


def test_unassigned_count_is_separate():
    result = run_mock([
        paper("UNKNOWN_A", ""),
        paper("UNKNOWN_B", ""),
    ])

    assert result["paperwork_count"] == 0
    assert result["daily_rows"] == []
    assert result["unassigned_paperwork_count"] == 2

    assert all(
        record["review_required"]
        for record in result["unassigned_paperwork"]
    )


def test_other_date_is_not_unassigned():
    result = run_mock([
        paper("OTHER_DATE", "2028-03-22"),
    ])

    assert result["paperwork_count"] == 0
    assert result["daily_rows"] == []
    assert result["unassigned_paperwork"] == []
    assert result["rows"] == []
