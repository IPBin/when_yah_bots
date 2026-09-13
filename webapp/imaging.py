"""On-demand imagery for the review screen: a single axial slice as PNG bytes,
plus a small bounded cache of loaded `Case` objects (loading is the slow step,
and the slice endpoint may be hit repeatedly while a clinician scrubs through
a volume).

The coronal/sagittal MIP + arrow overlay and the unrolled arclength/clock map
are NOT regenerated here -- those are rendered once per run by
`src.report.visual_check`/`unrolled_map` and served as static files by
`webapp/server.py`. This module only covers the one thing report.py doesn't
already produce: an arbitrary single slice for interactive scrubbing.
"""

import io
from collections import OrderedDict

import matplotlib

matplotlib.use("Agg")
import matplotlib.image

from src.io_geom import load_case

# Same HU display window src/report.py's `_draw_mip_panel` uses, so a slice
# viewed here looks consistent with the coronal/sagittal/axial-crop panels in
# the overlay PNG.
_HU_VMIN = -100
_HU_VMAX = 500

_CACHE_CAPACITY = 2
_cache = OrderedDict()  # case_id -> Case


def get_case(case_id: str, image_path: str, mask_path: str, cfg: dict):
    """Return a cached `Case`, loading it if necessary (LRU, capped size).

    Args:
        case_id: opaque webapp case identifier, used only as the cache key.
        image_path: path to the CT volume (mm-scale physical grid preserved
            by `load_case`).
        mask_path: path to the binary aorta mask.
        cfg: parsed config dict (passed straight through to `load_case`).

    Returns:
        `src.io_geom.Case` for this case_id.
    """
    if case_id in _cache:
        _cache.move_to_end(case_id)
        return _cache[case_id]
    case = load_case(image_path, mask_path, cfg)
    _cache[case_id] = case
    _cache.move_to_end(case_id)
    if len(_cache) > _CACHE_CAPACITY:
        _cache.popitem(last=False)
    return case


def slice_count(case) -> int:
    """Number of axial slices (voxels along the array's z axis) in `case`."""
    return case.ct_np.shape[0]


def render_slice_png(case, z_index: int) -> bytes:
    """Render one axial slice of `case.ct_np` as HU-windowed grayscale PNG bytes.

    Args:
        case: a loaded `src.io_geom.Case`.
        z_index: voxel index along the array's z axis (0-based, clamped to
            the valid range). A raw voxel index, not physical mm -- this is
            a UI slice-scrubber convenience, not a pipeline coordinate; the
            client independently gets an mm label for display via the
            case's spacing/shape metadata, never computed here.

    Returns:
        PNG-encoded bytes, one 8-bit grayscale slice.
    """
    z_index = max(0, min(z_index, case.ct_np.shape[0] - 1))
    slice_hu = case.ct_np[z_index]
    buf = io.BytesIO()
    matplotlib.image.imsave(buf, slice_hu, cmap="gray", vmin=_HU_VMIN, vmax=_HU_VMAX, format="png")
    return buf.getvalue()
