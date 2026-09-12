"""
Scoring harness (§8.1). Matches predicted daughters to reference daughters
one-to-one and reports P/R/F1 and geometric error metrics.

Owner: P3.
"""

import argparse
import glob
import json
import os

import numpy as np
from scipy.optimize import linear_sum_assignment

THRESHOLDS_MM = (3.0, 5.0, 10.0)


def _ostium_matrix(pred_daughters, ref_daughters):
    """Pairwise Euclidean ostium distance matrix, in mm.

    Args:
        pred_daughters: list of prediction daughter dicts (ostium_xyz_mm).
        ref_daughters: list of reference daughter dicts (ostium_xyz_mm).

    Returns:
        np.ndarray (len(pred), len(ref)) of Euclidean distances in mm.
    """
    if not pred_daughters or not ref_daughters:
        return np.zeros((len(pred_daughters), len(ref_daughters)))
    p = np.array([d["ostium_xyz_mm"] for d in pred_daughters], dtype=float)
    r = np.array([d["ostium_xyz_mm"] for d in ref_daughters], dtype=float)
    return np.linalg.norm(p[:, None, :] - r[None, :, :], axis=-1)


def _direction_angle_deg(a, b):
    """Angle in degrees between two 3-vectors (need not be unit length)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return float("nan")
    cos_t = np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_t)))


def _seed_on_daughter(pred_seed_mm, ref_seed_mm, ref_radius_mm):
    """True if the predicted seed lies within the reference radius of the
    reference seed (a stand-in, on point references, for "lies on the
    matched daughter's proximal centreline")."""
    dist = float(np.linalg.norm(np.asarray(pred_seed_mm) - np.asarray(ref_seed_mm)))
    return dist <= float(ref_radius_mm)


def score_case(pred: dict, ref: dict, thresholds_mm=THRESHOLDS_MM) -> dict:
    """Score one predicted case against its reference.

    Args:
        pred: parsed prediction JSON (§5.10 schema).
        ref: parsed reference JSON, same schema.
        thresholds_mm: ostium-distance thresholds (mm) at which to report
            matching statistics.

    Returns:
        dict keyed by threshold (mm, as float), each value a dict with TP,
        FP, FN, precision, recall, f1, mean/max ostium distance (mm) over
        matches, mean direction angle error (degrees), mean absolute radius
        error (mm), and seed-on-daughter accuracy (fraction of matches).
        Matching uses scipy.optimize.linear_sum_assignment on the pairwise
        Euclidean ostium-distance matrix, rejecting matches beyond the
        threshold.
    """
    pred_d = pred.get("daughters", [])
    ref_d = ref.get("daughters", [])
    dist_matrix = _ostium_matrix(pred_d, ref_d)

    results = {}
    for thr in thresholds_mm:
        n_pred, n_ref = len(pred_d), len(ref_d)

        if n_pred > 0 and n_ref > 0:
            row_ind, col_ind = linear_sum_assignment(dist_matrix)
            matches = [
                (i, j) for i, j in zip(row_ind, col_ind) if dist_matrix[i, j] <= thr
            ]
        else:
            matches = []

        tp = len(matches)
        fp = n_pred - tp
        fn = n_ref - tp
        precision = tp / n_pred if n_pred else 0.0
        recall = tp / n_ref if n_ref else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        ost_dists = [float(dist_matrix[i, j]) for i, j in matches]
        angle_errs = [
            _direction_angle_deg(pred_d[i]["direction_xyz"], ref_d[j]["direction_xyz"])
            for i, j in matches
        ]
        radius_errs = [
            abs(float(pred_d[i]["radius_mm"]) - float(ref_d[j]["radius_mm"]))
            for i, j in matches
        ]
        seed_hits = [
            _seed_on_daughter(pred_d[i]["seed_xyz_mm"], ref_d[j]["seed_xyz_mm"], ref_d[j]["radius_mm"])
            for i, j in matches
        ]

        results[thr] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "ost_mean_mm": float(np.mean(ost_dists)) if ost_dists else float("nan"),
            "ost_max_mm": float(np.max(ost_dists)) if ost_dists else float("nan"),
            "angle_mean_deg": float(np.nanmean(angle_errs)) if angle_errs else float("nan"),
            "radius_mean_err_mm": float(np.mean(radius_errs)) if radius_errs else float("nan"),
            "seed_on_daughter_frac": float(np.mean(seed_hits)) if seed_hits else float("nan"),
        }

    return results


def _aggregate(per_case: dict, thr: float, key: str, kind: str):
    """Aggregate one metric across cases, micro (pooled) or macro (mean)."""
    if kind == "micro":
        tp = sum(v[thr]["tp"] for v in per_case.values())
        fp = sum(v[thr]["fp"] for v in per_case.values())
        fn = sum(v[thr]["fn"] for v in per_case.values())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}
    values = [v[thr][key] for v in per_case.values()]
    return float(np.mean(values)) if values else float("nan")


