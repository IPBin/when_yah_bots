"""
Stage 1 (§5.1): load, validate, crop, resample; voxel <-> physical-mm conversions.

Owner: P2.

Hard rules (see CLAUDE.md / branchseed_playbook.md §3.5 and §6):
- numpy arrays are ALWAYS [z, y, x].
- SimpleITK index/point tuples are ALWAYS (x, y, z).
- This module is the ONLY place that reverses between the two conventions.
- All coordinates that leave this module (returned to callers) are physical mm,
  obtained via TransformContinuousIndexToPhysicalPoint (never rounded to an
  integer voxel index).
"""

import gzip
import logging
import os
import tempfile
from dataclasses import dataclass

import numpy as np
import SimpleITK as sitk
from scipy import ndimage


@dataclass
class Case:
    """A single loaded, cropped, resampled case, ready for the pipeline.

    Attributes:
        ct: SimpleITK image, HU, cropped to ROI, resampled to cfg.iso_mm
            isotropic spacing. Carries a valid origin/spacing/direction, so
            physical-point transforms on this grid are correct in the
            original scanner frame.
        aorta: SimpleITK image, uint8 (0/1), same grid as `ct`.
        ct_np: numpy view of `ct`, shape [z, y, x], dtype float32, units HU.
        aorta_np: numpy view of `aorta`, shape [z, y, x], dtype bool.
        case_id: identifier derived from the input filename.
    """

    ct: sitk.Image
    aorta: sitk.Image
    ct_np: np.ndarray
    aorta_np: np.ndarray
    case_id: str


