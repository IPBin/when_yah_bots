"""
Batch runner (§5.9, §6). Runs the full pipeline over every case in a data
directory, writes predictions, a runtime/memory CSV, and validates schema.
Never lets one case's failure stop the batch.

Owner: P1 + P2.
"""

import argparse
import csv
import glob
import math
import os
import re
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run import load_config, run_case  # noqa: E402  (path fix-up above must run first)
from src.report import write_prediction_json  # noqa: E402

_ORIG_RE = re.compile(r"^orig(\w+)\.nii(\.gz)?$")


def _discover_cases(data_dir: str) -> list:
    """Find every (case_id, image_path, mask_path) triple under `data_dir`.

    Args:
        data_dir: root directory to search. Supports the brief's nested
            layout (`subjectNNN/origN.nii` + `subjectNNN/maskN.nii`) and a
            flat layout (`origN.nii[.gz]` + `maskN.nii[.gz]` directly in
            `data_dir`), matched by pairing each `orig*` file with a
            `mask*` file sharing the same suffix in the same folder.

    Returns:
        list of (case_id: str, image_path: str, mask_path: str), sorted by
        image_path. Files with no matching mask are skipped.
    """
    root = os.path.normpath(data_dir)
    cases = []
    for image_path in sorted(glob.glob(os.path.join(data_dir, "**", "orig*.nii*"), recursive=True)):
        base = os.path.basename(image_path)
        match = _ORIG_RE.match(base)
        if not match:
            continue
        suffix = match.group(1)
        folder = os.path.dirname(image_path)
        mask_path = None
        for ext in (".nii.gz", ".nii"):
            candidate = os.path.join(folder, f"mask{suffix}{ext}")
            if os.path.exists(candidate):
                mask_path = candidate
                break
        if mask_path is None:
            continue
        case_id = os.path.basename(folder) if os.path.normpath(folder) != root else f"subject{suffix}"
        cases.append((case_id, image_path, mask_path))
    return cases


def validate_schema(prediction: dict) -> list:
    """Validate a prediction dict against the required output schema.

    Args:
        prediction: parsed prediction JSON (§5.10).

    Returns:
        list of str, one per schema violation found (empty list if valid).
        Checks: unique instance_id values, parent_instance_id == "aorta" on
        every daughter, unit-length direction_xyz vectors, three finite
        coordinates in ostium_xyz_mm / seed_xyz_mm.
    """
    errors = []
    daughters = prediction.get("daughters", [])

    ids = [d.get("instance_id") for d in daughters]
    if len(ids) != len(set(ids)):
        errors.append("duplicate instance_id values among daughters")

    for d in daughters:
        label = d.get("instance_id", "<missing instance_id>")

        if d.get("parent_instance_id") != "aorta":
            errors.append(f"{label}: parent_instance_id is not 'aorta'")

        for key in ("ostium_xyz_mm", "seed_xyz_mm"):
            point = d.get(key)
            valid = (
                isinstance(point, (list, tuple))
                and len(point) == 3
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in point)
            )
            if not valid:
                errors.append(f"{label}: {key} is not three finite coordinates")

        direction = d.get("direction_xyz")
        if (
            isinstance(direction, (list, tuple))
            and len(direction) == 3
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in direction)
        ):
            norm = math.sqrt(sum(v * v for v in direction))
            if not math.isclose(norm, 1.0, abs_tol=1e-3):
                errors.append(f"{label}: direction_xyz is not unit length (norm={norm:.4f})")
        else:
            errors.append(f"{label}: direction_xyz is not a finite 3-vector")

    return errors