def _load_json_dir(path: str) -> dict:
    """Load every *.json file in `path` into a dict keyed by case_id."""
    out = {}
    for fp in sorted(glob.glob(os.path.join(path, "*.json"))):
        with open(fp, "r") as f:
            data = json.load(f)
        case_id = data.get("case_id", os.path.splitext(os.path.basename(fp))[0])
        out[case_id] = data
    return out


def score_directory(pred_dir: str, ref_dir: str, thresholds_mm=THRESHOLDS_MM) -> dict:
    """Score every case with both a prediction and a reference JSON.

    Args:
        pred_dir: directory of prediction JSON files (§5.10 schema).
        ref_dir: directory of reference JSON files, same schema.
        thresholds_mm: ostium-distance thresholds (mm).

    Returns:
        dict with "per_case" (case_id -> score_case output) and "summary"
        (threshold -> {"micro": {...}, "macro": {...}}).
    """
    preds = _load_json_dir(pred_dir)
    refs = _load_json_dir(ref_dir)
    case_ids = sorted(set(preds) & set(refs))

    per_case = {cid: score_case(preds[cid], refs[cid], thresholds_mm) for cid in case_ids}

    summary = {}
    for thr in thresholds_mm:
        summary[thr] = {
            "micro": _aggregate(per_case, thr, None, "micro"),
            "macro": {
                "f1": _aggregate(per_case, thr, "f1", "macro"),
                "precision": _aggregate(per_case, thr, "precision", "macro"),
                "recall": _aggregate(per_case, thr, "recall", "macro"),
                "ost_mean_mm": _aggregate(per_case, thr, "ost_mean_mm", "macro"),
                "angle_mean_deg": _aggregate(per_case, thr, "angle_mean_deg", "macro"),
                "radius_mean_err_mm": _aggregate(per_case, thr, "radius_mean_err_mm", "macro"),
            },
        }

    return {"per_case": per_case, "summary": summary}


def _print_table(result: dict, thresholds_mm=THRESHOLDS_MM) -> None:
    """Print the per-case table plus a summary row, at each threshold."""
    for thr in thresholds_mm:
        print(f"\n=== ostium match threshold: {thr:g} mm ===")
        header = f"{'case':<20}{'n_ref':>6}{'n_pred':>7}{'TP':>4}{'FP':>4}{'FN':>4}{'prec':>7}{'recall':>8}{'F1':>7}{'ost_mm':>9}{'ang_deg':>9}{'dr_mm':>8}"
        print(header)
        for case_id, scores in result["per_case"].items():
            s = scores[thr]
            print(
                f"{case_id:<20}{s['tp'] + s['fn']:>6}{s['tp'] + s['fp']:>7}{s['tp']:>4}{s['fp']:>4}{s['fn']:>4}"
                f"{s['precision']:>7.2f}{s['recall']:>8.2f}{s['f1']:>7.2f}"
                f"{s['ost_mean_mm']:>9.2f}{s['angle_mean_deg']:>9.1f}{s['radius_mean_err_mm']:>8.2f}"
            )
        micro = result["summary"][thr]["micro"]
        macro = result["summary"][thr]["macro"]
        print(
            f"{'MICRO':<20}{'':>6}{'':>7}{micro['tp']:>4}{micro['fp']:>4}{micro['fn']:>4}"
            f"{micro['precision']:>7.2f}{micro['recall']:>8.2f}{micro['f1']:>7.2f}"
        )
        print(f"{'MACRO':<20}{'':>6}{'':>7}{'':>4}{'':>4}{'':>4}{macro['precision']:>7.2f}{macro['recall']:>8.2f}{macro['f1']:>7.2f}")


def _sweep(pred_root: str, ref_dir: str, param_name: str, thresholds_mm=THRESHOLDS_MM) -> None:
    """Re-score every `pred_root/<value>/` subdirectory and print F1 vs value.

    Args:
        pred_root: directory containing one subdirectory of predictions per
            swept config value (subdirectory names are the swept values,
            e.g. "0.5", "0.8", "1.2").
        ref_dir: directory of reference JSON files.
        param_name: name of the swept parameter, for the printed header.
    """
    print(f"\n=== sweep: {param_name} ===")
    print(f"{param_name:>12}" + "".join(f"{thr:>10.0f}mm" for thr in thresholds_mm))
    for entry in sorted(os.listdir(pred_root)):
        sub = os.path.join(pred_root, entry)
        if not os.path.isdir(sub):
            continue
        result = score_directory(sub, ref_dir, thresholds_mm)
        row = f"{entry:>12}"
        for thr in thresholds_mm:
            row += f"{result['summary'][thr]['micro']['f1']:>12.3f}"
        print(row)


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
    args = parser.parse_args()

    if args.sweep:
        _sweep(args.pred, args.ref, args.sweep)
    else:
        result = score_directory(args.pred, args.ref)
        _print_table(result)


if __name__ == "__main__":
    main()
