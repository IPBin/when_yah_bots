"""
Stage 4/5 (§5.4, §5.5): aorta centreline, wall surface, outward normals,
clock/arc-length frame, and the forbidden surface (cropped end caps + iliac
fork).

Owner: P1.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from src.io_geom import Case, idx_to_mm

_STRUCT_2D = ndimage.generate_binary_structure(2, 2)  # 8-connected


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

    # Implementation-only fields, not part of the §6 cross-module contract.
    # They let `outward_normal` / `clock_and_arclen` work from `frame` alone
    # (both need the per-slice centreline; `outward_normal` also needs a
    # coordinate transform to turn its raw voxel index into physical mm).
    _case: Case = field(repr=False, compare=False)
    _k_axis: np.ndarray = field(repr=False, compare=False)  # (N,) int, ascending slice index
    _centreline_by_k_mm: np.ndarray = field(repr=False, compare=False)  # (N,3) xyz mm, aligned with _k_axis
    _arclen_by_row: np.ndarray = field(repr=False, compare=False)  # (N,) mm, aligned with centreline_mm


def _largest_cc_centroid_2d(slice_bool: np.ndarray):
    """Centroid (y, x) in voxel units of the largest connected component in
    a 2D bool slice, or None if the slice is empty."""
    labeled, n = ndimage.label(slice_bool, structure=_STRUCT_2D)
    if n == 0:
        return None
    sizes = ndimage.sum(slice_bool, labeled, index=np.arange(1, n + 1))
    largest = int(np.argmax(sizes)) + 1
    ys, xs = np.nonzero(labeled == largest)
    return float(ys.mean()), float(xs.mean())


def _has_comparable_components_2d(slice_bool: np.ndarray, size_ratio: float) -> bool:
    """True if a 2D bool slice has >=2 components whose sizes are within
    `size_ratio` of each other (the iliac-fork signature)."""
    labeled, n = ndimage.label(slice_bool, structure=_STRUCT_2D)
    if n < 2:
        return False
    sizes = np.sort(ndimage.sum(slice_bool, labeled, index=np.arange(1, n + 1)))[::-1]
    if sizes[0] <= 0:
        return False
    return bool(sizes[1] / sizes[0] >= size_ratio)


def _nearest_k_index(k_axis: np.ndarray, k_query: np.ndarray) -> np.ndarray:
    """Index into `k_axis` of the entry nearest each value in `k_query`."""
    pos = np.clip(np.searchsorted(k_axis, k_query), 0, len(k_axis) - 1)
    pos_prev = np.clip(pos - 1, 0, len(k_axis) - 1)
    use_prev = np.abs(k_axis[pos_prev] - k_query) < np.abs(k_axis[pos] - k_query)
    return np.where(use_prev, pos_prev, pos)


def build_frame(case: Case, cfg: dict) -> AortaFrame:
    """Build the aorta's centreline, wall and forbidden-surface frame.

    Args:
        case: loaded `Case` (aorta_np bool, [z,y,x], cfg['iso_mm'] isotropic
            grid, plus the SimpleITK `case.aorta` image for direction
            cosines / physical transforms).
        cfg: parsed config. Uses centreline_smooth_mm (mm), endcap_mm (mm),
            endcap_angle_deg (deg), iliac_margin_mm (mm), and
            iliac_fork_size_ratio (unitless, in [0, 1]).

    Returns:
        An `AortaFrame` per the dataclass docstring above.
    """
    aorta = case.aorta_np
    iso_mm = float(cfg["iso_mm"])

    k_has_mask = aorta.any(axis=(1, 2))
    present_k = np.nonzero(k_has_mask)[0]
    if present_k.size == 0:
        raise ValueError("build_frame: aorta mask is empty; cannot build a frame")
    kmin, kmax = int(present_k.min()), int(present_k.max())

    # --- centreline: per-slice centroid of the largest 2D component ---
    k_axis = []
    centroids_zyx = []
    for k in present_k:
        c = _largest_cc_centroid_2d(aorta[k])
        if c is None:
            continue
        k_axis.append(int(k))
        centroids_zyx.append((float(k), c[0], c[1]))
    k_axis = np.asarray(k_axis, dtype=float)
    centroids_zyx = np.asarray(centroids_zyx, dtype=float)  # (N,3) z,y,x, ascending k

    window = max(1, round(float(cfg["centreline_smooth_mm"]) / iso_mm))
    centroids_zyx[:, 1] = ndimage.uniform_filter1d(centroids_zyx[:, 1], size=window, mode="nearest")
    centroids_zyx[:, 2] = ndimage.uniform_filter1d(centroids_zyx[:, 2], size=window, mode="nearest")

    centreline_by_k_mm = idx_to_mm(case, centroids_zyx)  # (N,3) xyz mm, ascending k

    # SimpleITK's physical space is LPS regardless of direction cosines, so
    # +z is always superior -- ordering by physical z is robust even on a
    # rotated grid.
    order = np.argsort(-centreline_by_k_mm[:, 2])
    centreline_mm = centreline_by_k_mm[order]

    seg_len = np.linalg.norm(np.diff(centreline_mm, axis=0), axis=1)
    arclen_by_row = np.concatenate([[0.0], np.cumsum(seg_len)])

    if len(k_axis) >= 2:
        tangent_by_k = np.gradient(centreline_by_k_mm, axis=0)
    else:
        tangent_by_k = np.zeros_like(centreline_by_k_mm)
    tnorm = np.linalg.norm(tangent_by_k, axis=1, keepdims=True)
    tnorm[tnorm < 1e-9] = 1.0
    tangent_by_k = tangent_by_k / tnorm

    # --- wall surface ---
    wall_np = aorta & ~ndimage.binary_erosion(aorta, iterations=1)
    wall_zyx = np.argwhere(wall_np)  # (M,3) z,y,x

    excluded = []
    forbid = np.zeros(len(wall_zyx), dtype=bool)

    if wall_zyx.shape[0] > 0:
        wall_mm = idx_to_mm(case, wall_zyx.astype(float))
        nearest = _nearest_k_index(k_axis, wall_zyx[:, 0].astype(float))
        centre_mm_at_wall = centreline_by_k_mm[nearest]

        normals = wall_mm - centre_mm_at_wall
        nnorm = np.linalg.norm(normals, axis=1, keepdims=True)
        nnorm[nnorm < 1e-9] = 1.0
        normals = normals / nnorm

        tangents_at_wall = tangent_by_k[nearest]
        cosang = np.abs(np.sum(normals * tangents_at_wall, axis=1))
        angle_deg = np.degrees(np.arccos(np.clip(cosang, -1.0, 1.0)))

        endcap_mm = float(cfg["endcap_mm"])
        endcap_angle_deg = float(cfg["endcap_angle_deg"])

        near_top = (wall_zyx[:, 0] - kmin) * iso_mm <= endcap_mm
        near_bottom = (kmax - wall_zyx[:, 0]) * iso_mm <= endcap_mm
        cap_by_angle = angle_deg <= endcap_angle_deg
        cap_mask = near_top | near_bottom | cap_by_angle
        forbid |= cap_mask

        if cap_mask.any():
            median_z = float(np.median(centreline_by_k_mm[:, 2]))
            cap_pts = wall_mm[cap_mask]
            is_superior = cap_pts[:, 2] >= median_z
            if is_superior.any():
                excluded.append({
                    "reason": "superior_end_cap",
                    "ostium_xyz_mm": cap_pts[is_superior].mean(axis=0).tolist(),
                })
            if (~is_superior).any():
                excluded.append({
                    "reason": "inferior_end_cap",
                    "ostium_xyz_mm": cap_pts[~is_superior].mean(axis=0).tolist(),
                })

        # --- iliac fork: first slice, scanning superior -> inferior, where
        # the mask splits into two comparably sized components ---
        size_ratio = float(cfg["iliac_fork_size_ratio"])
        iliac_margin_mm = float(cfg["iliac_margin_mm"])
        scan_order = np.argsort(-centreline_by_k_mm[:, 2])  # superior -> inferior
        fork_row = None
        for i in scan_order:
            if _has_comparable_components_2d(aorta[int(k_axis[i])], size_ratio):
                fork_row = i
                break

        if fork_row is not None:
            fork_z_mm = float(centreline_by_k_mm[fork_row, 2])
            boundary_z = fork_z_mm + iliac_margin_mm  # pull the cut margin above the fork
            below_fork = wall_mm[:, 2] <= boundary_z
            forbid |= below_fork
            excluded.append({
                "reason": "iliac_bifurcation",
                "ostium_xyz_mm": centreline_by_k_mm[fork_row].tolist(),
            })

    legal_wall_np = np.zeros_like(wall_np, dtype=bool)
    if wall_zyx.shape[0] > 0:
        keep = ~forbid
        legal_wall_np[wall_zyx[keep, 0], wall_zyx[keep, 1], wall_zyx[keep, 2]] = True

    return AortaFrame(
        centreline_mm=centreline_mm,
        wall_np=wall_np,
        legal_wall_np=legal_wall_np,
        excluded=excluded,
        _case=case,
        _k_axis=k_axis,
        _centreline_by_k_mm=centreline_by_k_mm,
        _arclen_by_row=arclen_by_row,
    )


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
    zyx_arr = np.asarray(zyx, dtype=float)
    nearest = _nearest_k_index(frame._k_axis, np.asarray([zyx_arr[0]]))[0]
    centre_mm = frame._centreline_by_k_mm[nearest]
    wall_mm = idx_to_mm(frame._case, zyx_arr)
    vec = wall_mm - centre_mm
    norm = np.linalg.norm(vec)
    if norm < 1e-9:
        return np.zeros(3)
    return vec / norm


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
    xyz = np.asarray(xyz_mm, dtype=float)
    offsets = frame.centreline_mm - xyz[np.newaxis, :]
    idx = int(np.argmin(np.linalg.norm(offsets, axis=1)))
    centre = frame.centreline_mm[idx]

    # SimpleITK physical points are LPS: x -> left, y -> posterior, z ->
    # superior, always, regardless of the source image's direction cosines.
    # So anterior = -y, left = +x, directly on these coordinates.
    dx = xyz[0] - centre[0]
    dy = xyz[1] - centre[1]
    theta_deg = np.degrees(np.arctan2(dx, -dy)) % 360.0
    clock_hours = theta_deg / 30.0
    arclen_mm = float(frame._arclen_by_row[idx])
    return clock_hours, arclen_mm
