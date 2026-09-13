"""Flask app for the local Branchseed web console.

Wraps the existing CLI pipeline (run.py, src/*) for a single local clinician:
upload a case, run it, review the real prediction with the same PNGs
src/report.py already renders, browse past cases. No detection logic lives
here -- every route either reuses an existing pipeline function or does thin
file/JSON glue. See /Users/Fazli/.claude/plans/goofy-leaping-pnueli.md for
the full design rationale.

Run with: python -m webapp.server
"""

import copy
import datetime
import io
import json
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from flask import Flask, jsonify, request, send_file, send_from_directory  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

from run import load_config  # noqa: E402
from webapp import imaging, jobs, storage  # noqa: E402

ALLOWED_EXTENSIONS = (".nii.gz", ".nii")
DEFAULT_CONFIG_PATH = os.path.join(ROOT, "config", "default.yaml")

app = Flask(__name__, static_folder="static", static_url_path="")


def _ext_of(filename: str) -> str:
    """Return the allowed NIfTI extension of `filename`, or None if not allowed."""
    for ext in ALLOWED_EXTENSIONS:
        if filename.lower().endswith(ext):
            return ext
    return None


def _stem_of(filename: str, ext: str) -> str:
    """A filesystem-safe stem for `filename` with its `ext` suffix removed.

    Used so the on-disk image filename keeps a recognizable name (the
    pipeline derives its own `case_id` from this basename, per
    `src/io_geom.py:_basename_no_ext`), rather than a generic "image".
    """
    stem = filename[: -len(ext)] if filename.lower().endswith(ext) else filename
    stem = secure_filename(stem)
    return stem or "image"


def _case_summary(case_id: str) -> dict:
    """Build one case-library row: real meta + latest run status/metrics, or {} if missing."""
    try:
        meta = storage.get_meta(case_id)
    except FileNotFoundError:
        return {}
    run_id = meta.get("latest_run_id")
    summary = {
        "case_id": case_id,
        "pipeline_case_id": meta.get("pipeline_case_id"),
        "original_image_name": meta.get("original_image_name"),
        "original_mask_name": meta.get("original_mask_name"),
        "latest_run_id": run_id,
        "status": "no_runs",
        "n_daughters": None,
        "n_excluded_candidates": None,
        "runtime_s": None,
        "peak_memory_mb": None,
    }
    if run_id is None:
        return summary
    status = storage.read_status(case_id, run_id)
    summary["status"] = status.get("state", "unknown")
    rm = storage.read_runtime_memory(case_id, run_id)
    if rm:
        summary["runtime_s"] = rm.get("runtime_s")
        summary["peak_memory_mb"] = rm.get("peak_memory_mb")
    prediction = storage.read_prediction(case_id, run_id)
    if prediction:
        summary["n_daughters"] = len(prediction.get("daughters", []))
        summary["n_excluded_candidates"] = len(prediction.get("excluded_candidates", []))
    return summary


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config/defaults")
def config_defaults():
    """Real, config-backed defaults for the upload screen's sliders/checkbox."""
    cfg = load_config(DEFAULT_CONFIG_PATH)
    return jsonify({
        "min_extent_mm": cfg["min_extent_mm"],
        "trace_max_mm": cfg["trace_max_mm"],
        "min_radius_mm": cfg["min_radius_mm"],
        "log_rejections": cfg["log_rejections"],
    })


@app.post("/api/cases")
def create_case():
    """Upload a CT volume + aorta mask, no manual point placement. Returns {case_id}."""
    image_file = request.files.get("image")
    mask_file = request.files.get("mask")
    if image_file is None or mask_file is None:
        return jsonify({"error": "both 'image' and 'mask' files are required"}), 400

    image_ext = _ext_of(image_file.filename or "")
    mask_ext = _ext_of(mask_file.filename or "")
    if image_ext is None or mask_ext is None:
        return jsonify({"error": "files must be .nii or .nii.gz"}), 400

    stored_image_name = f"{_stem_of(image_file.filename, image_ext)}{image_ext}"
    stored_mask_name = f"mask{mask_ext}"
    case_id = storage.create_case(image_file.filename, mask_file.filename, stored_image_name, stored_mask_name)
    case_directory = storage.case_dir(case_id)
    image_file.save(str(case_directory / stored_image_name))
    mask_file.save(str(case_directory / stored_mask_name))
    return jsonify({"case_id": case_id})


