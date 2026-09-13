"""Filesystem-only persistence for the local web console.

No database: every case and run is a directory under `webapp_data/`. This
module owns every path convention and every read/write of the small JSON
sidecar files (`meta.json`, `status.json`, `review.json`,
`runtime_memory.json`) so the rest of `webapp/` never constructs a path or
touches JSON on disk directly.

Owner: webapp (new module, not part of the scored src/ pipeline).
"""

import json
import os
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "webapp_data"
CASES_DIR = DATA_DIR / "cases"


def new_case_id() -> str:
    """Return a fresh opaque case identifier (storage key, not the pipeline's own case_id)."""
    return uuid.uuid4().hex[:12]


def new_run_id() -> str:
    """Return a fresh opaque run identifier."""
    return uuid.uuid4().hex


def case_dir(case_id: str) -> Path:
    """Directory holding one uploaded case's inputs and runs.

    Args:
        case_id: opaque case identifier from `new_case_id`.
    """
    return CASES_DIR / case_id


def run_dir(case_id: str, run_id: str) -> Path:
    """Directory holding one run's status, logs, and outputs.

    Args:
        case_id: opaque case identifier.
        run_id: opaque run identifier from `new_run_id`.
    """
    return case_dir(case_id) / "runs" / run_id


def _read_json(path: Path, default):
    """Read a JSON file, returning `default` if it doesn't exist yet."""
    if not path.exists():
        return default
    with open(path, "r") as f:
        return json.load(f)


def _write_json(path: Path, obj) -> None:
    """Write `obj` as JSON to `path`, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def create_case(orig_image_name: str, orig_mask_name: str, stored_image_name: str, stored_mask_name: str) -> str:
    """Create a new case directory and its initial `meta.json`.

    Args:
        orig_image_name: the uploaded CT file's original filename (display only).
        orig_mask_name: the uploaded mask file's original filename (display only).
        stored_image_name: the actual filename the CT volume is saved under
            in this case's directory (its stem becomes the pipeline's own
            `case_id`, per `src/io_geom.py:_basename_no_ext`).
        stored_mask_name: the actual filename the mask is saved under.

    Returns:
        The new case_id (str), the opaque storage key (distinct from the
        pipeline's own case_id, which is only known after a run completes).
    """
    case_id = new_case_id()
    case_dir(case_id).mkdir(parents=True, exist_ok=True)
    meta = {
        "case_id": case_id,
        "original_image_name": orig_image_name,
        "original_mask_name": orig_mask_name,
        "stored_image_name": stored_image_name,
        "stored_mask_name": stored_mask_name,
        "pipeline_case_id": None,
        "latest_run_id": None,
    }
    _write_json(case_dir(case_id) / "meta.json", meta)
    return case_id


def get_meta(case_id: str) -> dict:
    """Read `meta.json` for a case. Raises FileNotFoundError if the case doesn't exist."""
    path = case_dir(case_id) / "meta.json"
    if not path.exists():
        raise FileNotFoundError(f"no such case: {case_id}")
    return _read_json(path, None)


def update_meta(case_id: str, **patch) -> dict:
    """Merge `patch` into a case's `meta.json` and return the updated dict."""
    meta = get_meta(case_id)
    meta.update(patch)
    _write_json(case_dir(case_id) / "meta.json", meta)
    return meta


def list_case_ids() -> list:
    """Return every known case_id, oldest-created first (by directory mtime)."""
    if not CASES_DIR.exists():
        return []
    dirs = [d for d in CASES_DIR.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.stat().st_mtime)
    return [d.name for d in dirs]


def init_run(case_id: str, run_id: str, config_used: dict) -> None:
    """Create a run directory with an initial `status.json` and config snapshot."""
    d = run_dir(case_id, run_id)
    d.mkdir(parents=True, exist_ok=True)
    _write_json(d / "config_used.json", config_used)
    write_status(case_id, run_id, {"state": "queued", "stage": None, "error": None})


def read_status(case_id: str, run_id: str) -> dict:
    """Read a run's `status.json` (state: queued|running|done|error)."""
    return _read_json(run_dir(case_id, run_id) / "status.json", {"state": "unknown"})


def write_status(case_id: str, run_id: str, patch: dict) -> dict:
    """Merge `patch` into a run's `status.json` and return the updated dict."""
    path = run_dir(case_id, run_id) / "status.json"
    status = _read_json(path, {})
    status.update(patch)
    _write_json(path, status)
    return status


def append_log(case_id: str, run_id: str, event: dict) -> None:
    """Append one JSON-serializable event as a line to a run's `log.jsonl`."""
    path = run_dir(case_id, run_id) / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")


def read_log(case_id: str, run_id: str) -> list:
    """Read every event previously appended to a run's `log.jsonl`."""
    path = run_dir(case_id, run_id) / "log.jsonl"
    if not path.exists():
        return []
    events = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def write_runtime_memory(case_id: str, run_id: str, runtime_s: float, peak_memory_mb: float) -> None:
    """Persist the final, real runtime/peak-memory figures for a completed run."""
    _write_json(
        run_dir(case_id, run_id) / "runtime_memory.json",
        {"runtime_s": runtime_s, "peak_memory_mb": peak_memory_mb},
    )


def read_runtime_memory(case_id: str, run_id: str) -> dict:
    """Read a completed run's runtime/peak-memory figures, or {} if not finished."""
    return _read_json(run_dir(case_id, run_id) / "runtime_memory.json", {})


def read_prediction(case_id: str, run_id: str) -> dict:
    """Read a run's `prediction.json`, or {} if the run hasn't produced one yet."""
    return _read_json(run_dir(case_id, run_id) / "prediction.json", {})


def read_review(case_id: str) -> dict:
    """Read a case's review log: {"<run_id>:<instance_id>": {decision, note, at}}."""
    return _read_json(case_dir(case_id) / "review.json", {})


def write_review_entry(case_id: str, run_id: str, instance_id: str, decision: str, note: str, at: str) -> dict:
    """Record one confirm/reject decision for a branch and return the full review log."""
    review = read_review(case_id)
    key = f"{run_id}:{instance_id}"
    review[key] = {"decision": decision, "note": note, "at": at}
    _write_json(case_dir(case_id) / "review.json", review)
    return review
