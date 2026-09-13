"""Tests for eval/score.py against hand-written fake predictions (playbook
§2 Block 2: "you don't need a detector to test a scorer")."""

import json
import os

import pytest

from eval.score import score_case, score_directory

REF = {
    "case_id": "fake001",
    "daughters": [
        {"instance_id": "b1", "ostium_xyz_mm": [0, 0, 0], "seed_xyz_mm": [0, 0, 5], "radius_mm": 3.0, "direction_xyz": [0, 0, 1]},
        {"instance_id": "b2", "ostium_xyz_mm": [10, 0, 0], "seed_xyz_mm": [15, 0, 0], "radius_mm": 1.0, "direction_xyz": [1, 0, 0]},
        {"instance_id": "b3", "ostium_xyz_mm": [0, 10, 0], "seed_xyz_mm": [0, 15, 0], "radius_mm": 0.7, "direction_xyz": [0, 1, 0]},
    ],
}


def test_perfect_match_is_all_true_positive():
    pred = {"case_id": "fake001", "daughters": REF["daughters"]}
    result = score_case(pred, REF)
    for thr, s in result.items():
        assert s["tp"] == 3
        assert s["fp"] == 0
        assert s["fn"] == 0
        assert s["f1"] == pytest.approx(1.0)


def test_close_match_counts_as_tp_missing_and_extra_as_fn_fp():
    pred = {
        "case_id": "fake001",
        "daughters": [
            {"instance_id": "p1", "ostium_xyz_mm": [0.5, 0, 0], "seed_xyz_mm": [0.5, 0, 5], "radius_mm": 2.8, "direction_xyz": [0, 0, 1]},
            {"instance_id": "p2", "ostium_xyz_mm": [10, 0.2, 0], "seed_xyz_mm": [15, 0.2, 0], "radius_mm": 1.2, "direction_xyz": [1, 0, 0.1]},
            {"instance_id": "p3", "ostium_xyz_mm": [50, 50, 50], "seed_xyz_mm": [51, 50, 50], "radius_mm": 1.0, "direction_xyz": [1, 0, 0]},
        ],
    }
    result = score_case(pred, REF)
    s = result[5.0]
    assert s["tp"] == 2
    assert s["fp"] == 1
    assert s["fn"] == 1


def test_duplicate_detections_count_as_false_positive():
    """The brief: predictions are matched one-to-one, so a duplicate near
    the same reference ostium must count as a false positive, not a second
    true positive."""
    pred = {
        "case_id": "fake001",
        "daughters": [
            {"instance_id": "p1", "ostium_xyz_mm": [0.2, 0, 0], "seed_xyz_mm": [0.2, 0, 5], "radius_mm": 3.0, "direction_xyz": [0, 0, 1]},
            {"instance_id": "p1b", "ostium_xyz_mm": [0.3, 0, 0], "seed_xyz_mm": [0.3, 0, 5], "radius_mm": 3.0, "direction_xyz": [0, 0, 1]},
        ],
    }
    result = score_case(pred, {"case_id": "fake001", "daughters": [REF["daughters"][0]]})
    s = result[5.0]
    assert s["tp"] == 1
    assert s["fp"] == 1
    assert s["fn"] == 0


def test_empty_daughters_does_not_crash():
    pred = {"case_id": "fake002", "daughters": []}
    ref = {"case_id": "fake002", "daughters": []}
    result = score_case(pred, ref)
    for thr, s in result.items():
        assert s["tp"] == 0 and s["fp"] == 0 and s["fn"] == 0


def test_score_directory_matches_cases_by_id(tmp_path):
    """With more than one file per directory (so the single-file shortcut in
    `_load_json_dir` doesn't apply), cases must still be paired by their own
    `case_id` field, not by filename."""
    pred_dir = tmp_path / "pred"
    ref_dir = tmp_path / "ref"
    pred_dir.mkdir()
    ref_dir.mkdir()

    pred1 = {"case_id": "fake001", "daughters": REF["daughters"]}
    ref2 = {"case_id": "fake002", "daughters": []}
    pred2 = {"case_id": "fake002", "daughters": []}
    (pred_dir / "fake001.json").write_text(json.dumps(pred1))
    (ref_dir / "fake001.json").write_text(json.dumps(REF))
    (pred_dir / "fake002.json").write_text(json.dumps(pred2))
    (ref_dir / "fake002.json").write_text(json.dumps(ref2))

    result = score_directory(str(pred_dir), str(ref_dir))
    assert "fake001" in result["per_case"]
    assert "fake002" in result["per_case"]
    assert result["summary"][5.0]["micro"]["f1"] == pytest.approx(1.0)


def test_score_directory_single_file_pair_uses_generic_key(tmp_path):
    """With exactly one file per directory, pairing must not depend on
    `case_id` matching between them -- see
    `test_score_directory_pairs_single_files_despite_mismatched_case_id`."""
    pred_dir = tmp_path / "pred"
    ref_dir = tmp_path / "ref"
    pred_dir.mkdir()
    ref_dir.mkdir()

    pred = {"case_id": "fake001", "daughters": REF["daughters"]}
    (pred_dir / "fake001.json").write_text(json.dumps(pred))
    (ref_dir / "fake001.json").write_text(json.dumps(REF))

    result = score_directory(str(pred_dir), str(ref_dir))
    assert len(result["per_case"]) == 1
    assert result["summary"][5.0]["micro"]["f1"] == pytest.approx(1.0)


def test_score_directory_pairs_single_files_despite_mismatched_case_id(tmp_path):
    """A lone prediction file must pair with a lone reference file even when
    the `case_id` field inside each JSON doesn't match -- there's no
    ambiguity to resolve with only one file on each side."""
    pred_dir = tmp_path / "pred"
    ref_dir = tmp_path / "ref"
    pred_dir.mkdir()
    ref_dir.mkdir()

    pred = {"case_id": "whatever_the_pipeline_called_it", "daughters": REF["daughters"]}
    ref = {"case_id": "the_official_reference_id", "daughters": REF["daughters"]}
    (pred_dir / "prediction.json").write_text(json.dumps(pred))
    (ref_dir / "reference.json").write_text(json.dumps(ref))

    result = score_directory(str(pred_dir), str(ref_dir))
    assert len(result["per_case"]) == 1
    assert result["summary"][5.0]["micro"]["f1"] == pytest.approx(1.0)
