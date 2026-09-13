"""
Stage 9 (§5.9): eligibility gate and de-duplication.

Owner: P1.
"""

import numpy as np

from src.instances import RawBranch
from src.geometry import BranchGeom
from src.intensity import Profile


def accept(raw: RawBranch, geom: BranchGeom, profile: Profile, cfg: dict) -> tuple:
    """Decide whether a candidate branch is a real, eligible daughter.

    Args:
        raw: `RawBranch` from `instances.find_raw_branches`.
        geom: `BranchGeom` from `geometry.measure` for the same instance.
        profile: `Profile` from `intensity.profile_aorta`.
        cfg: parsed config. Uses min_extent_mm (mm), max_extent_mm (mm),
            min_radius_mm (mm), patch_area_min_mm2/patch_area_max_mm2 (mm^2),
            hu_ratio_min (unitless), tortuosity_max (unitless),
            max_mean_cross_section_mm2 (mm^2).

    Returns:
        (keep, reason): `keep` is bool. `reason` is a short string
        explaining the decision (e.g. "ok", "below_min_radius",
        "patch_too_small", "patch_too_large", "low_hu_ratio",
        "too_tortuous", "insufficient_extent", "excessive_extent",
        "blobby_leak"), always populated and logged when
        cfg['log_rejections'].

    Notes:
        `excessive_extent` and `blobby_leak` both guard against the same
        real failure mode observed on real cases: a candidate component that
        leaked into bone or an enhancing organ can still pass every other
        check (it touches the legal wall, clears min_extent_mm, and can even
        sit inside hu_ratio_min), because nothing else here bounds how large
        or how thick the component is. Real first-order aortic daughters top
        out around ~3.5 mm radius (celiac/SMA; see docs/brief.md), so a
        candidate whose geodesic extent or average cross-section is far
        beyond that is structurally not a branch, regardless of its HU.
    """
    if raw.geodesic_extent_mm < float(cfg["min_extent_mm"]):
        return False, "insufficient_extent"
    if raw.geodesic_extent_mm > float(cfg["max_extent_mm"]):
        return False, "excessive_extent"
    if geom.radius_mm < float(cfg["min_radius_mm"]):
        return False, "below_min_radius"
    if raw.patch_area_mm2 < float(cfg["patch_area_min_mm2"]):
        return False, "patch_too_small"
    if raw.patch_area_mm2 > float(cfg["patch_area_max_mm2"]):
        return False, "patch_too_large"
    if raw.hu_ratio < float(cfg["hu_ratio_min"]):
        return False, "low_hu_ratio"
    if raw.mean_cross_section_mm2 > float(cfg["max_mean_cross_section_mm2"]):
        return False, "blobby_leak"
    if geom.tortuosity > float(cfg["tortuosity_max"]):
        return False, "too_tortuous"
    return True, "ok"


def _direction_angle_deg(d1: np.ndarray, d2: np.ndarray) -> float:
    cosang = float(np.clip(np.dot(d1, d2), -1.0, 1.0))
    return float(np.degrees(np.arccos(cosang)))


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
    n = len(items)
    if n == 0:
        return []

    dedup_dist_mm = float(cfg["dedup_dist_mm"])
    dedup_angle_deg = float(cfg["dedup_angle_deg"])

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        _, gi = items[i]
        for j in range(i + 1, n):
            _, gj = items[j]
            dist = float(np.linalg.norm(gi.ostium_mm - gj.ostium_mm))
            if dist > dedup_dist_mm:
                continue  # merge requires BOTH close position AND similar direction
            if _direction_angle_deg(gi.direction, gj.direction) < dedup_angle_deg:
                union(i, j)

    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)

    merged = []
    for idxs in clusters.values():
        # keep the instance with the largest (most confident) contact patch
        best = max(idxs, key=lambda k: items[k][0].patch_area_mm2)
        merged.append(items[best])
    return merged
