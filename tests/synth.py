"""Shared synthetic-case builder for P1's module tests (§10.6 prompts 7-9).

Not the official phantom (`eval/phantom.py`, now implemented and used by
`tests/test_phantom.py`, `tests/test_report.py`, `tests/test_pipeline_integration.py`)
-- a lighter, private harness that builds a `Case`/`Profile` pair directly,
skipping disk I/O and `intensity.profile_aorta`, for faster unit tests of
instances/geometry/gate. Every module under test only ever sees a
`Case`/`AortaFrame`/`Profile`, so nothing here is pipeline-specific.
"""

import numpy as np
import SimpleITK as sitk

from src.io_geom import Case
from src.intensity import Profile

AORTA_HU = 350.0
BACKGROUND_HU = 40.0


def _cylinder_mask(zz, yy, xx, origin_zyx, axis_zyx, radius_vox, length_vox):
    """Bool mask of a solid cylinder: axis from `origin_zyx` along the unit
    vector `axis_zyx` for `length_vox`, with the given circular radius."""
    axis = np.asarray(axis_zyx, dtype=float)
    axis = axis / np.linalg.norm(axis)
    oz, oy, ox = origin_zyx
    vz, vy, vx = zz - oz, yy - oy, xx - ox
    t = vz * axis[0] + vy * axis[1] + vx * axis[2]
    perp2 = (vz - t * axis[0]) ** 2 + (vy - t * axis[1]) ** 2 + (vx - t * axis[2]) ** 2
    return (t >= 0.0) & (t <= length_vox) & (perp2 <= radius_vox ** 2)


def make_case_with_branches(
    branches,
    nx=100,
    ny=100,
    nz=200,
    aorta_radius_vox=15.0,
    aorta_centre=(50.0, 50.0),
    spacing=(1.0, 1.0, 1.0),
    case_id="synthetic",
):
    """A vertical aorta cylinder (full z extent, both flat ends present, like
    a real mask cropped to its bounding box) plus one straight branch stub
    per entry in `branches`.

    Args:
        branches: list of dicts, each with:
            angle_deg: direction off the aorta in the axial (x,y) plane,
                0 = +x, 90 = +y.
            z: axial slice (voxel index) at which the branch leaves.
            radius_vox: branch radius in voxels.
            length_vox: branch length beyond the aortic surface, in voxels.
        nx, ny, nz, aorta_radius_vox, aorta_centre, spacing: grid geometry.

    Returns:
        (case, profile): a `Case` with `aorta_np` / `branch_np` (aorta plus
        every branch, all at `AORTA_HU`) and a hand-built `Profile` (skips
        `intensity.profile_aorta` for a fully deterministic reference HU).
    """
    cy, cx = aorta_centre
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    aorta_np = ((yy - cy) ** 2 + (xx - cx) ** 2) <= aorta_radius_vox ** 2

    branch_np = np.zeros_like(aorta_np)
    for b in branches:
        angle = np.radians(b["angle_deg"])
        axis_zyx = (0.0, np.sin(angle), np.cos(angle))
        origin_zyx = (float(b["z"]), cy, cx)
        branch_np |= _cylinder_mask(
            zz, yy, xx, origin_zyx, axis_zyx, b["radius_vox"], aorta_radius_vox + b["length_vox"]
        )

    bright_np = aorta_np | branch_np
    ct_np = np.where(bright_np, AORTA_HU, BACKGROUND_HU).astype(np.float32)

    ct = sitk.GetImageFromArray(ct_np)
    ct.SetSpacing(spacing)
    aorta_img = sitk.GetImageFromArray(aorta_np.astype(np.uint8))
    aorta_img.CopyInformation(ct)
    aorta_img = sitk.Cast(aorta_img, sitk.sitkUInt8)

    case = Case(ct=ct, aorta=aorta_img, ct_np=ct_np, aorta_np=aorta_np, case_id=case_id)
    profile = Profile(
        a_med=AORTA_HU, a_p10=AORTA_HU - 50.0, a_iqr=40.0,
        t_vessel=200.0, t_high=300.0, t_bone=900.0,
    )
    cand = bright_np
    return case, profile, cand
