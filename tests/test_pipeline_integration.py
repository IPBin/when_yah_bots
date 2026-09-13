"""End-to-end coordinate-system regression test (checklist: "Physical
coordinate system preserved and verified on anisotropic + rotated
phantoms"). `test_phantom.py` only checks the phantom generator's own
reference geometry; this drives real files through the full
`run.run_case` pipeline -- disk I/O, resample, crop, every module boundary
-- on both an identity grid and an anisotropic + rotated grid, and checks
that whatever ostia the pipeline does report land close (in mm) to the true
reference ostium, with no accuracy gap between the two grids. Detection
recall/count is not asserted here -- that is the detector's job
(`src/instances.py`, `src/gate.py`), not the coordinate system's.

Owner: P2.
"""

import numpy as np
import SimpleITK as sitk
import yaml

from eval.phantom import make_phantom
from run import run_case

BRANCHES = [
    {"theta_deg": 90.0, "arclen_mm": 60.0, "direction_xyz": (0.0, -1.0, 0.05), "radius_mm": 3.5, "length_mm": 15.0},
    {"theta_deg": 0.0, "arclen_mm": 80.0, "direction_xyz": (1.0, 0.0, -0.1), "radius_mm": 2.5, "length_mm": 12.0},
]

OSTIUM_TOL_MM = 3.0
ANGLE_TOL_DEG = 30.0


def _cfg():
    with open("config/default.yaml") as f:
        return yaml.safe_load(f)


def _run_phantom_case(tmp_path, spacing, direction, shape):
    """Write a phantom to real NIfTI files and run it through `run.run_case`,
    exactly as the CLI would for a real case."""
    ct, mask, ref = make_phantom(BRANCHES, spacing=spacing, direction=direction, shape=shape)
    image_path = str(tmp_path / "orig.nii.gz")
    mask_path = str(tmp_path / "mask.nii.gz")
    sitk.WriteImage(ct, image_path)
    sitk.WriteImage(mask, mask_path)
    result = run_case(image_path, mask_path, _cfg())
    return result, ref


def _assert_ostia_and_directions_close(daughters, ref_daughters):
    assert daughters, "expected at least one detection on a well-formed phantom"
    for d in daughters:
        ref = min(
            ref_daughters,
            key=lambda r: np.linalg.norm(np.asarray(r["ostium_xyz_mm"]) - np.asarray(d["ostium_xyz_mm"])),
        )
        dist_mm = float(np.linalg.norm(np.asarray(ref["ostium_xyz_mm"]) - np.asarray(d["ostium_xyz_mm"])))
        assert dist_mm < OSTIUM_TOL_MM, f"ostium off by {dist_mm:.2f} mm"

        cos = np.clip(np.dot(d["direction_xyz"], ref["direction_xyz"]), -1.0, 1.0)
        angle_deg = float(np.degrees(np.arccos(cos)))
        assert angle_deg < ANGLE_TOL_DEG, f"direction off by {angle_deg:.1f} deg"


def test_pipeline_ostia_correct_on_identity_grid(tmp_path):
    result, ref = _run_phantom_case(tmp_path, spacing=(1.0, 1.0, 1.0), direction=None, shape=(160, 160, 160))
    _assert_ostia_and_directions_close(result["daughters"], ref["daughters"])


def test_pipeline_ostia_correct_on_anisotropic_rotated_grid(tmp_path):
    theta = np.deg2rad(20.0)
    direction = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    result, ref = _run_phantom_case(
        tmp_path, spacing=(0.7, 0.7, 2.0), direction=direction.flatten().tolist(), shape=(140, 140, 100)
    )
    _assert_ostia_and_directions_close(result["daughters"], ref["daughters"])
