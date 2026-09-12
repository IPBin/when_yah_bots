"""
Stage 6/7 (§5.6, §5.7): candidate connected components, contact patches over
the legal wall, and the multi-seed geodesic race that splits one blob into
one instance per real ostium.

Owner: P1.
"""

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage.graph import MCP_Geometric

from src.io_geom import Case
from src.aorta_frame import AortaFrame
from src.intensity import Profile

_STRUCT_3D = ndimage.generate_binary_structure(3, 3)  # 26-connected


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


def _bbox_slices(mask: np.ndarray, pad: int) -> tuple:
    """Bounding-box slices of a bool mask, padded by `pad` voxels and
    clipped to the array's own extent."""
    coords = np.argwhere(mask)
    lo = np.maximum(coords.min(axis=0) - pad, 0)
    hi = np.minimum(coords.max(axis=0) + pad + 1, np.array(mask.shape))
    return tuple(slice(int(a), int(b)) for a, b in zip(lo, hi))


def _pointer_jump_roots(pred_flat: np.ndarray, n_steps: int) -> np.ndarray:
    """Resolve a forest of predecessor pointers (flat indices, self-pointer
    at roots) to each node's ultimate root, via vectorised pointer doubling
    (no per-voxel Python loop; `n_steps` is O(log(max chain length)))."""
    root = pred_flat.copy()
    for _ in range(n_steps):
        root = root[root]
    return root


def _split_component(
    case: Case,
    profile: Profile,
    comp_mask: np.ndarray,
    patch_mask: np.ndarray,
    iso_mm: float,
) -> list:
    """One candidate component plus its (possibly multi-piece) contact patch
    -> one or more RawBranch, via a multi-seed geodesic race (§5.7)."""
    patch_labeled, n_patches = ndimage.label(patch_mask, structure=_STRUCT_3D)
    if n_patches == 0:
        return []

    bbox = _bbox_slices(comp_mask | patch_mask, pad=2)
    comp_local = comp_mask[bbox]
    patch_local = patch_labeled[bbox]

    # `comp_local` sits up to 2 voxels from its patch (the buffer stripped
    # out around the aorta in `find_raw_branches`), so the MCP cost region
    # must bridge that gap via the patch's own dilation, or the race can
    # never reach the component at all.
    patch_bridge = ndimage.binary_dilation(patch_local > 0, structure=_STRUCT_3D, iterations=2)
    region = comp_local | patch_bridge
    costs = np.where(region, 1.0, np.inf)
    seeds = [tuple(c) for c in np.argwhere(patch_local > 0)]

    mcp = MCP_Geometric(costs, sampling=(iso_mm, iso_mm, iso_mm))
    cum, tb = mcp.find_costs(seeds)
    offsets = np.asarray(mcp.offsets)

    comp_coords = np.argwhere(comp_local)
    if comp_coords.shape[0] == 0 or len(seeds) == 0:
        return []

    if n_patches == 1:
        owner_by_voxel = np.ones(comp_coords.shape[0], dtype=int)
    else:
        shape = comp_local.shape
        flat_size = int(np.prod(shape))
        pred_flat = np.arange(flat_size)  # identity by default (fixed points)

        # Predecessor pointers must cover every voxel MCP actually reached
        # (comp *and* the bridge voxels between comp and its patch) -- not
        # just comp -- or pointer-jumping gets stuck at a bridge voxel
        # instead of chasing all the way back to a real patch seed.
        region_coords = np.argwhere(region)
        tb_at_region = tb[region_coords[:, 0], region_coords[:, 1], region_coords[:, 2]]
        is_root = tb_at_region == -1
        region_flat = np.ravel_multi_index(region_coords.T, shape)

        moved = region_coords[~is_root]
        off = offsets[tb_at_region[~is_root]]
        pred_coords = moved - off
        pred_flat_vals = np.ravel_multi_index(pred_coords.T, shape)
        pred_flat[region_flat[~is_root]] = pred_flat_vals

        comp_flat = np.ravel_multi_index(comp_coords.T, shape)
        n_steps = max(1, int(np.ceil(np.log2(max(2, region_coords.shape[0])))) + 2)
        root_flat = _pointer_jump_roots(pred_flat, n_steps)

        patch_flat_labels = patch_local.ravel()
        owner_by_voxel = patch_flat_labels[root_flat[comp_flat]]

    raw_branches = []
    for patch_id in range(1, n_patches + 1):
        this_patch_local = patch_local == patch_id
        this_voxels_local = comp_coords[owner_by_voxel == patch_id]
        if this_voxels_local.shape[0] == 0:
            continue

        offset = np.array([s.start for s in bbox])
        patch_zyx = np.argwhere(this_patch_local) + offset
        voxels_zyx = this_voxels_local + offset

        this_cum = cum[this_voxels_local[:, 0], this_voxels_local[:, 1], this_voxels_local[:, 2]]
        geodesic_extent_mm = float(np.max(this_cum)) if this_cum.size else 0.0

        patch_area_mm2 = float(patch_zyx.shape[0]) * (iso_mm ** 2)
        hu_values = case.ct_np[voxels_zyx[:, 0], voxels_zyx[:, 1], voxels_zyx[:, 2]]
        mean_hu = float(hu_values.mean())
        hu_ratio = mean_hu / profile.a_med if profile.a_med else 0.0

        raw_branches.append(
            RawBranch(
                patch_zyx=patch_zyx,
                voxels_zyx=voxels_zyx,
                geodesic_extent_mm=geodesic_extent_mm,
                patch_area_mm2=patch_area_mm2,
                mean_hu=mean_hu,
                hu_ratio=hu_ratio,
            )
        )
    return raw_branches


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
    iso_mm = float(cfg["iso_mm"])

    non_aorta = cand & ~ndimage.binary_dilation(case.aorta_np, structure=_STRUCT_3D, iterations=1)
    labeled, n_components = ndimage.label(non_aorta, structure=_STRUCT_3D)

    raw_branches = []
    for comp_id in range(1, n_components + 1):
        comp_mask = labeled == comp_id
        # Dilated by 2, not 1: `non_aorta` already had a 1-voxel buffer
        # around the aorta stripped out (below), so a component sitting
        # right at that buffer's edge is 2 voxels, not 1, from the nearest
        # legal wall voxel.
        comp_dilated = ndimage.binary_dilation(comp_mask, structure=_STRUCT_3D, iterations=2)
        patch_mask = comp_dilated & frame.legal_wall_np
        if not patch_mask.any():
            continue  # doesn't touch the legal wall at all -> not an ostium
        raw_branches.extend(_split_component(case, profile, comp_mask, patch_mask, iso_mm))

    return raw_branches
