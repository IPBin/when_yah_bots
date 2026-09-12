"""
Stage 4/5 (§5.4, §5.5): aorta centreline, wall surface, outward normals,
clock/arc-length frame, and the forbidden surface (cropped end caps + iliac
fork).

Owner: P1.
"""

from dataclasses import dataclass

import numpy as np

from src.io_geom import Case


@dataclass
class AortaFrame:
    """Geometric frame built from the given aorta mask.

    Attributes:
        centreline_mm: (N, 3) array of centreline points in physical mm
            (x, y, z order matches idx_to_mm output), ordered superior ->
            inferior, one point per axial slice (smoothed).
        wall_np: bool [z,y,x], all aortic wall voxels (mask minus its
            1-voxel erosion).
        legal_wall_np: bool [z,y,x], `wall_np` with the forbidden surface
            (end caps, iliac fork) removed. Only these voxels may host an
            ostium.
        excluded: list of dicts, one per excluded wall region, each with at
            least {"reason": str, "ostium_xyz_mm": [x,y,z]}. Reasons include
            "superior_end_cap", "inferior_end_cap", "iliac_bifurcation".
    """

    centreline_mm: np.ndarray
    wall_np: np.ndarray
    legal_wall_np: np.ndarray
    excluded: list


def build_frame(case: Case, cfg: dict) -> AortaFrame:
    """Build the aorta's centreline, wall and forbidden-surface frame.

    Args:
        case: loaded `Case` (aorta_np bool, [z,y,x], cfg['iso_mm'] isotropic
            grid, plus the SimpleITK `case.aorta` image for direction
            cosines / physical transforms).
        cfg: parsed config. Uses centreline_smooth_mm, endcap_mm,
            endcap_angle_deg, iliac_margin_mm (all mm or degrees).

    Returns:
        An `AortaFrame` per the dataclass docstring above.
    """
    raise NotImplementedError


def outward_normal(frame: AortaFrame, zyx) -> np.ndarray:
    """Outward unit normal at a wall voxel, in physical mm direction.

    Args:
        frame: `AortaFrame` built by `build_frame` for this case.
        zyx: voxel index (z, y, x) of a wall voxel.

    Returns:
        np.ndarray, shape (3,), unit vector in the SimpleITK (x, y, z)
        physical direction, computed as the normalised difference between
        the wall point and the centreline point at the same slice, both in
        physical mm.
    """
    raise NotImplementedError


def clock_and_arclen(frame: AortaFrame, xyz_mm) -> tuple:
    """Clock position and arc length of a physical point relative to the frame.

    Args:
        frame: `AortaFrame` built by `build_frame` for this case.
        xyz_mm: a physical point (x, y, z) in mm.

    Returns:
        (clock_hours, arclen_mm): clock_hours is a float in [0, 12) with
        12 o'clock = anterior (derived from the image's direction cosines in
        LPS, where anterior is -y -- never assume an array axis), increasing
        toward patient-left. arclen_mm is the arc length in mm along the
        centreline from the superior end of coverage to the point nearest
        `xyz_mm` on the centreline.
    """
    raise NotImplementedError
