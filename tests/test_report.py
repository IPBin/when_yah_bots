"""Smoke tests for the visual checks and unrolled map (playbook §9.1, §9.2):
must render without crashing, including with zero detections.

`clock_and_arclen` is monkeypatched because `aorta_frame.build_frame` is
owned by P1 and not yet implemented; these tests only exercise report.py.
"""

import numpy as np
import SimpleITK as sitk
import yaml

import src.report as report
from eval.phantom import make_phantom
from src.io_geom import Case

CFG_PATH = "config/default.yaml"

BRANCHES = [
    {"theta_deg": 90.0, "arclen_mm": 30.0, "direction_xyz": (0.0, -1.0, 0.05), "radius_mm": 3.5, "length_mm": 15.0},
    {"theta_deg": 0.0, "arclen_mm": 45.0, "direction_xyz": (1.0, 0.0, -0.1), "radius_mm": 2.5, "length_mm": 12.0},
]


def _fake_clock_and_arclen(frame, xyz_mm):
    xyz_mm = np.asarray(xyz_mm)
    cx, cy = 29.5, 29.5
    theta = np.degrees(np.arctan2(xyz_mm[1] - cy, xyz_mm[0] - cx))
    clock = (90.0 - theta) / 30.0 % 12.0
    return clock, float(xyz_mm[2])


def _make_case_and_ref():
    ct, mask, ref = make_phantom(BRANCHES, shape=(60, 60, 80))
    case = Case(
        ct=ct,
        aorta=mask,
        ct_np=sitk.GetArrayFromImage(ct).astype(np.float32),
        aorta_np=sitk.GetArrayFromImage(mask).astype(bool),
        case_id="phantom",
    )
    return case, ref


def _cfg():
    with open(CFG_PATH) as f:
        return yaml.safe_load(f)


def test_visual_check_renders_with_detections(tmp_path, monkeypatch):
    case, ref = _make_case_and_ref()
    out = tmp_path / "visual.png"
    report.visual_check(case, object(), ref["daughters"], str(out), _cfg())
    assert out.exists() and out.stat().st_size > 0


def test_visual_check_renders_with_zero_detections(tmp_path):
    case, _ = _make_case_and_ref()
    out = tmp_path / "visual_empty.png"
    report.visual_check(case, object(), [], str(out), _cfg())
    assert out.exists() and out.stat().st_size > 0


def test_unrolled_map_renders_with_detections_and_excluded(tmp_path, monkeypatch):
    case, ref = _make_case_and_ref()
    monkeypatch.setattr(report, "clock_and_arclen", _fake_clock_and_arclen)
    excluded = [{"reason": "superior_end_cap", "ostium_xyz_mm": [29.5, 39.5, 1.0]}]
    out = tmp_path / "unrolled.png"
    report.unrolled_map(case, object(), ref["daughters"], excluded, str(out), _cfg())
    assert out.exists() and out.stat().st_size > 0


def test_unrolled_map_renders_with_zero_detections(tmp_path, monkeypatch):
    case, _ = _make_case_and_ref()
    monkeypatch.setattr(report, "clock_and_arclen", _fake_clock_and_arclen)
    out = tmp_path / "unrolled_empty.png"
    report.unrolled_map(case, object(), [], [], str(out), _cfg())
    assert out.exists() and out.stat().st_size > 0
