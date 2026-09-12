"""
Stage 8 (§5.8): per-branch ostium, proximal path, seed, direction and
radius, all in physical mm.

Owner: P1.
"""

from dataclasses import dataclass

import numpy as np

from src.io_geom import Case
from src.aorta_frame import AortaFrame
from src.intensity import Profile
from src.instances import RawBranch


@dataclass
class BranchGeom:
    """Measured geometry of one branch instance, all lengths in mm.

    Attributes:
        ostium_mm: (3,) physical point (x, y, z), the contact-patch centroid
            nudged to mid-wall (sub-voxel).
        seed_mm: (3,) physical point (x, y, z) at cfg['seed_arc_mm'] arc
            length along the path, snapped to the local EDT maximum.
        direction: (3,) unit vector (x, y, z), oriented away from the
            ostium, from PCA of the path within cfg['pca_window_mm'].
        radius_mm: EDT value (mm) at the seed point.
        path_mm: (P, 3) physical points (x, y, z) along the proximal path,
            resampled to cfg['path_step_mm'] arc-length steps. Kept for
            visualisation.
        tortuosity: path length (mm) divided by the straight-line distance
            (mm) from ostium to path end (unitless).
    """

    ostium_mm: np.ndarray
    seed_mm: np.ndarray
    direction: np.ndarray
    radius_mm: float
    path_mm: np.ndarray
    tortuosity: float


def measure(
    case: Case,
    raw: RawBranch,
    frame: AortaFrame,
    profile: Profile,
    cfg: dict,
) -> BranchGeom:
    """Measure ostium, path, seed, direction and radius for one raw branch.

    Args:
        case: loaded `Case` (for physical-point transforms and CT values).
        raw: `RawBranch` from `instances.find_raw_branches`.
        frame: `AortaFrame` from `aorta_frame.build_frame` (for mid-wall
            nudging of the ostium).
        profile: `Profile` from `intensity.profile_aorta`.
        cfg: parsed config. Uses trace_max_mm, seed_arc_mm, path_step_mm,
            pca_window_mm, seed_snap_mm (mm, mm, mm, [mm,mm], mm).

    Returns:
        A `BranchGeom` per the dataclass docstring above. The Euclidean
        distance transform (EDT) is computed on `raw.voxels_zyx`; the path
        is a minimum-cost path from the ostium to the voxel at maximum
        geodesic distance from the patch (capped at cfg['trace_max_mm']),
        with cost 1/(EDT + 0.1) so it hugs the lumen centre.
    """
    raise NotImplementedError