def _basename_no_ext(path: str) -> str:
    """Return a filename with all extensions stripped (handles .nii.gz)."""
    name = os.path.basename(path)
    for ext in (".nii.gz", ".nii"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return os.path.splitext(name)[0]


def _read_image_tolerating_mislabeled_gzip(path: str, pixel_type) -> sitk.Image:
    """Read a NIfTI image, falling back to gzip decompression if a plain
    `sitk.ReadImage` fails on a file that's actually gzip-compressed but
    doesn't carry a .gz extension (some tools compress in place without
    renaming the file, which trips up ITK's reader).

    Args:
        path: path to the CT or mask volume.
        pixel_type: SimpleITK pixel type to read the image as.

    Returns:
        The loaded sitk.Image.
    """
    try:
        return sitk.ReadImage(path, pixel_type)
    except RuntimeError:
        with open(path, "rb") as f:
            is_gzip = f.read(2) == b"\x1f\x8b"
        if not is_gzip:
            raise
        logging.warning(
            "%s: failed to read directly but is gzip-compressed; decompressing to a temp .nii.gz file.",
            path,
        )
        with open(path, "rb") as f:
            decompressed = gzip.decompress(f.read())
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            tmp.write(decompressed)
            tmp_path = tmp.name
        return sitk.ReadImage(tmp_path, pixel_type)


def _images_share_geometry(a: sitk.Image, b: sitk.Image, tol: float = 1e-3) -> bool:
    """True if two SimpleITK images share size/spacing/origin/direction."""
    if a.GetSize() != b.GetSize():
        return False
    if any(abs(x - y) > tol for x, y in zip(a.GetSpacing(), b.GetSpacing())):
        return False
    if any(abs(x - y) > tol for x, y in zip(a.GetOrigin(), b.GetOrigin())):
        return False
    if any(abs(x - y) > tol for x, y in zip(a.GetDirection(), b.GetDirection())):
        return False
    return True


def load_case(image_path: str, mask_path: str, cfg: dict) -> Case:
    """Load, validate, crop and resample a case.

    Args:
        image_path: path to the CT volume (.nii or .nii.gz), units HU.
        mask_path: path to the binary aorta mask, same physical space as the
            image (validated, and resampled onto the image grid if it
            differs rather than raising).
        cfg: parsed config/default.yaml. Uses cfg['roi_margin_mm'] (mm) and
            cfg['iso_mm'] (mm, isotropic resample spacing).

    Returns:
        A `Case` cropped to the aorta bounding box padded by
        cfg['roi_margin_mm'] mm (clipped to the volume) and resampled to
        cfg['iso_mm'] mm isotropic (linear for the CT, nearest-neighbour for
        the mask).

    Raises:
        Never raises for recoverable issues (mismatched geometry, empty
        mask) -- those are logged as warnings and handled. Only raises for
        unreadable files.
    """
    case_id = _basename_no_ext(image_path)

    # Some NIfTI files carry a direction cosine matrix that's not perfectly
    # orthonormal (floating-point error from whatever tool produced them);
    # ITK's default tolerance rejects those with a RuntimeError, so relax it
    # before any sitk.ReadImage call.
    sitk.ProcessObject.SetGlobalDefaultDirectionTolerance(1e-3)

    image = _read_image_tolerating_mislabeled_gzip(image_path, sitk.sitkFloat32)
    mask = _read_image_tolerating_mislabeled_gzip(mask_path, sitk.sitkUInt8)

    if not _images_share_geometry(image, mask):
        logging.warning(
            "Case %s: image/mask geometry mismatch; resampling mask onto the image grid.",
            case_id,
        )
        mask = sitk.Resample(
            mask,
            image,
            sitk.Transform(),
            sitk.sitkNearestNeighbor,
            0,
            mask.GetPixelID(),
        )

    mask_np = sitk.GetArrayFromImage(mask).astype(bool)
    if not mask_np.any():
        logging.warning("Case %s: aorta mask is empty.", case_id)

    labeled, n_components = ndimage.label(mask_np)
    if n_components > 1:
        logging.warning(
            "Case %s: aorta mask has %d connected components; keeping the largest.",
            case_id,
            n_components,
        )
        sizes = ndimage.sum(mask_np, labeled, index=range(1, n_components + 1))
        largest = int(np.argmax(sizes)) + 1
        mask_np = labeled == largest
        mask = sitk.GetImageFromArray(mask_np.astype(np.uint8))
        mask.CopyInformation(image)

    # --- crop to the aorta bounding box, padded by roi_margin_mm, clipped to the volume ---
    margin_mm = float(cfg["roi_margin_mm"])
    spacing_xyz = np.array(image.GetSpacing())  # (sx, sy, sz)
    size_xyz = np.array(image.GetSize())  # (nx, ny, nz)

    if mask_np.any():
        zs, ys, xs = np.nonzero(mask_np)
        lo_idx_xyz = np.array([xs.min(), ys.min(), zs.min()], dtype=float)
        hi_idx_xyz = np.array([xs.max(), ys.max(), zs.max()], dtype=float)
    else:
        lo_idx_xyz = np.zeros(3)
        hi_idx_xyz = size_xyz.astype(float) - 1

    margin_vox = margin_mm / spacing_xyz
    lo_idx_xyz = np.floor(lo_idx_xyz - margin_vox).astype(int)
    hi_idx_xyz = np.ceil(hi_idx_xyz + margin_vox).astype(int)
    lo_idx_xyz = np.clip(lo_idx_xyz, 0, size_xyz - 1)
    hi_idx_xyz = np.clip(hi_idx_xyz, 0, size_xyz - 1)
    crop_size_xyz = (hi_idx_xyz - lo_idx_xyz + 1).tolist()

    image_cropped = sitk.RegionOfInterest(image, crop_size_xyz, lo_idx_xyz.tolist())
    mask_cropped = sitk.RegionOfInterest(mask, crop_size_xyz, lo_idx_xyz.tolist())

    # --- resample to iso_mm isotropic: linear for CT, nearest-neighbour for the mask ---
    iso_mm = float(cfg["iso_mm"])
    out_spacing = (iso_mm, iso_mm, iso_mm)
    in_size = np.array(image_cropped.GetSize())
    in_spacing = np.array(image_cropped.GetSpacing())
    out_size = np.ceil(in_size * in_spacing / iso_mm).astype(int).tolist()

    resample = sitk.ResampleImageFilter()
    resample.SetOutputSpacing(out_spacing)
    resample.SetSize(out_size)
    resample.SetOutputOrigin(image_cropped.GetOrigin())
    resample.SetOutputDirection(image_cropped.GetDirection())
    resample.SetTransform(sitk.Transform())
    resample.SetDefaultPixelValue(-1000.0)
    resample.SetInterpolator(sitk.sitkLinear)
    ct_resampled = resample.Execute(image_cropped)

    resample.SetDefaultPixelValue(0)
    resample.SetInterpolator(sitk.sitkNearestNeighbor)
    aorta_resampled = resample.Execute(mask_cropped)
    aorta_resampled = sitk.Cast(aorta_resampled, sitk.sitkUInt8)

    ct_np = sitk.GetArrayFromImage(ct_resampled).astype(np.float32)
    aorta_np = sitk.GetArrayFromImage(aorta_resampled).astype(bool)

    return Case(
        ct=ct_resampled,
        aorta=aorta_resampled,
        ct_np=ct_np,
        aorta_np=aorta_np,
        case_id=case_id,
    )


def idx_to_mm(case: Case, zyx) -> np.ndarray:
    """Convert one or many voxel indices (numpy convention) to physical mm.

    Args:
        case: the `Case` whose grid (`case.ct`) defines the transform.
        zyx: a length-3 sequence (z, y, x) in voxel units (may be
            fractional / sub-voxel), or an (N, 3) array of such indices.

    Returns:
        np.ndarray of shape (3,) or (N, 3), physical coordinates in mm, in
        SimpleITK's (x, y, z) axis order per point, using
        TransformContinuousIndexToPhysicalPoint (sub-voxel, never rounded).
    """
    arr = np.asarray(zyx, dtype=float)
    single = arr.ndim == 1
    if single:
        arr = arr[np.newaxis, :]

    out = np.empty_like(arr)
    for i, (z, y, x) in enumerate(arr):
        # numpy [z,y,x] -> SimpleITK continuous index (x,y,z)
        out[i] = case.ct.TransformContinuousIndexToPhysicalPoint((float(x), float(y), float(z)))

    return out[0] if single else out


def mm_to_idx(case: Case, xyz_mm) -> np.ndarray:
    """Convert one or many physical mm points to voxel indices (numpy convention).

    Args:
        case: the `Case` whose grid (`case.ct`) defines the transform.
        xyz_mm: a length-3 sequence (x, y, z) in physical mm, or an (N, 3)
            array of such points.

    Returns:
        np.ndarray of shape (3,) or (N, 3), float voxel indices in [z, y, x]
        order (numpy convention), using TransformPhysicalPointToContinuousIndex.
    """
    arr = np.asarray(xyz_mm, dtype=float)
    single = arr.ndim == 1
    if single:
        arr = arr[np.newaxis, :]

    out = np.empty_like(arr)
    for i, (x, y, z) in enumerate(arr):
        # SimpleITK continuous index (x,y,z) -> numpy [z,y,x]
        cix, ciy, ciz = case.ct.TransformPhysicalPointToContinuousIndex((float(x), float(y), float(z)))
        out[i] = (ciz, ciy, cix)

    return out[0] if single else out
