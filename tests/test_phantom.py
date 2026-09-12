"""Regression tests for eval/phantom.py: geometry correctness, and survival
of anisotropic spacing + rotated direction cosines (playbook §8.2, §12)."""

import numpy as np
import SimpleITK as sitk

from eval.phantom import make_phantom, AORTA_RADIUS_MM

BRANCHES = [
    {"theta_deg": 90.0, "arclen_mm": 60.0, "direction_xyz": (0.0, -1.0, 0.05), "radius_mm": 3.5, "length_mm": 15.0},
    {"theta_deg": 0.0, "arclen_mm": 80.0, "direction_xyz": (1.0, 0.0, -0.1), "radius_mm": 2.5, "length_mm": 12.0},
]


def _axis_perp_distance(image, ostium_mm, shape_xyz, spacing_xyz, direction_mat):
    nx, ny, nz = shape_xyz
    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    a = direction_mat @ (spacing_xyz * np.array([cx, cy, 0.0]))
    b = direction_mat @ (spacing_xyz * np.array([cx, cy, float(nz - 1)]))
    u = b - a
    u = u / np.linalg.norm(u)
    v = np.asarray(ostium_mm) - a
    t = np.dot(v, u)
    perp = v - t * u
    return np.linalg.norm(perp)


def test_phantom_basic_shape_and_mask():
    ct, mask, ref = make_phantom(BRANCHES, shape=(100, 100, 100))
    assert ct.GetSize() == (100, 100, 100)
    mask_np = sitk.GetArrayFromImage(mask)
    assert mask_np.dtype == np.uint8
    assert mask_np.sum() > 0
    assert len(ref["daughters"]) == 2


def test_phantom_ostium_on_aortic_surface_identity_grid():
    ct, mask, ref = make_phantom(BRANCHES, shape=(100, 100, 100))
    direction_mat = np.eye(3)
    spacing_xyz = np.array([1.0, 1.0, 1.0])
    for d in ref["daughters"]:
        r = _axis_perp_distance(ct, d["ostium_xyz_mm"], (100, 100, 100), spacing_xyz, direction_mat)
        assert abs(r - AORTA_RADIUS_MM) < 1e-6


def test_phantom_survives_anisotropic_and_rotated_grid():
    """The ostium must still sit exactly on the true aortic surface when the
    grid has anisotropic spacing and a non-identity direction matrix."""
    theta = np.deg2rad(20.0)
    direction = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    spacing = (0.7, 0.7, 2.0)
    shape = (140, 140, 100)
    ct, mask, ref = make_phantom(
        BRANCHES,
        spacing=spacing,
        direction=direction.flatten().tolist(),
        shape=shape,
        include_spine=True,
        include_calcification=True,
        include_vein=True,
        fork_branch=True,
    )
    assert ct.GetSpacing() == spacing
    spacing_xyz = np.array(spacing)
    for d in ref["daughters"]:
        r = _axis_perp_distance(ct, d["ostium_xyz_mm"], shape, spacing_xyz, direction)
        assert abs(r - AORTA_RADIUS_MM) < 1e-6

    # seed sits 5 mm along the branch axis from the ostium
    for d in ref["daughters"]:
        ostium = np.asarray(d["ostium_xyz_mm"])
        seed = np.asarray(d["seed_xyz_mm"])
        direction_xyz = np.asarray(d["direction_xyz"])
        expected = ostium + direction_xyz * 5.0
        assert np.allclose(seed, expected, atol=1e-6)

    # fork_branch keeps a single reference instance for the forked branch
    assert len(ref["daughters"]) == len(BRANCHES)


def test_phantom_short_crop_has_no_extra_branches():
    """A phantom with zero requested branches should still produce a valid
    aorta mask and an empty daughters list (regression-tests the end-cap
    trap: a bare cylinder must not itself look like a branch)."""
    ct, mask, ref = make_phantom([], shape=(60, 60, 60))
    assert ref["daughters"] == []
    mask_np = sitk.GetArrayFromImage(mask)
    assert mask_np.sum() > 0
