"""
Synthetic phantom generator (§8.2). Produces a CTA-like SimpleITK volume plus
its exact reference JSON, with caller-specified branch geometry, spacing and
direction cosines (to regression-test coordinate handling on anisotropic /
rotated grids).

Owner: P3.
"""

import numpy as np
import SimpleITK as sitk
from scipy import ndimage

BACKGROUND_HU = 40.0
AORTA_HU = 350.0
BRANCH_HU = 320.0
AORTA_RADIUS_MM = 10.0
BLUR_SIGMA_MM = 0.8
NOISE_STD_HU = 15.0
SEED_ARC_MM = 5.0
SPINE_HU = 700.0
SPINE_OFFSET_MM = 25.0
SPINE_THICKNESS_MM = 20.0
SPINE_HALF_WIDTH_MM = 15.0
CALCIFICATION_HU = 900.0
CALCIFICATION_RADIUS_MM = 2.0
VEIN_HU = 120.0
VEIN_RADIUS_MM = 6.0
VEIN_OFFSET_MM = 20.0
FORK_ARC_MM = 7.0
FORK_ANGLE_DEG = 20.0
FORK_RADIUS_FRAC = 0.75
FORK_MIN_REMAINDER_MM = 3.0


def _direction_matrix(direction):
    """3x3 direction-cosine matrix from a flat 9-sequence, or identity."""
    if direction is None:
        return np.eye(3)
    return np.asarray(direction, dtype=float).reshape(3, 3)


def _physical_grid(shape_xyz, spacing_xyz, direction_mat, origin):
    """Physical (x,y,z) mm coordinates of every voxel, shape (nz,ny,nx,3).

    Args:
        shape_xyz: (nx, ny, nz) voxel grid size.
        spacing_xyz: (sx, sy, sz) mm per voxel.
        direction_mat: (3,3) direction cosine matrix.
        origin: (x, y, z) physical mm origin.

    Returns:
        np.ndarray (nz, ny, nx, 3): physical mm point per voxel, matching
        SimpleITK's `origin + direction @ (spacing * index)`.
    """
    nx, ny, nz = shape_xyz
    kk, jj, ii = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    idx_xyz = np.stack([ii, jj, kk], axis=-1).astype(np.float64)
    m = direction_mat @ np.diag(spacing_xyz)
    return idx_xyz @ m.T + np.asarray(origin, dtype=float)


