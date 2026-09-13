"""Human-readable labels for the real pipeline stages reported by `run.run_case`'s
`on_stage` callback (run.py). One entry per stage name actually emitted; keep in
sync with run.py's `_notify(on_stage, ...)` call sites.
"""

STAGE_ORDER = ["load", "profile", "candidates", "frame", "instances", "geometry", "export"]

STAGE_LABELS = {
    "load": "Loading volume & aorta mask",
    "profile": "Profiling aortic lumen HU",
    "candidates": "Building candidate vessel mask",
    "frame": "Building aortic centreline & wall frame",
    "instances": "Finding raw branch instances",
    "geometry": "Measuring geometry & applying eligibility gate",
    "export": "Assembling prediction output",
}
