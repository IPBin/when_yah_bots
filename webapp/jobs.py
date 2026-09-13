"""Single-worker run queue: the web console never runs two pipeline cases at
once. This isn't just simplicity -- `src.report.visual_check`/`unrolled_map`
use matplotlib's global `pyplot` figure-stack API, so concurrent report
generation from two threads would corrupt shared state. One background
worker thread draining a `queue.Queue` sidesteps that by construction; a
`threading.Lock` around the pyplot-touching block is kept anyway as cheap
insurance against a future second worker.
"""

import queue
import threading
import time
import tracemalloc

from run import run_case
from src.aorta_frame import build_frame
from src.report import unrolled_map, visual_check, write_prediction_json
from webapp import imaging, storage
from webapp.stage_labels import STAGE_LABELS

_queue = queue.Queue()
_worker_thread = None
_report_lock = threading.Lock()


def start_worker() -> None:
    """Start the single background worker thread, if not already running."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()


def enqueue_run(case_id: str, image_path: str, mask_path: str, cfg: dict) -> str:
    """Create a new run and enqueue it for the background worker.

    Args:
        case_id: opaque webapp case identifier (see webapp/storage.py).
        image_path: path to the case's stored CT volume.
        mask_path: path to the case's stored aorta mask.
        cfg: parsed config dict (defaults merged with any slider overrides
            for this run only -- never written back to config/default.yaml).

    Returns:
        The new run_id (str). The run is queued, not yet started.
    """
    run_id = storage.new_run_id()
    storage.init_run(case_id, run_id, cfg)
    _queue.put((case_id, run_id, image_path, mask_path, cfg))
    return run_id


def _worker_loop() -> None:
    """Drain the run queue forever, one case at a time."""
    while True:
        case_id, run_id, image_path, mask_path, cfg = _queue.get()
        try:
            _process_run(case_id, run_id, image_path, mask_path, cfg)
        except Exception as exc:  # noqa: BLE001 - one run must never kill the worker
            storage.write_status(case_id, run_id, {"state": "error", "error": str(exc)})
            storage.append_log(case_id, run_id, {"type": "error", "message": str(exc)})
        finally:
            _queue.task_done()


def _process_run(case_id: str, run_id: str, image_path: str, mask_path: str, cfg: dict) -> None:
    """Run one case end to end: pipeline, prediction JSON, both report PNGs."""
    storage.write_status(case_id, run_id, {"state": "running", "started_at": time.time()})
    storage.append_log(case_id, run_id, {"type": "status", "message": "run started", "t": time.time()})

    def on_stage(name: str) -> None:
        storage.write_status(case_id, run_id, {"stage": name})
        storage.append_log(
            case_id, run_id,
            {"type": "stage", "stage": name, "label": STAGE_LABELS.get(name, name), "t": time.time()},
        )

    tracemalloc.start()
    t0 = time.time()
    try:
        prediction = run_case(image_path, mask_path, cfg, on_stage=on_stage)
    finally:
        _current, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    runtime_s = time.time() - t0
    peak_memory_mb = peak_bytes / (1024 * 1024)

    run_directory = storage.run_dir(case_id, run_id)
    write_prediction_json(
        prediction["case_id"], prediction["daughters"], prediction["excluded_candidates"],
        prediction["meta"], str(run_directory / "prediction.json"),
    )
    storage.update_meta(case_id, pipeline_case_id=prediction["case_id"], latest_run_id=run_id)

    with _report_lock:
        storage.append_log(case_id, run_id, {"type": "status", "message": "rendering visual checks", "t": time.time()})
        case = imaging.get_case(case_id, image_path, mask_path, cfg)
        frame = build_frame(case, cfg)
        visual_check(case, frame, prediction["daughters"], str(run_directory / "visual_check.png"), cfg)
        unrolled_map(
            case, frame, prediction["daughters"], prediction["excluded_candidates"],
            str(run_directory / "unrolled_map.png"), cfg,
        )

    storage.write_runtime_memory(case_id, run_id, runtime_s, peak_memory_mb)
    storage.write_status(case_id, run_id, {"state": "done", "finished_at": time.time()})
    storage.append_log(
        case_id, run_id,
        {
            "type": "done", "message": "run complete", "t": time.time(),
            "n_daughters": len(prediction["daughters"]),
            "n_excluded_candidates": len(prediction["excluded_candidates"]),
            "runtime_s": runtime_s, "peak_memory_mb": peak_memory_mb,
            "warnings": prediction["meta"].get("warnings", []),
        },
    )