def _dist_to_segment(points, a, b, clamp=True):
    """Physical-mm distance from `points` to the segment (or line) a->b.

    Args:
        points: (..., 3) physical mm points.
        a, b: (3,) physical mm segment endpoints.
        clamp: if True, distance to the finite segment; if False, to the
            infinite line through a and b.

    Returns:
        np.ndarray (...,) distance in mm from each point to the segment/line.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ab = b - a
    denom = float(np.dot(ab, ab)) or 1e-9
    t = np.tensordot(points - a, ab, axes=([-1], [0])) / denom
    if clamp:
        t = np.clip(t, 0.0, 1.0)
    closest = a + t[..., None] * ab
    return np.linalg.norm(points - closest, axis=-1)


def make_phantom(
    branches: list,
    spacing=(1.0, 1.0, 1.0),
    direction=None,
    shape=(160, 160, 160),
    include_spine=False,
    include_calcification=False,
    include_vein=False,
    fork_branch=False,
):
    """Generate a synthetic CTA phantom and its exact reference JSON.

    The parent aorta is a vertical cylinder (radius 10 mm, 350 HU) running
    the full length of the k (z) index axis, centred in x/y — so the top and
    bottom slices of the volume are its cropped end caps, exactly like real
    cropped data. Each branch attaches at a point computed to lie exactly on
    the aorta's physical surface (never on the caller's say-so), so the
    reference ostium is always correct by construction.

    Args:
        branches: list of dicts, one per branch cylinder, each with:
            theta_deg (float): angle in the index x/y plane (0 = +x index,
                increasing toward +y index) giving where the branch attaches
                around the aorta's circumference.
            arclen_mm (float): distance in mm along the aorta's axis (from
                the k=0 / superior end) where the branch attaches.
            direction_xyz (sequence of 3 floats): unit-ish vector, physical
                (x,y,z) mm frame, the branch's own axis direction pointing
                away from the ostium (normalised internally).
            radius_mm (float): branch radius, mm.
            length_mm (float): branch length from the ostium, mm.
        spacing: (sx, sy, sz) mm per voxel (SimpleITK order) of the output
            grid. Use anisotropic values (e.g. (0.7, 0.7, 2.0)) to test
            coordinate-handling robustness.
        direction: optional 3x3 direction cosine matrix (row-major, flattened
            length-9 sequence) for the output SimpleITK image. None means
            identity.
        shape: (nx, ny, nz) voxel grid size (SimpleITK order).
        include_spine: add a 700 HU slab 25 mm posterior to the aorta.
        include_calcification: add a 900 HU, 2 mm radius sphere in the
            aortic wall.
        include_vein: add a dimmer (120 HU) parallel cylinder.
        fork_branch: make the first branch fork into two at 7 mm from its
            ostium (a common-trunk stand-in); the reference still lists it
            as a single instance, since only its aortic-wall ostium counts.

    Returns:
        (ct_image, aorta_mask_image, reference): SimpleITK images (HU
        float32, mask uint8) on the given grid, background 40 HU, the aorta
        cylinder plus its own mask, the requested branch cylinders (320 HU),
        a 0.8 mm Gaussian blur and 15 HU Gaussian noise; and `reference`, a
        dict in the §5.10 output schema with ostium_xyz_mm on the aortic
        surface, seed_xyz_mm at 5 mm along the branch axis, the true
        radius_mm and true unit direction_xyz, all derived through the same
        origin/spacing/direction affine SimpleITK uses for
        TransformContinuousIndexToPhysicalPoint.
    """
    nx, ny, nz = shape
    spacing_xyz = np.asarray(spacing, dtype=float)
    direction_mat = _direction_matrix(direction)
    origin = (0.0, 0.0, 0.0)

    phys = _physical_grid(shape, spacing_xyz, direction_mat, origin)

    cx, cy = (nx - 1) / 2.0, (ny - 1) / 2.0
    axis_a_mm = direction_mat @ (spacing_xyz * np.array([cx, cy, 0.0])) + origin
    axis_b_mm = direction_mat @ (spacing_xyz * np.array([cx, cy, float(nz - 1)])) + origin
    axis_u = axis_b_mm - axis_a_mm
    axis_u = axis_u / np.linalg.norm(axis_u)

    dist_axis = _dist_to_segment(phys, axis_a_mm, axis_b_mm, clamp=False)
    aorta_mask = dist_axis <= AORTA_RADIUS_MM

    hu = np.full(shape[::-1], BACKGROUND_HU, dtype=np.float64)

    if include_spine:
        posterior_dir = direction_mat @ np.array([0.0, 1.0, 0.0])
        posterior_dir = posterior_dir / np.linalg.norm(posterior_dir)
        lateral_dir = direction_mat @ np.array([1.0, 0.0, 0.0])
        lateral_dir = lateral_dir / np.linalg.norm(lateral_dir)
        axis_mid = (axis_a_mm + axis_b_mm) / 2.0
        rel = phys - axis_mid
        post_offset = rel @ posterior_dir
        lat_offset = rel @ lateral_dir
        spine_mask = (
            (post_offset >= SPINE_OFFSET_MM)
            & (post_offset <= SPINE_OFFSET_MM + SPINE_THICKNESS_MM)
            & (np.abs(lat_offset) <= SPINE_HALF_WIDTH_MM)
        )
        hu[spine_mask] = SPINE_HU

    if include_vein:
        lateral_dir = direction_mat @ np.array([1.0, 0.0, 0.0])
        lateral_dir = lateral_dir / np.linalg.norm(lateral_dir)
        vein_a = axis_a_mm + lateral_dir * VEIN_OFFSET_MM
        vein_b = axis_b_mm + lateral_dir * VEIN_OFFSET_MM
        dist_vein = _dist_to_segment(phys, vein_a, vein_b, clamp=False)
        hu[dist_vein <= VEIN_RADIUS_MM] = VEIN_HU

    hu[aorta_mask] = AORTA_HU

    daughters_ref = []
    for i, br in enumerate(branches):
        theta = np.deg2rad(float(br["theta_deg"]))
        arclen_mm = float(br["arclen_mm"])
        branch_dir = np.asarray(br["direction_xyz"], dtype=float)
        branch_dir = branch_dir / np.linalg.norm(branch_dir)
        radius_mm = float(br["radius_mm"])
        length_mm = float(br["length_mm"])

        ostium_idx = np.array(
            [
                cx + (AORTA_RADIUS_MM / spacing_xyz[0]) * np.cos(theta),
                cy + (AORTA_RADIUS_MM / spacing_xyz[1]) * np.sin(theta),
                arclen_mm / spacing_xyz[2],
            ]
        )
        ostium_mm = direction_mat @ (spacing_xyz * ostium_idx) + origin
        far_mm = ostium_mm + branch_dir * length_mm

        branch_mask = _dist_to_segment(phys, ostium_mm, far_mm) <= radius_mm

        if fork_branch and i == 0:
            split_mm = ostium_mm + branch_dir * FORK_ARC_MM
            perp = np.cross(branch_dir, np.array([0.0, 0.0, 1.0]))
            if np.linalg.norm(perp) < 1e-6:
                perp = np.cross(branch_dir, np.array([1.0, 0.0, 0.0]))
            perp = perp / np.linalg.norm(perp)
            angle = np.deg2rad(FORK_ANGLE_DEG)
            dir_a = branch_dir * np.cos(angle) + perp * np.sin(angle)
            dir_b = branch_dir * np.cos(angle) - perp * np.sin(angle)
            remaining_len = max(length_mm - FORK_ARC_MM, FORK_MIN_REMAINDER_MM)
            far_a = split_mm + dir_a * remaining_len
            far_b = split_mm + dir_b * remaining_len
            fork_mask = (_dist_to_segment(phys, split_mm, far_a) <= radius_mm * FORK_RADIUS_FRAC) | (
                _dist_to_segment(phys, split_mm, far_b) <= radius_mm * FORK_RADIUS_FRAC
            )
            branch_mask = branch_mask | fork_mask

        hu[branch_mask] = BRANCH_HU

        seed_mm = ostium_mm + branch_dir * SEED_ARC_MM
        takeoff_deg = float(np.degrees(np.arccos(np.clip(np.dot(branch_dir, axis_u), -1.0, 1.0))))
        daughters_ref.append(
            {
                "instance_id": f"branch_{i + 1:03d}",
                "parent_instance_id": "aorta",
                "ostium_xyz_mm": ostium_mm.tolist(),
                "seed_xyz_mm": seed_mm.tolist(),
                "radius_mm": radius_mm,
                "direction_xyz": branch_dir.tolist(),
                "confidence": 1.0,
                "clock_position": None,
                "arclen_from_top_mm": arclen_mm,
                "takeoff_angle_deg": takeoff_deg,
            }
        )

    if include_calcification:
        calc_theta = np.deg2rad(45.0)
        calc_idx = np.array(
            [
                cx + (AORTA_RADIUS_MM / spacing_xyz[0]) * np.cos(calc_theta),
                cy + (AORTA_RADIUS_MM / spacing_xyz[1]) * np.sin(calc_theta),
                nz / 2.0,
            ]
        )
        calc_mm = direction_mat @ (spacing_xyz * calc_idx) + origin
        dist_calc = np.linalg.norm(phys - calc_mm, axis=-1)
        hu[dist_calc <= CALCIFICATION_RADIUS_MM] = CALCIFICATION_HU

    sigma_zyx = (
        BLUR_SIGMA_MM / spacing_xyz[2],
        BLUR_SIGMA_MM / spacing_xyz[1],
        BLUR_SIGMA_MM / spacing_xyz[0],
    )
    hu = ndimage.gaussian_filter(hu, sigma=sigma_zyx)
    rng = np.random.default_rng(0)
    hu = hu + rng.normal(0.0, NOISE_STD_HU, size=hu.shape)

    ct_image = sitk.GetImageFromArray(hu.astype(np.float32))
    ct_image.SetSpacing(tuple(spacing_xyz))
    ct_image.SetDirection(tuple(direction_mat.flatten()))
    ct_image.SetOrigin(origin)

    mask_image = sitk.GetImageFromArray(aorta_mask.astype(np.uint8))
    mask_image.CopyInformation(ct_image)

    reference = {
        "case_id": "phantom",
        "parent": {"instance_id": "aorta"},
        "daughters": daughters_ref,
        "excluded_candidates": [],
        "meta": {"runtime_s": 0.0, "a_med_hu": AORTA_HU, "t_vessel_hu": None, "warnings": []},
    }

    return ct_image, mask_image, reference