def _case_paths(case_id: str):
    """Locate a case's stored image/mask paths on disk, or (None, None) if missing."""
    try:
        meta = storage.get_meta(case_id)
    except FileNotFoundError:
        return None, None
    case_directory = storage.case_dir(case_id)
    image_path = case_directory / meta["stored_image_name"]
    mask_path = case_directory / meta["stored_mask_name"]
    if not image_path.exists() or not mask_path.exists():
        return None, None
    return image_path, mask_path


@app.post("/api/cases/<case_id>/run")
def run_case_endpoint(case_id):
    """Start a run with optional slider overrides. Returns {run_id} immediately (queued)."""
    try:
        storage.get_meta(case_id)
    except FileNotFoundError:
        return jsonify({"error": "no such case"}), 404

    image_path, mask_path = _case_paths(case_id)
    if image_path is None or mask_path is None:
        return jsonify({"error": "case is missing its uploaded files"}), 409

    overrides = request.get_json(silent=True) or {}
    cfg = copy.deepcopy(load_config(DEFAULT_CONFIG_PATH))
    for key in ("min_extent_mm", "trace_max_mm", "min_radius_mm"):
        if key in overrides:
            cfg[key] = float(overrides[key])
    if "log_rejections" in overrides:
        cfg["log_rejections"] = bool(overrides["log_rejections"])

    jobs.start_worker()
    run_id = jobs.enqueue_run(case_id, str(image_path), str(mask_path), cfg)
    return jsonify({"run_id": run_id})


def _find_case_for_run(run_id: str):
    """Scan known cases for the one owning `run_id` (see storage.py layout)."""
    for case_id in storage.list_case_ids():
        if (storage.run_dir(case_id, run_id)).exists():
            return case_id
    return None


@app.get("/api/runs/<run_id>/events")
def run_events(run_id):
    """SSE stream of stage/log events: replay history, then tail until done/error."""
    case_id = _find_case_for_run(run_id)
    if case_id is None:
        return jsonify({"error": "no such run"}), 404

    def generate():
        sent = 0
        while True:
            events = storage.read_log(case_id, run_id)
            for event in events[sent:]:
                yield f"data: {_json_line(event)}\n\n"
            sent = len(events)
            status = storage.read_status(case_id, run_id)
            if status.get("state") in ("done", "error"):
                yield f"data: {_json_line({'type': 'status', 'state': status.get('state')})}\n\n"
                break
            time.sleep(0.3)

    return app.response_class(generate(), mimetype="text/event-stream")


def _json_line(obj) -> str:
    return json.dumps(obj)


def _resolve_run_id(case_id: str, run_id_param):
    """Use an explicit ?run_id= if given, else the case's latest run."""
    if run_id_param:
        return run_id_param
    try:
        meta = storage.get_meta(case_id)
    except FileNotFoundError:
        return None
    return meta.get("latest_run_id")


@app.get("/api/cases/<case_id>/prediction")
def get_prediction(case_id):
    """The prediction JSON for a case's (given or latest) run."""
    run_id = _resolve_run_id(case_id, request.args.get("run_id"))
    if run_id is None:
        return jsonify({"error": "case has no runs yet"}), 404
    prediction = storage.read_prediction(case_id, run_id)
    if not prediction:
        return jsonify({"error": "run has not produced a prediction yet"}), 409
    return jsonify(prediction)


@app.get("/api/cases/<case_id>/volume-info")
def volume_info(case_id):
    """Slice count + spacing, so the review screen can size its slice scrubber."""
    image_path, mask_path = _case_paths(case_id)
    if image_path is None:
        return jsonify({"error": "no such case"}), 404
    cfg = load_config(DEFAULT_CONFIG_PATH)
    case = imaging.get_case(case_id, str(image_path), str(mask_path), cfg)
    nz, ny, nx = case.ct_np.shape
    return jsonify({"shape_zyx": [nz, ny, nx]})


