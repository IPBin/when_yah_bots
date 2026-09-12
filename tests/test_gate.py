"""Tests for src/gate.py (§10.6 prompt 9, P1 half: accept + dedup)."""

import numpy as np
import yaml

from src.instances import RawBranch
from src.geometry import BranchGeom
from src.intensity import Profile
from src.gate import accept, dedup


def _load_cfg():
    with open("config/default.yaml") as f:
        return yaml.safe_load(f)


def _raw(extent=8.0, patch_area=20.0, hu_ratio=0.95):
    return RawBranch(
        patch_zyx=np.zeros((4, 3), dtype=int),
        voxels_zyx=np.zeros((10, 3), dtype=int),
        geodesic_extent_mm=extent,
        patch_area_mm2=patch_area,
        mean_hu=330.0,
        hu_ratio=hu_ratio,
    )


def _geom(ostium=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0), radius=2.0, tortuosity=1.1):
    return BranchGeom(
        ostium_mm=np.array(ostium, dtype=float),
        seed_mm=np.array(ostium, dtype=float) + np.array(direction, dtype=float) * 5.0,
        direction=np.array(direction, dtype=float),
        radius_mm=radius,
        path_mm=np.array([ostium, ostium]),
        tortuosity=tortuosity,
    )


def _profile():
    return Profile(a_med=350.0, a_p10=300.0, a_iqr=40.0, t_vessel=200.0, t_high=300.0, t_bone=900.0)


def test_accept_ok_case_passes():
    cfg = _load_cfg()
    keep, reason = accept(_raw(), _geom(), _profile(), cfg)
    assert keep
    assert reason == "ok"


def test_accept_rejects_insufficient_extent():
    cfg = _load_cfg()
    keep, reason = accept(_raw(extent=1.0), _geom(), _profile(), cfg)
    assert not keep
    assert reason == "insufficient_extent"


def test_accept_rejects_below_min_radius():
    cfg = _load_cfg()
    keep, reason = accept(_raw(), _geom(radius=0.1), _profile(), cfg)
    assert not keep
    assert reason == "below_min_radius"


def test_accept_rejects_patch_too_small_and_too_large():
    cfg = _load_cfg()
    keep, reason = accept(_raw(patch_area=0.1), _geom(), _profile(), cfg)
    assert not keep
    assert reason == "patch_too_small"

    keep, reason = accept(_raw(patch_area=9999.0), _geom(), _profile(), cfg)
    assert not keep
    assert reason == "patch_too_large"


def test_accept_rejects_low_hu_ratio():
    cfg = _load_cfg()
    keep, reason = accept(_raw(hu_ratio=0.1), _geom(), _profile(), cfg)
    assert not keep
    assert reason == "low_hu_ratio"


def test_accept_rejects_too_tortuous():
    cfg = _load_cfg()
    keep, reason = accept(_raw(), _geom(tortuosity=10.0), _profile(), cfg)
    assert not keep
    assert reason == "too_tortuous"


def test_dedup_merges_close_same_direction_duplicates():
    cfg = _load_cfg()
    items = [
        (_raw(patch_area=10.0), _geom(ostium=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))),
        (_raw(patch_area=25.0), _geom(ostium=(1.0, 0.5, 0.0), direction=(0.99, 0.05, 0.0))),
    ]
    merged = dedup(items, cfg)
    assert len(merged) == 1
    # the larger, more confident patch should be the survivor
    assert merged[0][0].patch_area_mm2 == 25.0


def test_dedup_keeps_nearby_but_differently_directed_branches_split():
    """Two real ostia close together (e.g. facing renals) must not merge
    just because they're near each other -- direction has to differ too."""
    cfg = _load_cfg()
    items = [
        (_raw(), _geom(ostium=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))),
        (_raw(), _geom(ostium=(1.0, 0.0, 0.0), direction=(-1.0, 0.0, 0.0))),
    ]
    merged = dedup(items, cfg)
    assert len(merged) == 2


def test_dedup_keeps_far_apart_same_direction_branches_split():
    cfg = _load_cfg()
    items = [
        (_raw(), _geom(ostium=(0.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))),
        (_raw(), _geom(ostium=(50.0, 0.0, 0.0), direction=(1.0, 0.0, 0.0))),
    ]
    merged = dedup(items, cfg)
    assert len(merged) == 2


def test_dedup_handles_empty_list():
    cfg = _load_cfg()
    assert dedup([], cfg) == []
