# Branchseed Challenge

Automatic detection of arterial branches arising from the abdominal aorta in CTA volumes.

## Setup
pip install -r requirements.txt

## Run
python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json

Batch mode (whole directory of `subjectNNN/` or flat `origN`/`maskN` pairs):
python eval/batch.py --data data/ --out results/predictions

## Method
Classical image processing pipeline: adaptive aorta-relative thresholding, hysteresis candidate masking, bone suppression, end-cap exclusion, contact-patch instancing with geodesic separation, EDT-based radius estimation.

## Web UI (optional)
A local, single-user web console for uploading a case, watching it run, and reviewing the
result (branch list, real coronal/sagittal overlay, axial slice scrubber, unrolled origin
map, raw JSON, confirm/reject review log, case library). Not required for the scored CLI
pipeline above; kept in its own `webapp/` package and its own dependency file so it never
touches the pinned, already-rehearsed `requirements.txt`.

    pip install -r requirements-web.txt
    python -m webapp.server

Then open http://127.0.0.1:5057 (5000 is avoided since macOS's AirPlay Receiver
often squats on it; override with `--port`). Runs fully offline (no CDN assets, plain HTML/CSS/JS, no
build step) and executes cases one at a time through the same `run.py:run_case` used by the
CLI -- no separate detection logic. Server-rendered images (overlay, origin map) are exactly
`src/report.py`'s `visual_check`/`unrolled_map` output.

## Performance
Measured with `eval/batch.py` over the 5-case dev set (`results/predictions/batch_summary.csv`), single process, 4 CPU cores, no GPU:
- Runtime: 2.1-7.8s/case, mean ~3.8s/case (well under the 60s/case target).
- Peak memory: 65-281 MB/case (Python-heap peak via `tracemalloc`; a lower bound on true RSS since it does not see memory allocated by SimpleITK's native extensions, but well within the 8GB budget with wide margin).

## Known limitations
- Lumbar arteries under ~1mm radius may be missed
- Case 24 has non-orthonormal direction cosines and fails to load
- Heavy wall calcification can produce occasional false positives
- Validated against the organizers' per-case daughter-candidate counts (orig19-23:
  3/4/3/6/3, 19 total). Current pipeline detects 16/19 (3/2/5/5/1) after two
  fixes: a false-positive bug where single-voxel threshold noise cleared
  `min_extent_mm` via the wall-bridge dilation inflating its measured extent
  (`min_mean_cross_section_mm2`, `docs/scoreboard.md` pass #3), and an
  isolated `hu_ratio_min` relaxation that rescued one plausible orig22
  candidate with zero effect on the other 4 cases (pass #4). orig20 and
  orig23 still under-detect and orig21 still over-detects; a further
  candidate fix (raising `max_extent_mm` to admit long thin candidates)
  was investigated and rejected because it would also admit several
  similarly-thin candidates in orig21, worsening its over-detection. The
  remaining gap has not been root-caused per-branch, since only aggregate
  counts are available from the organizers, not reference positions.
- `radius_mm` is quantized near 1.0-1.4mm (the isotropic voxel size) for most
  real daughters: the candidate mask is only 1-2 voxels wide at these branches'
  ostia on the real dev set. A `k_vessel` sweep (3.0-10.0, `docs/scoreboard.md`
  pass #3) confirmed this is not a simple thresholding fix -- radius barely
  moved while looser values destabilized detection counts on some cases (e.g.
  orig22 dropped to 0 daughters at k_vessel>=4). Likely a genuine partial-volume
  resolution limit for these vessels at their very ostium, not attempted
  further given the risk of regressing detection this close to the deadline.
