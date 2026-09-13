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
        mean_cross_section_mm2: mean cross-sectional area (mm^2) along the
            instance's length, estimated as
            (voxel_count * voxel_volume_mm3) / geodesic_extent_mm. A real
            proximal branch stays roughly tube-shaped (celiac/SMA top out
            around ~3.5 mm radius, i.e. ~38 mm^2), so a candidate whose
            average cross-section is far larger than any plausible vessel
            is a blobby leak into bone/an organ, not a branch -- this is
            what `gate.accept`'s `max_mean_cross_section_mm2` check rejects.
    """

    patch_zyx: np.ndarray
    voxels_zyx: np.ndarray
    geodesic_extent_mm: float
    patch_area_mm2: float
    mean_hu: float
    hu_ratio: float
    mean_cross_section_mm2: float


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
    bridge_iters: int,
    outer_offset: np.ndarray = None,
) -> list:
    """One candidate component plus its (possibly multi-piece) contact patch
    -> one or more RawBranch, via a multi-seed geodesic race (§5.7).

    `comp_mask`/`patch_mask` may already be cropped to a local bounding box
    by the caller (`find_raw_branches` crops before this is ever called, to
    keep the dilation/MCP work below off the full case volume); `outer_offset`
    is that crop's own [z,y,x] origin, added on top of the bbox this function
    finds within its own (possibly already-local) inputs, so the returned
    `patch_zyx`/`voxels_zyx` are always in the full case's voxel indices.
    `bridge_iters` (voxels, derived from cfg['patch_bridge_mm']) is the
    dilation radius used to bridge the gap between a component and its own
    contact patch -- see `find_raw_branches` for why this must be tunable
    rather than a hardcoded value.
    """
    patch_labeled, n_patches = ndimage.label(patch_mask, structure=_STRUCT_3D)
    if n_patches == 0:
        return []

    bbox = _bbox_slices(comp_mask | patch_mask, pad=bridge_iters)
    comp_local = comp_mask[bbox]
    patch_local = patch_labeled[bbox]

    # `comp_local` sits up to `bridge_iters` voxels from its patch (the
    # buffer stripped out around the aorta in `find_raw_branches`, plus real
    # segmentation/partial-volume noise at the aortic wall on real cases),
    # so the MCP cost region must bridge that gap via the patch's own
    # dilation, or the race can never reach the component at all.
    patch_bridge = ndimage.binary_dilation(patch_local > 0, structure=_STRUCT_3D, iterations=bridge_iters)
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
        if outer_offset is not None:
            offset = offset + outer_offset
        patch_zyx = np.argwhere(this_patch_local) + offset
        voxels_zyx = this_voxels_local + offset

        this_cum = cum[this_voxels_local[:, 0], this_voxels_local[:, 1], this_voxels_local[:, 2]]
        geodesic_extent_mm = float(np.max(this_cum)) if this_cum.size else 0.0

        patch_area_mm2 = float(patch_zyx.shape[0]) * (iso_mm ** 2)
        hu_values = case.ct_np[voxels_zyx[:, 0], voxels_zyx[:, 1], voxels_zyx[:, 2]]
        mean_hu = float(hu_values.mean())
        hu_ratio = mean_hu / profile.a_med if profile.a_med else 0.0

        # See RawBranch.mean_cross_section_mm2 docstring: total voxel volume
        # divided by the geodesic extent approximates the average tube
        # cross-section, which is what separates a real thin branch from a
        # blobby leak into bone/an enhancing organ (both can pass the HU and
        # min-extent checks alone -- see gate.accept).
        voxel_volume_mm3 = iso_mm ** 3
        mean_cross_section_mm2 = (
            (voxels_zyx.shape[0] * voxel_volume_mm3) / geodesic_extent_mm
            if geodesic_extent_mm > 0
            else float(voxels_zyx.shape[0]) * voxel_volume_mm3
        )

        raw_branches.append(
            RawBranch(
                patch_zyx=patch_zyx,
                voxels_zyx=voxels_zyx,
                geodesic_extent_mm=geodesic_extent_mm,
                patch_area_mm2=patch_area_mm2,
                mean_hu=mean_hu,
                hu_ratio=hu_ratio,
                mean_cross_section_mm2=mean_cross_section_mm2,
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
    max_branch_voxels = int(cfg.get("max_branch_voxels", 50000))
    # `patch_bridge_mm` (real-data gap between a candidate component and its
    # own contact patch, after the 1-voxel aorta-mask buffer stripped below)
    # converted to a voxel dilation radius, never below 1.
    bridge_iters = max(1, round(float(cfg["patch_bridge_mm"]) / iso_mm))

    non_aorta = cand & ~ndimage.binary_dilation(case.aorta_np, structure=_STRUCT_3D, iterations=1)
    labeled, n_components = ndimage.label(non_aorta, structure=_STRUCT_3D)

    # Both computed once, over the whole labelled volume, rather than
    # per-component: bincount avoids an O(volume) `labeled == comp_id` size
    # check for every component, and find_objects gives each component's
    # bounding box directly instead of an O(volume) argwhere per component.
    component_sizes = np.bincount(labeled.ravel(), minlength=n_components + 1)
    component_bboxes = ndimage.find_objects(labeled)

    raw_branches = []
    for comp_id in range(1, n_components + 1):
        if component_sizes[comp_id] > max_branch_voxels:
            # Too large to be a real branch -- a leak into bone or an
            # enhancing organ, not worth a single expensive operation.
            continue

        # Crop to this component's own bounding box (padded) *before* any
        # dilation: `comp_mask`/`comp_dilated` used to be full case-volume
        # arrays even for a branch stub a few dozen voxels across, which
        # made the dilation below (and the legal-wall AND) the dominant
        # cost of this loop.
        raw_bbox = component_bboxes[comp_id - 1]
        bbox = tuple(
            slice(max(s.start - bridge_iters, 0), min(s.stop + bridge_iters, dim))
            for s, dim in zip(raw_bbox, labeled.shape)
        )
        comp_local = labeled[bbox] == comp_id
        legal_wall_local = frame.legal_wall_np[bbox]

        # Dilated by `bridge_iters`, not 1: `non_aorta` already had a
        # 1-voxel buffer around the aorta stripped out (above), and real
        # cases show additional segmentation/partial-volume gaps between a
        # component and the nearest legal wall voxel (cfg['patch_bridge_mm']
        # -- see config/default.yaml for the real-data rationale).
        comp_dilated_local = ndimage.binary_dilation(comp_local, structure=_STRUCT_3D, iterations=bridge_iters)
        patch_mask_local = comp_dilated_local & legal_wall_local
        if not patch_mask_local.any():
            continue  # doesn't touch the legal wall at all -> not an ostium

        outer_offset = np.array([s.start for s in bbox])
        raw_branches.extend(
            _split_component(
                case, profile, comp_local, patch_mask_local, iso_mm, bridge_iters, outer_offset=outer_offset
            )
        )

    return raw_branches
