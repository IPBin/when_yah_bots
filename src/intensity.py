"""
Stage 2 (§5.2): profile the aortic lumen and derive adaptive HU thresholds.

Owner: P2.

Everything here is computed relative to the *given* aorta's own lumen HU,
because contrast timing varies enormously between scans (see playbook §3.3).
No literal HU threshold may appear outside this module; every multiplier
comes from cfg.
"""

import logging
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from src.io_geom import Case


@dataclass
class Profile:
    """Per-case intensity profile of the aortic lumen, all in HU.

    Attributes:
        a_med: median HU inside the eroded aortic lumen.
        a_p10: 10th percentile HU inside the eroded aortic lumen.
        a_iqr: interquartile range of HU inside the eroded aortic lumen.
        t_vessel: adaptive low threshold for hysteresis (HU).
        t_high: adaptive high (seed) threshold for hysteresis (HU).
        t_bone: adaptive bone-suppression threshold (HU).
    """

    a_med: float
    a_p10: float
    a_iqr: float
    t_vessel: float
    t_high: float
    t_bone: float


def profile_aorta(case: Case, cfg: dict) -> Profile:
    """Measure the aortic lumen HU distribution and derive thresholds.

    Args:
        case: loaded `Case` (ct_np in HU, aorta_np bool mask, both [z,y,x],
            on a cfg['iso_mm'] isotropic grid).
        cfg: parsed config. Uses k_vessel, frac_vessel, frac_high,
            vessel_hu_floor, bone_offset (all unitless multipliers or HU
            offsets, see config/default.yaml).

    Returns:
        A `Profile` with a_med/a_p10/a_iqr and the derived t_vessel/t_high/
        t_bone thresholds (all HU). Must be logged when cfg['verbose'].
    """
    iso_mm = float(cfg["iso_mm"])
    erosion_iterations = max(1, round(2.0 / iso_mm))
    aorta_core = ndimage.binary_erosion(case.aorta_np, iterations=erosion_iterations)

    if not aorta_core.any():
        logging.warning(
            "profile_aorta: eroded aorta core is empty (mask too thin for a %.1f mm erosion); "
            "falling back to the un-eroded mask.",
            2.0,
        )
        aorta_core = case.aorta_np

    lumen_hu = case.ct_np[aorta_core]
    if lumen_hu.size == 0:
        logging.warning("profile_aorta: aorta mask is empty; using degenerate zero-HU profile.")
        lumen_hu = np.zeros(1, dtype=np.float32)

    a_med = float(np.median(lumen_hu))
    a_p10 = float(np.percentile(lumen_hu, 10))
    q75, q25 = np.percentile(lumen_hu, [75, 25])
    a_iqr = float(q75 - q25)

    k_vessel = float(cfg["k_vessel"])
    frac_vessel = float(cfg["frac_vessel"])
    frac_high = float(cfg["frac_high"])
    vessel_hu_floor = float(cfg["vessel_hu_floor"])
    bone_offset = float(cfg["bone_offset"])

    t_vessel = max(a_med - k_vessel * (a_med - a_p10), frac_vessel * a_med, vessel_hu_floor)
    t_high = frac_high * a_med
    t_bone = a_med + bone_offset

    profile = Profile(a_med=a_med, a_p10=a_p10, a_iqr=a_iqr, t_vessel=t_vessel, t_high=t_high, t_bone=t_bone)

    if cfg.get("verbose"):
        logging.info(
            "profile_aorta[%s]: a_med=%.1f a_p10=%.1f a_iqr=%.1f -> t_vessel=%.1f t_high=%.1f t_bone=%.1f",
            case.case_id,
            a_med,
            a_p10,
            a_iqr,
            t_vessel,
            t_high,
            t_bone,
        )

    return profile
