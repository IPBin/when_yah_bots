"""
Stage 8 (§5.8): per-branch ostium, proximal path, seed, direction and
radius, all in physical mm.

Owner: P1.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage.graph import MCP_Geometric

from src.io_geom import Case, idx_to_mm
from src.aorta_frame import AortaFrame, outward_normal
from src.intensity import Profile
from src.instances import RawBranch, _bbox_slices

_STRUCT_3D = ndimage.generate_binary_structure(3, 3)  # 26-connected


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


def _resample_by_arclength(points_mm: np.ndarray, step_mm: float) -> tuple:
    """Resample an ordered polyline to uniform arc-length steps.

    Returns:
        (points, arclen_mm): `points` is (S, 3) physical mm, `arclen_mm` is
        (S,) arc length in mm from `points_mm[0]` to each resampled point.
    """
    if points_mm.shape[0] == 1:
        return points_mm.copy(), np.zeros(1)

    seg = np.linalg.norm(np.diff(points_mm, axis=0), axis=1)
    arclen = np.concatenate([[0.0], np.cumsum(seg)])
    total = arclen[-1]
    if total < 1e-9:
        return points_mm[:1].copy(), np.zeros(1)

    n_steps = max(1, int(np.floor(total / step_mm)))
    targets = np.arange(n_steps + 1) * step_mm
    targets = targets[targets <= total]
    if targets[-1] < total - 1e-9:
        targets = np.append(targets, total)

    out = np.empty((len(targets), 3))
    for axis in range(3):
        out[:, axis] = np.interp(targets, arclen, points_mm[:, axis])
    return out, targets


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
            pca_window_mm, seed_snap_mm, patch_bridge_mm
            (mm, mm, mm, [mm,mm], mm, mm).

    Returns:
        A `BranchGeom` per the dataclass docstring above. The Euclidean
        distance transform (EDT) is computed on `raw.voxels_zyx`; the path
        is a minimum-cost path from the ostium to the voxel at maximum
        geodesic distance from the patch (capped at cfg['trace_max_mm']),
        with cost 1/(EDT + 0.1) so it hugs the lumen centre.
    """
    iso_mm = float(cfg["iso_mm"])
    trace_max_mm = float(cfg["trace_max_mm"])
    seed_arc_mm = float(cfg["seed_arc_mm"])
    path_step_mm = float(cfg["path_step_mm"])
    pca_lo, pca_hi = cfg["pca_window_mm"]
    seed_snap_mm = float(cfg["seed_snap_mm"])
    # Same real-data gap as `instances.find_raw_branches`'s max_bridge_iters
    # -- see config/default.yaml patch_bridge_mm for the rationale. Used
    # here only to bridge `raw.patch_zyx`/`raw.voxels_zyx` (already fixed
    # by the time this runs) for path-finding, so a generous fixed cap is
    # safe -- it cannot inflate `raw.patch_area_mm2` the way a fixed
    # dilation in `find_raw_branches` did (that one is adaptive, see there).
    bridge_iters = max(1, round(float(cfg["patch_bridge_mm"]) / iso_mm))

    # --- ostium: patch centroid, nudged half a voxel out to the true wall
    # surface (the mask boundary sits between the last inside voxel centre
    # and the first outside one, so the "mid-wall" point is ~0.5 voxel
    # beyond the last-inside centroid, along the outward normal) ---
    patch_centroid_zyx = raw.patch_zyx.mean(axis=0)
    ostium_raw_mm = idx_to_mm(case, patch_centroid_zyx)
    normal = outward_normal(frame, patch_centroid_zyx)
    ostium_mm = ostium_raw_mm + 0.5 * iso_mm * normal

    # --- local crop covering the branch body plus its contact patch ---
    shape = case.ct_np.shape
    body_full = np.zeros(shape, dtype=bool)
    body_full[raw.voxels_zyx[:, 0], raw.voxels_zyx[:, 1], raw.voxels_zyx[:, 2]] = True
    patch_full = np.zeros(shape, dtype=bool)
    patch_full[raw.patch_zyx[:, 0], raw.patch_zyx[:, 1], raw.patch_zyx[:, 2]] = True

    bbox = _bbox_slices(body_full | patch_full, pad=bridge_iters)
    body_local = body_full[bbox]
    patch_local = patch_full[bbox]
    offset = np.array([s.start for s in bbox])

    # Same buffer-bridging issue as `instances._split_component`: the patch
    # (aortic wall) and the branch body sit up to `bridge_iters` voxels apart
    # because `find_raw_branches` strips a 1-voxel halo around the aorta,
    # plus real segmentation/partial-volume gaps (cfg['patch_bridge_mm']).
    patch_bridge = ndimage.binary_dilation(patch_local, structure=_STRUCT_3D, iterations=bridge_iters)
    region_local = body_local | patch_bridge

    edt_local = ndimage.distance_transform_edt(body_local, sampling=(iso_mm,) * 3)

    seeds = [tuple(c) for c in np.argwhere(patch_local)]

    # --- target: voxel at max geodesic distance from the patch, capped ---
    extent_costs = np.where(region_local, 1.0, np.inf)
    mcp_extent = MCP_Geometric(extent_costs, sampling=(iso_mm,) * 3)
    cum_extent, _ = mcp_extent.find_costs(seeds)

    body_coords = np.argwhere(body_local)
    body_dist = cum_extent[body_coords[:, 0], body_coords[:, 1], body_coords[:, 2]]
    within_cap = body_dist <= trace_max_mm
    if within_cap.any():
        candidate_idx = int(np.argmax(np.where(within_cap, body_dist, -np.inf)))
    else:
        candidate_idx = int(np.argmin(body_dist))  # nothing within cap: take the closest
    target_local = tuple(int(v) for v in body_coords[candidate_idx])

    # --- minimum-cost path from the patch (ostium) to the target, hugging
    # the lumen centre via cost 1/(EDT + 0.1) ---
    path_costs = np.where(region_local, 1.0 / (edt_local + 0.1), np.inf)
    mcp_path = MCP_Geometric(path_costs, sampling=(iso_mm,) * 3)
    mcp_path.find_costs(seeds, ends=[target_local])
    path_local = np.array(mcp_path.traceback(target_local))  # (P,3) local voxel coords

    path_zyx = path_local + offset
    path_mm_raw = idx_to_mm(case, path_zyx.astype(float))
    # Replace the path's own start (whichever patch voxel MCP happened to
    # start from) with the true sub-voxel mid-wall ostium point, so the
    # arc-length parameterisation used for the seed and direction below
    # starts exactly at `ostium_mm`.
    path_mm_raw = np.vstack([ostium_mm[np.newaxis, :], path_mm_raw])

    path_mm, arclen_vals = _resample_by_arclength(path_mm_raw, path_step_mm)

    total_len = float(arclen_vals[-1])
    straight = float(np.linalg.norm(path_mm[-1] - ostium_mm))
    tortuosity = total_len / straight if straight > 1e-9 else 1.0

    # --- seed: path point at seed_arc_mm, snapped to the local EDT maximum ---
    seed_idx = int(np.argmin(np.abs(arclen_vals - seed_arc_mm)))
    seed_guess_mm = path_mm[seed_idx]

    body_mm = idx_to_mm(case, (body_coords + offset).astype(float))
    dist_to_guess = np.linalg.norm(body_mm - seed_guess_mm[np.newaxis, :], axis=1)
    within_snap = dist_to_guess <= seed_snap_mm
    search_pool = np.where(within_snap)[0] if within_snap.any() else np.arange(len(dist_to_guess))
    edt_at_body = edt_local[body_coords[:, 0], body_coords[:, 1], body_coords[:, 2]]
    best = search_pool[int(np.argmax(edt_at_body[search_pool]))]

    seed_voxel = body_coords[best]
    seed_mm = idx_to_mm(case, (seed_voxel + offset).astype(float))
    radius_mm = float(edt_local[seed_voxel[0], seed_voxel[1], seed_voxel[2]])

    # --- direction: PCA of the path within pca_window_mm, away from the ostium ---
    in_window = (arclen_vals >= pca_lo) & (arclen_vals <= pca_hi)
    window_pts = path_mm[in_window]
    if window_pts.shape[0] < 2:
        window_pts = np.vstack([ostium_mm, path_mm[-1]])
    centered = window_pts - window_pts.mean(axis=0)
    _, _, vt = np.linalg.svd(centered, full_matrices=False)
    direction = vt[0]
    if np.dot(direction, window_pts[-1] - ostium_mm) < 0:
        direction = -direction
    norm = np.linalg.norm(direction)
    direction = direction / norm if norm > 1e-9 else direction

    return BranchGeom(
        ostium_mm=ostium_mm,
        seed_mm=seed_mm,
        direction=direction,
        radius_mm=radius_mm,
        path_mm=path_mm,
        tortuosity=float(tortuosity),
    )
