#!/usr/bin/env python3
"""
Branchseed CLI — thin wrapper only. Calls the pipeline stages in order and
always writes a valid JSON output, even on failure.

Usage (exact form required by the brief):
    python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json

Also accepts plain .nii for --image / --aorta-mask.
"""

import argparse
import os
import time
import traceback

import numpy as np
import yaml

from src.io_geom import load_case
from src.intensity import profile_aorta
from src.candidates import candidate_mask
from src.aorta_frame import AortaFrame, build_frame, clock_and_arclen
from src.instances import find_raw_branches
from src.geometry import measure
from src.gate import accept, dedup
from src.report import write_prediction_json


def parse_args() -> argparse.Namespace:
    """Parse the required CLI arguments.

    Returns:
        argparse.Namespace with `image`, `aorta_mask`, `output`, and
        `config` (defaults to config/default.yaml).
    """
    parser = argparse.ArgumentParser(description="Branchseed: detect aortic daughter branches.")
    parser.add_argument("--image", required=True, help="Path to the CT volume (.nii or .nii.gz), HU.")
    parser.add_argument("--aorta-mask", required=True, dest="aorta_mask", help="Path to the binary aorta mask (.nii or .nii.gz).")
    parser.add_argument("--output", required=True, help="Path to write the prediction JSON to.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to the YAML config (default: config/default.yaml).")
    return parser.parse_args()


def load_config(config_path: str) -> dict:
    """Load the YAML config used by every pipeline stage.

    Args:
        config_path: path to a YAML file (see config/default.yaml).

    Returns:
        dict of config values. No numeric literal may be used in src/
        outside of this dict.
    """
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _local_tangent(frame: AortaFrame, xyz_mm: np.ndarray) -> np.ndarray:
    """Unit tangent of the aortic centreline nearest a given physical point.

    Args:
        frame: `AortaFrame` from `aorta_frame.build_frame`.
        xyz_mm: physical point (x, y, z) in mm (typically a branch ostium).

    Returns:
        np.ndarray, shape (3,), unit vector along `frame.centreline_mm`
        (superior -> inferior ordering) at the point nearest `xyz_mm`, via a
        local finite difference. Zero vector if the centreline has fewer
        than two points or the local segment is degenerate.
    """
    centre = frame.centreline_mm
    if centre.shape[0] < 2:
        return np.zeros(3)
    idx = int(np.argmin(np.linalg.norm(centre - xyz_mm[np.newaxis, :], axis=1)))
    lo = max(idx - 1, 0)
    hi = min(idx + 1, centre.shape[0] - 1)
    tangent = centre[hi] - centre[lo]
    norm = np.linalg.norm(tangent)
    return tangent / norm if norm > 1e-9 else np.zeros(3)


def _takeoff_angle_deg(direction: np.ndarray, tangent: np.ndarray) -> float:
    """Angle in degrees between a branch direction and the local aortic axis."""
    norm_d = np.linalg.norm(direction)
    norm_t = np.linalg.norm(tangent)
    if norm_d < 1e-9 or norm_t < 1e-9:
        return float("nan")
    cos_t = float(np.clip(np.dot(direction, tangent) / (norm_d * norm_t), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_t)))


def empty_result(case_id: str, warnings: list) -> dict:
    """Build the minimal valid prediction JSON payload (no detections).

    Args:
        case_id: identifier for the case (derived from the input filename
            when the pipeline fails before a `Case` is available).
        warnings: list of str, human-readable failure descriptions.

    Returns:
        dict matching the required schema, with an empty `daughters` list
        and an empty `excluded_candidates` list, per §5.9 ("wrap every case
        in a try/except that, on any failure, still writes a valid file
        with an empty daughters list and a warnings field").
    """
    return {
        "case_id": case_id,
        "parent": {"instance_id": "aorta"},
        "daughters": [],
        "excluded_candidates": [],
        "meta": {"runtime_s": 0.0, "a_med_hu": None, "t_vessel_hu": None, "warnings": warnings},
    }


def run_case(image_path: str, mask_path: str, cfg: dict) -> dict:
    """Run the full pipeline (stages 1-9) on one case.

    Args:
        image_path: path to the CT volume.
        mask_path: path to the binary aorta mask.
        cfg: parsed config dict.

    Returns:
        dict matching the required prediction schema (§5.10). Never raises;
        any internal failure is caught and converted into `empty_result`
        with a populated `warnings` list, so the CLI always writes valid
        output.
    """
    t0 = time.time()
    warnings = []
    case_id = os.path.basename(os.path.dirname(image_path)) or image_path.split("/")[-1].split(".")[0]
    try:
        case = load_case(image_path, mask_path, cfg)
        case_id = case.case_id

        profile = profile_aorta(case, cfg)
        cand = candidate_mask(case, profile, cfg)
        frame = build_frame(case, cfg)
        raw_branches = find_raw_branches(case, cand, frame, profile, cfg)

        accepted = []
        for raw in raw_branches:
            # A single degenerate candidate (e.g. too few voxels for the
            # MCP path solver to find any route to its own extent target)
            # must never crash the whole case -- log it as a rejection and
            # keep processing every other candidate.
            try:
                geom = measure(case, raw, frame, profile, cfg)
            except Exception as exc:  # noqa: BLE001 - per-candidate robustness
                if cfg.get("log_rejections"):
                    warnings.append(f"rejected: measure_failed ({exc})")
                continue
            keep, reason = accept(raw, geom, profile, cfg)
            if keep:
                accepted.append((raw, geom))
            elif cfg.get("log_rejections"):
                warnings.append(f"rejected: {reason}")

        accepted = dedup(accepted, cfg)

        daughters = []
        for i, (raw, geom) in enumerate(accepted):
            clock_hours, arclen_mm = clock_and_arclen(frame, geom.ostium_mm)
            tangent = _local_tangent(frame, geom.ostium_mm)
            takeoff_deg = _takeoff_angle_deg(geom.direction, tangent)
            daughters.append(
                {
                    "instance_id": f"branch_{i + 1:03d}",
                    "parent_instance_id": "aorta",
                    "ostium_xyz_mm": geom.ostium_mm.tolist(),
                    "seed_xyz_mm": geom.seed_mm.tolist(),
                    "radius_mm": float(geom.radius_mm),
                    "direction_xyz": geom.direction.tolist(),
                    "confidence": 1.0,
                    "clock_position": float(clock_hours),
                    "arclen_from_top_mm": float(arclen_mm),
                    "takeoff_angle_deg": takeoff_deg,
                }
            )

        return {
            "case_id": case_id,
            "parent": {"instance_id": "aorta"},
            "daughters": daughters,
            "excluded_candidates": frame.excluded,
            "meta": {
                "runtime_s": time.time() - t0,
                "a_med_hu": profile.a_med,
                "t_vessel_hu": profile.t_vessel,
                "warnings": warnings,
            },
        }
    except Exception:  # noqa: BLE001 - per-case robustness is a hard requirement
        warnings.append(traceback.format_exc())
        result = empty_result(case_id, warnings)
        result["meta"]["runtime_s"] = time.time() - t0
        return result


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    result = run_case(args.image, args.aorta_mask, cfg)
    write_prediction_json(
        result["case_id"], result["daughters"], result["excluded_candidates"], result["meta"], args.output,
    )


if __name__ == "__main__":
    main()
