"""
JSON writer + visual checks (§9.1) + unrolled aortic map (§9.2) + optional
self-contained HTML report (§9.3).

Owner: P3 (visual checks, unrolled map); P2/run.py for the JSON writer.
"""

from src.io_geom import Case
from src.aorta_frame import AortaFrame


def write_prediction_json(case_id: str, daughters: list, excluded: list, meta: dict, output_path: str) -> None:
    """Write the required prediction JSON for one case.

    Args:
        case_id: the case identifier string.
        daughters: list of dicts, one per accepted branch, each with
            instance_id, parent_instance_id ("aorta"), ostium_xyz_mm,
            seed_xyz_mm, radius_mm, direction_xyz (unit vector), confidence,
            clock_position (hours), arclen_from_top_mm, takeoff_angle_deg.
            See branchseed_playbook.md §5.10 for the exact schema.
        excluded: list of dicts, each with at least {"reason": str,
            "ostium_xyz_mm": [x, y, z]} (§5.5).
        meta: dict with at least runtime_s, a_med_hu, t_vessel_hu, warnings
            (list of str).
        output_path: path to write the JSON file to.

    Returns:
        None. Always writes a valid JSON file, even when `daughters` and
        `excluded` are empty.
    """
    raise NotImplementedError


def visual_check(case: Case, frame: AortaFrame, daughters: list, output_path: str) -> None:
    """Render the required per-case verification PNG (§9.1).

    Args:
        case: loaded `Case` (for the CT and aorta mask arrays).
        frame: `AortaFrame` for this case (for the wall contour).
        daughters: list of accepted-branch dicts as in
            `write_prediction_json` (ostium_xyz_mm, direction_xyz, etc.).
        output_path: path to write the PNG to.

    Returns:
        None. Three panels: coronal MIP, sagittal MIP, and an axial-slice
        strip (one slice per ostium). Must not crash with zero detections.
    """
    raise NotImplementedError


def unrolled_map(case: Case, frame: AortaFrame, daughters: list, excluded: list, output_path: str) -> None:
    """Render the unrolled aortic map (§9.2), the clinician-facing view.

    Args:
        case: loaded `Case`.
        frame: `AortaFrame` for this case (for arc length / clock frame).
        daughters: list of accepted-branch dicts (as above).
        excluded: list of excluded-candidate dicts (as above).
        output_path: path to write the PNG to.

    Returns:
        None. x-axis: arc length (mm) from the superior end of coverage;
        y-axis: clock position (12 -> 3 -> 6 -> 9 -> 12, 12 = anterior);
        each branch a circle sized by its true radius, annotated with
        instance_id, radius, clock position and takeoff angle; excluded
        candidates as hollow grey markers with their reason.
    """
    raise NotImplementedError
