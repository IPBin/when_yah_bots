"""Tests for src/io_geom.py — round-trip coordinate conversions (§10.6 prompt 2)."""

import math
import shutil

import numpy as np
import SimpleITK as sitk
import yaml

from src.io_geom import Case, idx_to_mm, mm_to_idx, load_case


def _load_cfg():
    with open("config/default.yaml") as f:
        return yaml.safe_load(f)


def _make_case(spacing=(1.0, 1.0, 1.0), direction=None) -> Case:
    """Build a small synthetic Case without going through load_case, so the
    round-trip test is independent of the cropping/resampling logic."""
    shape_xyz = (20, 20, 20)  # (nx, ny, nz)
    ct_np = np.full((shape_xyz[2], shape_xyz[1], shape_xyz[0]), -1000.0, dtype=np.float32)
    aorta_np = np.zeros_like(ct_np, dtype=np.uint8)
    aorta_np[8:12, 8:12, 8:12] = 1

    ct = sitk.GetImageFromArray(ct_np)
    ct.SetSpacing(spacing)
    if direction is not None:
        ct.SetDirection(direction)

    aorta = sitk.GetImageFromArray(aorta_np)
    aorta.CopyInformation(ct)
    aorta = sitk.Cast(aorta, sitk.sitkUInt8)

    return Case(ct=ct, aorta=aorta, ct_np=ct_np, aorta_np=aorta_np.astype(bool), case_id="synthetic")


def test_round_trip_identity_grid():
    case = _make_case()
    zyx = np.array([5.3, 10.7, 2.1])
    mm = idx_to_mm(case, zyx)
    back = mm_to_idx(case, mm)
    assert np.allclose(zyx, back, atol=0.5)


def test_round_trip_many_points():
    case = _make_case()
    zyx = np.array([[5.3, 10.7, 2.1], [0.0, 0.0, 0.0], [15.9, 3.2, 18.4]])
    mm = idx_to_mm(case, zyx)
    back = mm_to_idx(case, mm)
    assert np.allclose(zyx, back, atol=0.5)


def test_round_trip_anisotropic_and_rotated():
    """§10.6 prompt 2: round trip must still hold with spacing (0.7,0.7,2.0)
    and a non-identity direction matrix."""
    angle = math.radians(30.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    # rotation about the z axis, row-major 3x3 flattened
    direction = (
        cos_a, -sin_a, 0.0,
        sin_a, cos_a, 0.0,
        0.0, 0.0, 1.0,
    )
    case = _make_case(spacing=(0.7, 0.7, 2.0), direction=direction)

    zyx = np.array([5.3, 10.7, 2.1])
    mm = idx_to_mm(case, zyx)
    back = mm_to_idx(case, mm)
    assert np.allclose(zyx, back, atol=0.5)

    zyx_many = np.array([[5.3, 10.7, 2.1], [0.0, 0.0, 0.0], [15.9, 3.2, 18.4]])
    mm_many = idx_to_mm(case, zyx_many)
    back_many = mm_to_idx(case, mm_many)
    assert np.allclose(zyx_many, back_many, atol=0.5)


def _write_case_files(tmp_path, image_ext, mask_ext):
    """Write a real image + mask through SimpleITK's own .nii.gz writer,
    then copy the (still gzip-compressed) bytes to files carrying whatever
    extension the test wants -- reproducing a file that's gzip-compressed
    but not named accordingly."""
    shape_xyz = (20, 20, 20)
    ct_np = np.full((shape_xyz[2], shape_xyz[1], shape_xyz[0]), -1000.0, dtype=np.float32)
    aorta_np = np.zeros_like(ct_np, dtype=np.uint8)
    aorta_np[8:12, 8:12, 8:12] = 1

    ct = sitk.GetImageFromArray(ct_np)
    aorta = sitk.GetImageFromArray(aorta_np)
    aorta.CopyInformation(ct)

    real_image_path = str(tmp_path / "image.nii.gz")
    real_mask_path = str(tmp_path / "mask.nii.gz")
    sitk.WriteImage(ct, real_image_path)
    sitk.WriteImage(sitk.Cast(aorta, sitk.sitkUInt8), real_mask_path)

    image_path = str(tmp_path / f"image{image_ext}")
    mask_path = str(tmp_path / f"mask{mask_ext}")
    if image_path != real_image_path:
        shutil.copy(real_image_path, image_path)
    if mask_path != real_mask_path:
        shutil.copy(real_mask_path, mask_path)
    return image_path, mask_path


def test_load_case_handles_gzip_content_mislabeled_as_plain_nii(tmp_path):
    """A file that's gzip-compressed but saved with a plain .nii extension
    (e.g. compressed in place without renaming) must still load, for both
    the image and the mask."""
    cfg = _load_cfg()
    image_path, mask_path = _write_case_files(tmp_path, image_ext=".nii", mask_ext=".nii")

    with open(image_path, "rb") as f:
        assert f.read(2) == b"\x1f\x8b"  # confirms the file really is gzip data

    case = load_case(image_path, mask_path, cfg)
    assert case.ct_np.size > 0
    assert case.aorta_np.any()


def test_load_case_still_handles_correctly_named_files(tmp_path):
    """Regression guard: the mislabeled-gzip fallback must not break the
    ordinary, correctly-named .nii / .nii.gz path (the common case, where
    the direct `sitk.ReadImage` succeeds and the fallback never triggers)."""
    cfg = _load_cfg()
    image_path, mask_path = _write_case_files(tmp_path, image_ext=".nii.gz", mask_ext=".nii.gz")
    case = load_case(image_path, mask_path, cfg)
    assert case.ct_np.size > 0
    assert case.aorta_np.any()
