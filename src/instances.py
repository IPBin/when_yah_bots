"""
Stage 6/7 (§5.6, §5.7): candidate connected components, contact patches over
the legal wall, and the multi-seed geodesic race that splits one blob into
one instance per real ostium.

Owner: P1.
"""

from dataclasses import dataclass

import numpy as np

from src.io_geom import Case
from src.aorta_frame import AortaFrame
from src.intensity import Profile


@dataclass
class RawBranch:
    """One candidate branch instance, prior to per-branch geometry (Stage 8).

    Attributes:
        patch_zyx: (M, 3) int array, voxel indices [z,y,x] of the contact
            patch on the legal aortic wall belonging to this instance.
        voxels_zyx: (K, 3) int array, voxel indices [z,y,x] of all candidate
            voxels assigned to this instance by the geodesic race.
        geodesic_extent_mm: maximum geodesic distance (mm) from the contact
            patch to any assigned voxel, through the assigned voxel set.
        patch_area_mm2: physical area (mm^2) of the contact patch.
        mean_hu: mean HU of the CT within `voxels_zyx`.
        hu_ratio: mean_hu / profile.a_med (unitless).
    """

    patch_zyx: np.ndarray
    voxels_zyx: np.ndarray
    geodesic_extent_mm: float
    patch_area_mm2: float
    mean_hu: float
    hu_ratio: float


def find_raw_branches(
    case: Case,
    cand: np.ndarray,
    frame: AortaFrame,
    profile: Profile,
    cfg: dict,
) -> list:
    """Find one RawBranch per real ostium touching the legal aortic wall.

    Args:
        case: loaded `Case` (ct_np HU, aorta_np bool, [z,y,x], cfg['iso_mm']
            isotropic grid).
        cand: bool [z,y,x] candidate mask from `candidates.candidate_mask`.
        frame: `AortaFrame` from `aorta_frame.build_frame`, providing
            `legal_wall_np`.
        profile: `Profile` from `intensity.profile_aorta`.
        cfg: parsed config (no literal thresholds outside cfg).

    Returns:
        list[RawBranch], one per distinct contact patch on the legal wall,
        found by: removing the dilated aorta mask from `cand`, labelling
        26-connected components, finding each component's contact patch on
        `frame.legal_wall_np`, splitting patches that are connected within
        one component (so two ostia sharing a merged blob become two
        instances), and assigning every voxel in the shared component to its
        nearest patch via a multi-seed geodesic race
        (skimage.graph.MCP_Geometric with multiple seeds and its traceback).

    Notes:
        Vectorised where possible; no per-voxel Python loops except where
        skimage's MCP API requires seed iteration.
    """
    raise NotImplementedError
