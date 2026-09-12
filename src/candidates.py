"""
Stage 3 (§5.3): build the bright-candidate mask; suppress bone; drop stray
components not attached to the aorta.

Owner: P2.
"""

import numpy as np
from scipy import ndimage
from skimage.filters import apply_hysteresis_threshold

from src.io_geom import Case
from src.intensity import Profile


def candidate_mask(case: Case, profile: Profile, cfg: dict) -> np.ndarray:
    """Build the bright-tube candidate mask for this case.

    Args:
        case: loaded `Case` (ct_np HU, aorta_np bool, [z,y,x], cfg['iso_mm']
            isotropic grid).
        profile: `Profile` from `intensity.profile_aorta` (HU thresholds).
        cfg: parsed config. Uses bone_dilate_mm (mm) and max_stray_cc_ml
            (millilitres = cm^3).

    Returns:
        bool np.ndarray, shape [z,y,x], True where a voxel is a bright-tube
        candidate: hysteresis-thresholded between profile.t_vessel and
        profile.t_high, with bone (> profile.t_bone, dilated by
        cfg['bone_dilate_mm']) removed, unioned with the given aorta mask,
        and with any connected component not touching the aorta whose
        volume exceeds cfg['max_stray_cc_ml'] dropped.

    Notes:
        Vectorised only (skimage.filters.apply_hysteresis_threshold,
        scipy.ndimage for dilation/labeling). No per-voxel Python loops.
    """
    iso_mm = float(cfg["iso_mm"])
    voxel_volume_ml = (iso_mm ** 3) / 1000.0  # mm^3 -> mL (1 mL = 1000 mm^3)

    grown = apply_hysteresis_threshold(case.ct_np, profile.t_vessel, profile.t_high)

    bone_dilate_iters = max(1, round(float(cfg["bone_dilate_mm"]) / iso_mm))
    bone = ndimage.binary_dilation(case.ct_np > profile.t_bone, iterations=bone_dilate_iters)

    candidate = (grown & ~bone) | case.aorta_np

    structure = ndimage.generate_binary_structure(3, 3)  # 26-connectivity
    labeled, n_components = ndimage.label(candidate, structure=structure)

    if n_components > 0:
        touches_aorta = ndimage.binary_dilation(case.aorta_np, structure=structure)
        component_ids = np.arange(1, n_components + 1)
        volumes_ml = ndimage.sum(np.ones_like(candidate, dtype=np.float64), labeled, index=component_ids) * voxel_volume_ml
        touches = ndimage.sum(touches_aorta.astype(np.float64), labeled, index=component_ids) > 0

        max_stray_cc_ml = float(cfg["max_stray_cc_ml"])
        drop_ids = component_ids[(~touches) & (volumes_ml > max_stray_cc_ml)]
        if drop_ids.size > 0:
            candidate = candidate & ~np.isin(labeled, drop_ids)

    return candidate.astype(bool)
