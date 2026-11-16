
"""
DocuRecon independent exception-detection evaluation.

Compares saved predictions against the 400-case
synthetic ground truth.

Frozen pipeline: v0.3.0-pilot / 2a3ebdd.
Does not rerun or modify DocuRecon.
"""

import csv
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "evaluation_dataset" / "independent_test"

TRUTH = ROOT / "ground_truth" / "case_ground_truth.csv"
RESULTS = ROOT / "results" / "independent_results_400.csv"

OUTPUT = ROOT / "results" / "exception_detection_summary.json"

# Ground-truth variation -> expected engine issue code.
LABELS = {
    "ACK_AE": "APPLICATION_ERROR",
    "ACK_AR": "APPLICATION_REJECTED",
    "DUPLICATE_HL7": "AMBIGUOUS_MULTIPLE_HL7_CANDIDATES",
    "HL7_MRN_DIFFERENT": "MRN_DISAGREEMENT",
    "HL7_TIME_DIFFERENT": "COMPLETION_TIME_MISMATCH_PROVISIONAL",
    "NO_ACK_IN_SAMPLE": "NO_ACK_IN_SUPPLIED_FILES",
    "NO_HL7_IN_SAMPLE": "NO_HL7_CANDIDATE_IN_SUPPLIED_FILES",
}

# A dedicated name-disagreement issue was not observed.
# Report this category separately rather than inventing
# a prediction mapping.
UNSCORED_VARIATIONS = {"HL7_NAME_DIFFERENT"}


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def get_issues(prediction):
    value = prediction.get("issues", "")
    return {
        issue.strip()
        for issue in value.split(";")
        if issue.strip()
    }


def safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def evaluate_label(label, issue_code, joined):
    tp = fp = fn = tn = 0

    false_positive_ids = []
    false_negative_ids = []

    for truth, prediction in joined:
        expected = truth["secondary_variation"] == label
        predicted = issue_code in get_issues(prediction)

        if expected and predicted:
            tp += 1
        elif not expected and predicted:
            fp += 1
            false_positive_ids.append(truth["case_id"])
        elif expected and not predicted:
            fn += 1
            false_negative_ids.append(truth["case_id"])
        else:
            tn += 1

    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    f1 = safe_divide(
        2 * precision * recall,
        precision + recall,
    )

    return {
        "issue_code": issue_code,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_ids": false_positive_ids,
        "false_negative_ids": false_negative_ids,
    }


def main():
    truth = load_csv(TRUTH)
    results = load_csv(RESULTS)

    if len(truth) != 400 or len(results) != 400:
        raise ValueError("Expected 400 truth and result rows")

    truth_by_id = {row["case_id"]: row for row in truth}
    result_by_id = {row["case_id"]: row for row in results}

    if (
        len(truth_by_id) != 400
        or len(result_by_id) != 400
        or set(truth_by_id) != set(result_by_id)
    ):
        raise ValueError("Duplicate or mismatched case IDs")

    joined = [
        (truth_by_id[case_id], result_by_id[case_id])
        for case_id in sorted(truth_by_id)
    ]

    metrics = {
        label: evaluate_label(label, issue, joined)
        for label, issue in LABELS.items()
    }

    total_tp = sum(m["tp"] for m in metrics.values())
    total_fp = sum(m["fp"] for m in metrics.values())
    total_fn = sum(m["fn"] for m in metrics.values())

    micro_precision = safe_divide(
        total_tp, total_tp + total_fp
    )
    micro_recall = safe_divide(
        total_tp, total_tp + total_fn
    )
    micro_f1 = safe_divide(
        2 * micro_precision * micro_recall,
        micro_precision + micro_recall,
    )

    macro_f1 = sum(
        m["f1"] for m in metrics.values()
    ) / len(metrics)

    unscored = {
        variation: [
            truth_row["case_id"]
            for truth_row, _ in joined
            if truth_row["secondary_variation"] == variation
        ]
        for variation in UNSCORED_VARIATIONS
    }

    missing_result_ids = [
        truth_row["case_id"]
        for truth_row, prediction in joined
        if prediction.get("row_count") != "1"
    ]

    output = {
        "evaluation": "Independent synthetic OCR-only",
        "pipeline_commit": "2a3ebdd",
        "total_cases": 400,
        "scoring_unit": "case-by-exception-type",
        "metrics": metrics,
        "micro_average": {
            "tp": total_tp,
            "fp": total_fp,
            "fn": total_fn,
            "precision": round(micro_precision, 4),
            "recall": round(micro_recall, 4),
            "f1": round(micro_f1, 4),
        },
        "macro_f1": round(macro_f1, 4),
        "unscored_variations": unscored,
        "missing_result_ids": missing_result_ids,
        "limitations": [
            "Seven explicitly mapped issue types scored.",
            "HL7_NAME_DIFFERENT is not scored.",
            "Issue-level metrics are not patient-linkage accuracy.",
            "Missing-result cases remain in all denominators.",
            "An issue flag may indicate provisional evidence.",
            "Single-case isolation does not measure cross-case matching."
        ],
    }

    if OUTPUT.exists():
        raise FileExistsError(
            f"Existing results preserved: {OUTPUT}"
        )

    OUTPUT.write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )

    print("\nDOCURECON EXCEPTION DETECTION EVALUATION")
    print("=" * 75)

    print(
        f"{'Variation':32} "
        f"{'TP':>4} {'FP':>4} {'FN':>4} "
        f"{'Precision':>10} {'Recall':>8} {'F1':>8}"
    )

    for label, metric in metrics.items():
        print(
            f"{label:32} "
            f"{metric['tp']:4} "
            f"{metric['fp']:4} "
            f"{metric['fn']:4} "
            f"{metric['precision']:10.3f} "
            f"{metric['recall']:8.3f} "
            f"{metric['f1']:8.3f}"
        )

    print("\nMICRO AVERAGE")
    print("Precision:", round(micro_precision, 4))
    print("Recall:", round(micro_recall, 4))
    print("F1:", round(micro_f1, 4))
    print("Macro F1:", round(macro_f1, 4))

    print("\nNOT SCORED")
    for label, ids in unscored.items():
        print(f"{label}: {len(ids)} cases")

    print("\nMissing result cases:", missing_result_ids)
    print("\nSaved:", OUTPUT)


if __name__ == "__main__":
    main()