@app.get("/api/cases/<case_id>/slice")
def get_slice(case_id):
    """One axial slice (voxel index `z`, default: middle slice) as a PNG."""
    image_path, mask_path = _case_paths(case_id)
    if image_path is None:
        return jsonify({"error": "no such case"}), 404
    cfg = load_config(DEFAULT_CONFIG_PATH)
    case = imaging.get_case(case_id, str(image_path), str(mask_path), cfg)
    z = request.args.get("z", type=int)
    if z is None:
        z = imaging.slice_count(case) // 2
    png_bytes = imaging.render_slice_png(case, z)
    return send_file(io.BytesIO(png_bytes), mimetype="image/png")


@app.get("/api/cases/<case_id>/overlay")
def get_overlay(case_id):
    """The coronal/sagittal MIP + ostia/arrow PNG (src.report.visual_check output)."""
    run_id = _resolve_run_id(case_id, request.args.get("run_id"))
    if run_id is None:
        return jsonify({"error": "case has no runs yet"}), 404
    path = storage.run_dir(case_id, run_id) / "visual_check.png"
    if not path.exists():
        return jsonify({"error": "run has not rendered a visual check yet"}), 409
    return send_file(str(path), mimetype="image/png")


@app.get("/api/cases/<case_id>/origin-map")
def get_origin_map(case_id):
    """The unrolled arclength/clock-position map (src.report.unrolled_map output)."""
    run_id = _resolve_run_id(case_id, request.args.get("run_id"))
    if run_id is None:
        return jsonify({"error": "case has no runs yet"}), 404
    path = storage.run_dir(case_id, run_id) / "unrolled_map.png"
    if not path.exists():
        return jsonify({"error": "run has not rendered an origin map yet"}), 409
    return send_file(str(path), mimetype="image/png")


@app.get("/api/cases")
def list_cases():
    """The case library: one row per uploaded case."""
    return jsonify({"cases": [_case_summary(cid) for cid in storage.list_case_ids()]})


@app.get("/api/cases/<case_id>")
def get_case_detail(case_id):
    """Single-case detail (same shape as one /api/cases row)."""
    summary = _case_summary(case_id)
    if not summary:
        return jsonify({"error": "no such case"}), 404
    return jsonify(summary)


@app.get("/api/cases/<case_id>/export")
def export_case(case_id):
    """Zip the latest run's prediction + both report PNGs + the config used."""
    run_id = _resolve_run_id(case_id, request.args.get("run_id"))
    if run_id is None:
        return jsonify({"error": "case has no runs yet"}), 404
    run_directory = storage.run_dir(case_id, run_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in ("prediction.json", "visual_check.png", "unrolled_map.png", "config_used.json"):
            path = run_directory / name
            if path.exists():
                zf.write(path, arcname=name)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                      download_name=f"{case_id}_{run_id}.zip")


@app.get("/api/cases/<case_id>/review")
def get_review(case_id):
    """The confirm/reject review log for a case, kept apart from detection itself."""
    return jsonify(storage.read_review(case_id))


@app.post("/api/cases/<case_id>/review")
def post_review(case_id):
    """Record one confirm/reject decision for a branch instance."""
    body = request.get_json(silent=True) or {}
    run_id = body.get("run_id") or _resolve_run_id(case_id, None)
    instance_id = body.get("instance_id")
    decision = body.get("decision")
    if run_id is None or not instance_id or decision not in ("confirmed", "rejected"):
        return jsonify({"error": "run_id, instance_id and decision ('confirmed'|'rejected') are required"}), 400
    at = datetime.datetime.utcnow().isoformat() + "Z"
    review = storage.write_review_entry(case_id, run_id, instance_id, decision, body.get("note", ""), at)
    return jsonify(review)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Branchseed local web console.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1, local-only).")
    # Default avoids 5000: macOS's AirPlay Receiver listens there by default.
    parser.add_argument("--port", type=int, default=5057, help="Port to listen on (default: 5057).")
    args = parser.parse_args()
    jobs.start_worker()
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
