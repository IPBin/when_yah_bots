"""Tests for src/aorta_frame.py (§10.6 prompt 4).

Built against a synthetic vertical-cylinder aorta rather than real data: at
build time P2's loader hadn't landed yet, so this exercises `build_frame`,
`outward_normal` and `clock_and_arclen` -- especially the §5.5 forbidden
surface -- against a hand-built numpy volume. Swap in `io_geom.load_case`
once real cases are available; the `Case` contract is identical either way.
"""

import numpy as np
import SimpleITK as sitk
import yaml

from src.io_geom import Case
from src.aorta_frame import build_frame, outward_normal, clock_and_arclen


def _load_cfg():
    with open("config/default.yaml") as f:
        return yaml.safe_load(f)


def _cylinder_case(nx=100, ny=100, nz=200, radius_vox=15, spacing=(1.0, 1.0, 1.0)):
    """A vertical tube of ones: aorta_np True inside a cylinder of the given
    radius, spanning the full z extent -- i.e. both flat cropped ends are
    present, exactly like a real aorta mask cropped to its bounding box."""
    _, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    cy, cx = ny / 2.0, nx / 2.0
    aorta_np = ((yy - cy) ** 2 + (xx - cx) ** 2) <= radius_vox ** 2
    ct_np = np.where(aorta_np, 350.0, 40.0).astype(np.float32)

    ct = sitk.GetImageFromArray(ct_np)
    ct.SetSpacing(spacing)
    aorta = sitk.GetImageFromArray(aorta_np.astype(np.uint8))
    aorta.CopyInformation(ct)
    aorta = sitk.Cast(aorta, sitk.sitkUInt8)

    return Case(ct=ct, aorta=aorta, ct_np=ct_np, aorta_np=aorta_np, case_id="cylinder")


def test_wall_and_legal_wall_shapes():
    cfg = _load_cfg()
    case = _cylinder_case()
    frame = build_frame(case, cfg)

    assert frame.wall_np.shape == case.aorta_np.shape
    assert frame.legal_wall_np.shape == case.aorta_np.shape
    assert frame.wall_np.any()
    assert frame.legal_wall_np.any()
    # legal wall must always be a subset of the full wall
    assert not (frame.legal_wall_np & ~frame.wall_np).any()


def test_end_caps_are_excluded_from_legal_wall():
    """§5.5: the flat top/bottom cropped faces must never host an ostium."""
    cfg = _load_cfg()
    case = _cylinder_case()
    frame = build_frame(case, cfg)

    assert frame.wall_np[0].any()
    assert not frame.legal_wall_np[0].any()
    assert frame.wall_np[-1].any()
    assert not frame.legal_wall_np[-1].any()

    endcap_vox = int(round(cfg["endcap_mm"] / cfg["iso_mm"]))
    for k in range(endcap_vox):
        assert not frame.legal_wall_np[k].any(), f"slice {k} within endcap_mm of the top should be forbidden"
        assert not frame.legal_wall_np[-(k + 1)].any(), f"slice -{k+1} within endcap_mm of the bottom should be forbidden"

    reasons = {e["reason"] for e in frame.excluded}
    assert "superior_end_cap" in reasons
    assert "inferior_end_cap" in reasons
    assert "iliac_bifurcation" not in reasons  # a plain cylinder never forks


def test_mid_body_side_wall_stays_legal():
    cfg = _load_cfg()
    case = _cylinder_case()
    frame = build_frame(case, cfg)

    mid_k = case.aorta_np.shape[0] // 2
    assert frame.wall_np[mid_k].any()
    assert np.array_equal(frame.wall_np[mid_k], frame.legal_wall_np[mid_k])


def test_outward_normal_points_radially_at_mid_body():
    cfg = _load_cfg()
    case = _cylinder_case()
    frame = build_frame(case, cfg)

    mid_k = case.aorta_np.shape[0] // 2
    ys, xs = np.nonzero(frame.wall_np[mid_k])
    i = int(np.argmax(xs))  # a wall voxel on the +x side of the tube
    zyx = (mid_k, ys[i], xs[i])

    n = outward_normal(frame, zyx)
    assert abs(n[2]) < 0.2  # mostly in-plane, not pointing along the aorta's axis
    assert n[0] > 0.8  # points away from the axis, towards +x


def test_clock_and_arclen_sanity():
    cfg = _load_cfg()
    case = _cylinder_case()
    frame = build_frame(case, cfg)

    centre = frame.centreline_mm[len(frame.centreline_mm) // 2]
    anterior_point = centre + np.array([0.0, -20.0, 0.0])  # -y = anterior in LPS
    left_point = centre + np.array([20.0, 0.0, 0.0])  # +x = patient-left in LPS

    clock_a, _ = clock_and_arclen(frame, anterior_point)
    clock_l, _ = clock_and_arclen(frame, left_point)
    assert clock_a < 0.5 or clock_a > 11.5  # ~12 o'clock
    assert 2.5 < clock_l < 3.5  # ~3 o'clock

    top_point = frame.centreline_mm[0]
    bottom_point = frame.centreline_mm[-1]
    _, arclen_top = clock_and_arclen(frame, top_point)
    _, arclen_bottom = clock_and_arclen(frame, bottom_point)
    assert arclen_top == 0.0
    assert arclen_bottom > 100.0  # most of the ~200 mm cylinder length


def test_anisotropic_and_rotated_cylinder_still_finds_end_caps():
    """§10.6 prompt 2's coordinate-robustness discipline applied to P1's own
    module: end-cap suppression must survive anisotropic spacing and a
    rotated direction matrix, not just the identity grid."""
    import math

    angle = math.radians(20.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    direction = (cos_a, -sin_a, 0.0, sin_a, cos_a, 0.0, 0.0, 0.0, 1.0)

    cfg = _load_cfg()
    case = _cylinder_case(spacing=(0.8, 0.8, 1.2))
    case.ct.SetDirection(direction)
    case.aorta.SetDirection(direction)

    frame = build_frame(case, cfg)
    assert not frame.legal_wall_np[0].any()
    assert not frame.legal_wall_np[-1].any()
    mid_k = case.aorta_np.shape[0] // 2
    assert frame.legal_wall_np[mid_k].any()
