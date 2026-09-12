"""
Scoring harness (§8.1). Matches predicted daughters to reference daughters
one-to-one and reports P/R/F1 and geometric error metrics.

Owner: P3.
"""

import argparse


def score_case(pred: dict, ref: dict, thresholds_mm=(3.0, 5.0, 10.0)) -> dict:
    """Score one predicted case against its reference.

    Args:
        pred: parsed prediction JSON (§5.10 schema).
        ref: parsed reference JSON, same schema.
        thresholds_mm: ostium-distance thresholds (mm) at which to report
            matching statistics.

    Returns:
        dict keyed by threshold, each value a dict with TP, FP, FN,
        precision, recall, f1, mean/max ostium distance (mm) over matches,
        mean direction angle error (degrees), mean absolute radius error
        (mm), and seed-on-daughter accuracy. Matching uses
        scipy.optimize.linear_sum_assignment on the pairwise Euclidean
        ostium-distance matrix, rejecting matches beyond the threshold.
    """
    raise NotImplementedError


def main() -> None:
    """CLI entry point: score a directory of predictions against references.

    Supports `--pred`, `--ref`, and `--sweep min_radius` to re-score a
    directory of predictions produced at different config values and print
    F1 against the swept value.
    """
    parser = argparse.ArgumentParser(description="Score branchseed predictions against references.")
    parser.add_argument("--pred", required=True, help="Directory of prediction JSON files.")
    parser.add_argument("--ref", required=True, help="Directory of reference JSON files.")
    parser.add_argument("--sweep", default=None, help="Name of the swept config parameter (e.g. min_radius).")
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