def _run_one_case(case_id: str, image_path: str, mask_path: str, cfg: dict) -> tuple:
    """Run one case with wall-clock timing and peak-memory tracking.

    Args:
        case_id: identifier used only for warnings if `run_case` itself
            raises before producing its own `case_id`.
        image_path: path to the CT volume.
        mask_path: path to the binary aorta mask.
        cfg: parsed config dict.

    Returns:
        (prediction: dict, peak_memory_mb: float, schema_errors: list of
        str). `prediction` is always a valid schema dict: `run_case` already
        catches its own internal failures, and any exception escaping it
        here is converted into an empty-daughters result so one case can
        never stop the batch. `peak_memory_mb` is Python-heap peak via
        `tracemalloc` (a lower bound on true RSS, since it does not see
        memory allocated by SimpleITK/numpy's native extensions).
    """
    tracemalloc.start()
    try:
        prediction = run_case(image_path, mask_path, cfg)
    except Exception as exc:  # noqa: BLE001 - one case must never stop the batch
        prediction = {
            "case_id": case_id,
            "parent": {"instance_id": "aorta"},
            "daughters": [],
            "excluded_candidates": [],
            "meta": {"runtime_s": 0.0, "a_med_hu": None, "t_vessel_hu": None, "warnings": [repr(exc)]},
        }
    finally:
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    schema_errors = validate_schema(prediction)
    if schema_errors:
        prediction.setdefault("meta", {}).setdefault("warnings", []).extend(
            f"schema: {e}" for e in schema_errors
        )
    return prediction, peak_bytes / (1024.0 * 1024.0), schema_errors


def main() -> None:
    """CLI entry point: run the pipeline over every case in a data directory.

    Walks `--data` for `subjectNNN/` folders, runs `run.run_case` on each,
    writes one prediction JSON per case under `--out`, plus a CSV of
    per-case runtime, peak memory, branch count and derived thresholds.
    """
    parser = argparse.ArgumentParser(description="Run branchseed over a directory of cases.")
    parser.add_argument("--data", required=True, help="Directory containing subjectNNN/ case folders.")
    parser.add_argument("--out", required=True, help="Directory to write prediction JSON + CSV to.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to the YAML config.")
    args = parser.parse_args()

    cfg = load_config(args.config)
    os.makedirs(args.out, exist_ok=True)

    cases = _discover_cases(args.data)
    if not cases:
        print(f"No cases found under {args.data!r} (expected orig*/mask* pairs).")

    rows = []
    for case_id, image_path, mask_path in cases:
        t0 = time.time()
        prediction, peak_mb, schema_errors = _run_one_case(case_id, image_path, mask_path, cfg)
        wall_s = time.time() - t0

        out_case_id = prediction.get("case_id", case_id)
        out_path = os.path.join(args.out, f"{out_case_id}.json")
        write_prediction_json(
            out_case_id,
            prediction.get("daughters", []),
            prediction.get("excluded_candidates", []),
            prediction.get("meta", {}),
            out_path,
        )

        n_daughters = len(prediction.get("daughters", []))
        n_excluded = len(prediction.get("excluded_candidates", []))
        n_warnings = len(prediction.get("meta", {}).get("warnings", []))
        status = "OK" if not schema_errors else "SCHEMA_ERROR"
        print(
            f"[{status}] {out_case_id}: {n_daughters} daughters, "
            f"{wall_s:.1f}s, {peak_mb:.0f} MB peak, {n_warnings} warnings"
        )

        rows.append(
            {
                "case_id": out_case_id,
                "runtime_s": f"{prediction.get('meta', {}).get('runtime_s', wall_s):.3f}",
                "wall_s": f"{wall_s:.3f}",
                "peak_memory_mb": f"{peak_mb:.1f}",
                "n_daughters": n_daughters,
                "n_excluded_candidates": n_excluded,
                "n_warnings": n_warnings,
                "n_schema_errors": len(schema_errors),
                "min_radius_mm": cfg.get("min_radius_mm"),
            }
        )

    summary_path = os.path.join(args.out, "batch_summary.csv")
    fieldnames = [
        "case_id", "runtime_s", "wall_s", "peak_memory_mb", "n_daughters",
        "n_excluded_candidates", "n_warnings", "n_schema_errors", "min_radius_mm",
    ]
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} prediction(s) and {summary_path}")


if __name__ == "__main__":
    main()
