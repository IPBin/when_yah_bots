"""
Stage 9 (§5.9): eligibility gate and de-duplication.

Owner: P1.
"""

from src.instances import RawBranch
from src.geometry import BranchGeom
from src.intensity import Profile


def accept(raw: RawBranch, geom: BranchGeom, profile: Profile, cfg: dict) -> tuple:
    """Decide whether a candidate branch is a real, eligible daughter.

    Args:
        raw: `RawBranch` from `instances.find_raw_branches`.
        geom: `BranchGeom` from `geometry.measure` for the same instance.
        profile: `Profile` from `intensity.profile_aorta`.
        cfg: parsed config. Uses min_extent_mm (mm), min_radius_mm (mm),
            patch_area_min_mm2/patch_area_max_mm2 (mm^2), hu_ratio_min
            (unitless), tortuosity_max (unitless).

    Returns:
        (keep, reason): `keep` is bool. `reason` is a short string
        explaining the decision (e.g. "ok", "below_min_radius",
        "patch_too_small", "patch_too_large", "low_hu_ratio",
        "too_tortuous", "insufficient_extent"), always populated and logged
        when cfg['log_rejections'].
    """
    raise NotImplementedError


def dedup(items: list, cfg: dict) -> list:
    """Merge duplicate detections of the same real ostium.

    Args:
        items: list of (raw, geom) tuples (or equivalent) that passed
            `accept`, each carrying an ostium position (mm) and a direction
            (unit vector).
        cfg: parsed config. Uses dedup_dist_mm (mm) and dedup_angle_deg
            (degrees).

    Returns:
        A filtered list with near-duplicate instances merged: two items are
        merged only if their ostium centroids are within cfg['dedup_dist_mm']
        of each other AND their directions at 5 mm differ by less than
        cfg['dedup_angle_deg']. Bias toward keeping items split, per
        playbook §5.7 (the brief separates nearby real origins).
    """
    raise NotImplementedError
