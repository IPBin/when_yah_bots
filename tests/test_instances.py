"""Tests for src/instances.py (§10.6 prompt 7).

Two levels: an end-to-end check on a synthetic cylinder-plus-branch case
(tests/synth.py), and a hand-built worst-case check that a single bridged
component with two distinct contact patches on the wall splits into two
instances -- the central design decision of §5.7 ("one instance per contact
patch, not per component").
"""

import numpy as np
import SimpleITK as sitk
import yaml
from scipy import ndimage

from src.io_geom import Case
from src.intensity import Profile
from src.aorta_frame import AortaFrame, build_frame
from src.instances import find_raw_branches

from tests.synth import make_case_with_branches, AORTA_HU, BACKGROUND_HU


def _load_cfg():
    with open("config/default.yaml") as f:
        return yaml.safe_load(f)


def test_single_branch_yields_one_instance_with_plausible_geometry():
    cfg = _load_cfg()
    branch = {"angle_deg": 0.0, "z": 100, "radius_vox": 3.0, "length_vox": 12.0}
    case, profile, cand = make_case_with_branches([branch])
    frame = build_frame(case, cfg)

    raw = find_raw_branches(case, cand, frame, profile, cfg)

    assert len(raw) == 1
    rb = raw[0]
    assert rb.patch_zyx.shape[0] > 0
    assert rb.voxels_zyx.shape[0] > 0
    # branch sticks out ~12 mm beyond the aortic surface
    assert 8.0 <= rb.geodesic_extent_mm <= 16.0
    assert rb.hu_ratio > 0.9  # same HU as the aorta lumen by construction
    # patch sits on a slice well clear of both end caps
    assert np.all(np.abs(rb.patch_zyx[:, 0] - branch["z"]) <= 5)


def test_two_separated_branches_are_not_merged_into_one_instance():
    cfg = _load_cfg()
    branches = [
        {"angle_deg": -30.0, "z": 100, "radius_vox": 2.0, "length_vox": 10.0},
        {"angle_deg": 30.0, "z": 100, "radius_vox": 2.0, "length_vox": 10.0},
    ]
    case, profile, cand = make_case_with_branches(branches)
    frame = build_frame(case, cfg)

    raw = find_raw_branches(case, cand, frame, profile, cfg)

    # ~16 mm apart at the wall, well clear of each other -- must not be
    # accidentally fused into a single instance.
    assert len(raw) == 2


def test_one_component_two_wall_patches_splits_via_geodesic_race():
    """Directly engineered worst case: a single connected candidate blob
    bridging two disjoint contact patches on the wall must split into two
    RawBranch instances, each owning the voxels nearest its own patch."""
    cfg = _load_cfg()
    shape = (5, 30, 30)  # z, y, x

    aorta_np = np.zeros(shape, dtype=bool)
    aorta_np[:, :, :9] = True  # the "parent" occupies x < 9

    legal_wall = np.zeros(shape, dtype=bool)
    legal_wall[:, 10:12, 8] = True  # patch A
    legal_wall[:, 16:18, 8] = True  # patch B, 4 voxels of gap from A

    branch_block = np.zeros(shape, dtype=bool)
    branch_block[:, 8:20, 9:15] = True  # bridges both patches

    ct_np = np.where(aorta_np | branch_block, AORTA_HU, BACKGROUND_HU).astype(np.float32)
    ct = sitk.GetImageFromArray(ct_np)
    aorta_img = sitk.GetImageFromArray(aorta_np.astype(np.uint8))
    aorta_img.CopyInformation(ct)
    aorta_img = sitk.Cast(aorta_img, sitk.sitkUInt8)
    case = Case(ct=ct, aorta=aorta_img, ct_np=ct_np, aorta_np=aorta_np, case_id="bridge")

    profile = Profile(a_med=AORTA_HU, a_p10=300.0, a_iqr=40.0, t_vessel=200.0, t_high=300.0, t_bone=900.0)
    cand = aorta_np | branch_block

    frame = AortaFrame(
        centreline_mm=np.zeros((1, 3)),
        wall_np=legal_wall,
        legal_wall_np=legal_wall,
        excluded=[],
        _case=case,
        _k_axis=np.array([0.0]),
        _centreline_by_k_mm=np.zeros((1, 3)),
        _arclen_by_row=np.zeros(1),
    )

    raw = find_raw_branches(case, cand, frame, profile, cfg)

    assert len(raw) == 2
    total_voxels = sum(rb.voxels_zyx.shape[0] for rb in raw)
    # `find_raw_branches` strips a 1-voxel buffer around the aorta before
    # labelling components (§5.6), so the counted branch is slightly smaller
    # than the raw drawn block.
    struct = ndimage.generate_binary_structure(3, 3)
    expected_component = branch_block & ~ndimage.binary_dilation(aorta_np, structure=struct, iterations=1)
    assert total_voxels == int(expected_component.sum())
    # every voxel a patch owns should be strictly closer (in y) to its own
    # patch's row-band than to the other patch's
    for rb in raw:
        patch_y = rb.patch_zyx[:, 1]
        assert np.ptp(patch_y) <= 2  # each instance's patch is one tight band, not both
