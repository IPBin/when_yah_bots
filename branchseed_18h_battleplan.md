# Branchseed — 18-Hour Battle Plan

**3 people · 16:00 Saturday → 11:00 Sunday · submit by 10:45**

This replaces §6 (team split) and §7 (schedule) of the roadmap. Everything else in that document still applies — keep it open for the technical detail: §2 (domain crash course), §4 (the pipeline, stage by stage), §5 (module contracts), §8 (scorer + phantom), §10 (visualisation).

---

## What changed from the 48-hour plan

Two thirds of the time and three quarters of the people. So:

**Cut entirely.** Vesselness filtering. Half-max radius (EDT only). The learned/random-forest gate. Multi-scale recovery pass. Clicking fiducials in Slicer for extra ground truth. Interactive 3D plotly view. Fork detection — see below.

**Fork detection is the surprising cut.** I had it as a core stage; at 18 hours it's the first thing to go, and here's why that's safe. A common trunk has exactly one opening in the aortic wall, so "instance-per-contact-patch" already returns it as one branch regardless. And the celiac (the main trunk that forks) divides 10–20 mm out, while your seed sits at 5 mm — before the fork. So skipping it costs you almost nothing. Just cap the traced path at 10 mm and move on. If you have spare time at 08:00, add it; otherwise say in the demo that the contact-patch design handles trunks structurally, which is true and sounds better than "we ran out of time."

**Kept despite the squeeze:** the synthetic phantom, the scorer, end-cap suppression, adaptive thresholding, the unrolled aortic map. Each of these earns back more time than it costs, or is worth points you can't otherwise get.

**Biggest behavioural change:** you are not writing much code by hand. Three people with basic CS backgrounds cannot hand-write this pipeline in 18 hours. One person owns one module, prompts for it with a tight contract, reviews and tests the result, integrates. Your job is specification and verification, not typing. §9 of the roadmap and the prompt pack at the end of this document are the highest-value pages for you now.

---

## Roles

| | Owns | Score exposure |
|---|---|---|
| **P1 — Detector** | `aorta_frame`, `instances`, `geometry`, `gate` | 45% + 15% |
| **P2 — Foundations & signal** | `io_geom`, `intensity`, `candidates`, `run.py`, packaging, README, profiling, the fresh-clone rehearsal | 25% + 10% + 5% |
| **P3 — Feedback & delivery** | `phantom`, `score`, `batch`, visual checks, unrolled map, demo | makes the other two able to improve |

P1 has the hardest and largest job. From 22:00 onward, all three work on P1's problem together against the scoreboard — the roles only hold for the build phase.

Give P1 and P3 the Claude Code sessions. P2's modules are small and well-specified enough for chat.

---

## The clock

Times are hard. Gates are pass/fail. If you fail a gate, cut from the cut line — never slide the schedule, because the 01:45 and 10:45 deadlines don't move.

### 16:00–16:40 · Setup (all three, together, one room)

- Read the brief aloud once. Write every requirement as a checklist line in `docs/checklist.md`. There are about twenty. This is your definition of done and your 10:30 final pass.
- Create the repo skeleton from roadmap §5: empty modules with the exact signatures, `config/default.yaml`, `requirements.txt`, `CLAUDE.md` (template in roadmap §9.2), `docs/brief.md` with the challenge text pasted in.
- Unzip the data. Confirm one case loads and print its shape, spacing, and direction matrix.
- Agree the frozen rules out loud: numpy is `[z,y,x]`, SimpleITK is `(x,y,z)`, conversions only in `io_geom`, all coordinates crossing modules are physical mm, no constants outside config.

**Gate 16:40 —** all three can run `python run.py --image ... --aorta-mask ... --output out.json` and get a valid file containing `"daughters": []`.

### 16:40–18:30 · Block 1 (parallel)

- **P2:** `io_geom` — load, validate, crop to aorta bbox + 50 mm, resample to 1.0 mm isotropic, `idx_to_mm` / `mm_to_idx`. Then a round-trip assertion: take voxel (30,40,50), convert to mm, convert back, assert within 0.5 mm.
- **P1:** `aorta_frame` — per-slice centroid centreline, smoothed; wall surface; outward normals; **legal wall** with end caps excluded. Write it against a hand-built numpy cylinder until P2's loader lands around 17:30.
- **P3:** `phantom.py` **first** (both others need it), then spend 20 minutes opening 3 real cases in a viewer: find the aorta, find the celiac and SMA, probe the HU inside the aorta and inside a branch. Share screenshots. Count visible branches per case.

**Gate 18:30 —** loader works on a real case; phantom writes a volume plus its exact reference JSON; P1 can output a legal-wall mask and visually confirm the end caps are gone.

### 18:30–20:30 · Block 2 (parallel) — toward first detections

- **P2:** `intensity` (aorta-relative thresholds) + `candidates` (hysteresis threshold, bone exclusion, drop huge unattached components). Log the derived thresholds every run.
- **P1:** `instances` — components of non-aorta candidates, contact patches on the legal wall, connected components of the patches, one `RawBranch` per patch, geodesic extent via `MCP_Geometric`.
- **P3:** `score.py` (Hungarian matching via `scipy.optimize.linear_sum_assignment`, P/R/F1 at 3/5/10 mm, ostium distance, angle error, radius error) and `batch.py`. Test the scorer against a hand-written fake prediction — you don't need a working detector to test a scorer.

**Gate 20:30 (the critical one) —** end-to-end run on the phantom produces non-empty, non-absurd JSON. If you're not here by **21:00**, start cutting.

### 20:30–22:00 · Geometry and first real numbers

- **P1:** `geometry` — geodesic path from ostium outward (MCP with cost `1/(EDT+ε)`), seed at 5 mm arc length, PCA direction over 1–7 mm, EDT radius at the seed. Then `gate` with all thresholds from config.
- **P2:** run the full batch over all 25 cases. Fix every crash. Add the per-case try/except that always writes valid JSON. Time it.
- **P3:** score against the dev references and the phantom. Produce the scoreboard table and pin it somewhere all three can see.

**Gate 22:00 —** a real F1 number on the dev cases, whatever it is. Commit the predictions. **You are now submittable, six hours early.** Tag it `v1-safe`.

### 22:00–01:00 · Make the number go up (all three)

Work strictly in this order, re-scoring after every change:

1. **Recall.** Log every rejected candidate with its rejection reason. Are misses absent from P2's candidate mask, or killed by P1's gate? One reason usually accounts for most of them.
2. **Sweep `min_radius_mm`** from 0.5 to 2.0. Plot F1. Sit in the middle of the plateau, not on a spike.
3. **False positives, by cause.** Look at them visually, one at a time. They'll cluster into three or four causes (missed end cap, bone, iliac fork, kidney leak). Fix by cause. Tightening a global threshold trades 3 FPs for 5 FNs and nets nothing.
4. **De-duplication** (ostia > 3 mm apart *or* directions > 30° apart).
5. **Ostium accuracy** — sub-voxel centroid via `TransformContinuousIndexToPhysicalPoint`, nudge to mid-wall. This is 25% of the score for maybe 30 minutes of work.

**P3 in this window:** 22:00–23:30 the required visual checks (coronal + sagittal MIP overlays, plus the axial strip). Do this early — it's a submission requirement *and* it's how the other two will diagnose their false positives. Then 23:30–01:00 the unrolled aortic map.

**Gate 01:00 —** F1 around 0.6 or better, zero crashes across all 25 cases, visual checks generated for at least three cases.

### 01:00–01:45 · Lock in a submittable state, then sleep

**Hard rule: by 01:45 the repo is a complete, valid submission.** Everything after this is upside. Teams lose hackathons by leaving submission assembly until the morning and then hitting a broken dependency at 10:30.

- **P2:** README — one setup command, one run command, method summary, config table, known failure cases, measured runtime and peak memory. Commit dev-set predictions and the visual checks.
- **P1:** freeze the best-scoring config into `default.yaml`. Commit.
- **P3:** demo outline and the one method slide.

### 01:45–07:00 · Sleep (~5 hours, all three)

All three, at the same time. I'd normally suggest staggering, but with three people the coordination cost exceeds the benefit, and the specific failure mode of a sleep-deprived team on this task is a coordinate-convention bug that quietly destroys 25% of your score and takes two hours to find. The morning block needs clear heads more than the night block needs an extra body.

Set two alarms. If someone genuinely can't sleep, the useful solo task is rehearsing the demo — not touching code unsupervised.

### 07:00–09:00 · Fresh eyes

- **07:00–07:30, P2, before anything else:** fresh clone into a fresh virtual environment, **network disabled**, run the exact CLI from the brief. Something will break. Fix it now, not at 10:30.
- **P1:** remaining precision fixes. Check your parameters sit on a plateau rather than a spike — if a 10% change in a threshold swings F1 by 0.15, you're overfitted to the dev cases and the hidden set will punish you.
- **P3:** finish the unrolled map and the per-case HTML report.

**Gate 09:00 — feature freeze.** Config values and typo fixes only from here.

### 09:00–10:15 · Demo

P3 leads. Structure in roadmap §11.2. Rehearse twice with a timer; five minutes means five. Record it if the submission requires a recording — budget for one retake.

Give each person a defined section. Judges notice when one person does all the talking.

Final numbers go into the README now that they're stable.

### 10:15–10:45 · Submit

Re-run the full batch, commit predictions, walk `docs/checklist.md` line by line, submit. **Submit at 10:45.** The last 15 minutes are for the upload failing.

---

## The cut line

If you're behind a gate, cut in this order. Top of the list goes first.

1. Fork detection *(already cut — see above)*
2. Vesselness filtering *(already cut)*
3. Patch-merge logic for over-split ostia — keep the splitting, drop the merging
4. Iliac bifurcation special-casing — the end-cap rule usually covers it
5. The HTML report wrapper — keep the PNGs and JSON
6. Sub-voxel / mid-wall ostium refinement
7. The unrolled aortic map

Do not cut 5–7 before 3–4. And **never cut any of these:**

- End-cap suppression (it's ~25 false positives, one per case)
- Aorta-relative adaptive thresholding (without it you work on maybe a third of cases)
- The per-case try/except safety net
- The exact CLI signature from the brief
- The README with one setup and one run command
- Coordinate correctness

---

## Three things that matter more at 18 hours than at 48

**Front-load the Claude Code credits.** Revised allocation: ~35% on the 16:40–20:30 build blocks, ~45% on the 22:00–01:00 debugging loop, ~20% reserve. The debugging loop is where an agent that can run your pipeline on a real case and print the rejection log is worth ten times a chat model guessing. Don't save credits for a tomorrow that is only four working hours long.

**Nothing is allowed to block two people.** The interfaces in roadmap §5 exist for exactly this. If P1 needs the loader and it isn't ready, P1 writes against a numpy cylinder and integrates later — never waits. Agree now that "I'll stub it" is always the right answer.

**A number at 22:00 beats a better algorithm at 02:00.** The gate structure above is designed so that you hit "submittable" at 22:00 and spend the remaining time improving a measured quantity. Teams that chase the elegant version and integrate at 03:00 discover their coordinate bug at 09:00 and submit something that scores worse than the boring version would have.

---

## Appendix: prompt pack

Paste these roughly in order. Each assumes your `CLAUDE.md` and the frozen interfaces are already in the repo. Adapt the names to whatever you actually froze at 16:00. Add to the end of every one of them: *"Then list the three ways this will produce wrong results on real data and what I should check."*

**1 · Scaffold** *(16:00, P2)*
> Create a Python project skeleton for the task described in `docs/brief.md`. Directory layout: `run.py`, `requirements.txt`, `config/default.yaml`, `src/{io_geom,intensity,candidates,aorta_frame,instances,geometry,gate,report}.py`, `eval/{score,phantom,batch}.py`, `tests/`. Create every module with the dataclasses and function signatures I've pasted below, full docstrings stating the units of every argument, and `raise NotImplementedError` bodies. `run.py` must implement exactly `python run.py --image X --aorta-mask Y --output Z`, call the stages in order, wrap everything in a try/except that always writes valid JSON with an empty `daughters` list on failure, and support both `.nii` and `.nii.gz`. Pin versions in `requirements.txt`: SimpleITK, numpy, scipy, scikit-image, PyYAML, matplotlib. Nothing that downloads data or weights at runtime. `[paste the interfaces from roadmap §5]`

**2 · Loader and coordinates** *(16:40, P2)*
> Implement `io_geom.py`. `load_case(image_path, mask_path, cfg)`: read both with SimpleITK; assert matching size, spacing, origin and direction (log a warning and resample the mask to the image grid rather than crashing if they differ); compute the aorta mask's bounding box; crop both to that box padded by `cfg.roi_margin_mm` = 50 mm, clipped to the volume; resample both to `cfg.iso_mm` = 1.0 mm isotropic, linear for the CT and nearest-neighbour for the mask; return the `Case` dataclass with both SimpleITK images and `[z,y,x]` numpy views. Implement `idx_to_mm(case, zyx)` and `mm_to_idx(case, xyz_mm)` using `TransformContinuousIndexToPhysicalPoint` and `TransformPhysicalPointToContinuousIndex`, accepting floats and single points or `(N,3)` arrays, remembering that numpy is `[z,y,x]` and SimpleITK is `(x,y,z)`. Then write `tests/test_io_geom.py` asserting a voxel→mm→voxel round trip within 0.5 mm, and asserting it still holds on a synthetic image with spacing `(0.7, 0.7, 2.0)` and a non-identity direction matrix.

**3 · Phantom** *(16:40, P3)*
> Write `eval/phantom.py`: generate a synthetic CTA-like NIfTI volume plus its exact reference JSON, for testing a branch detector. Contents: background 40 HU; a vertical cylinder radius 10 mm at 350 HU along z (the aorta) with its own binary mask written separately; N branch cylinders at caller-specified positions along the aorta, each with a given direction, radius and length, at 320 HU; a Gaussian blur of sigma 0.8 mm to mimic partial volume; Gaussian noise sigma 15 HU. Options for: a 700 HU slab 25 mm posterior (a spine), a 900 HU 2 mm sphere embedded in the aortic wall (a calcification), a dimmer 120 HU parallel cylinder (a vein), and one branch that forks into two at 7 mm out. Write the reference JSON in the challenge's exact output format, with `ostium_xyz_mm` on the aortic surface, `seed_xyz_mm` at 5 mm along the branch axis, the true radius and the true unit direction — all computed through SimpleITK's `TransformContinuousIndexToPhysicalPoint` so they're in the same physical frame. Also expose a `spacing` and `direction` argument so I can generate anisotropic and rotated variants of the same phantom.

**4 · Scorer** *(18:30, P3)*
> Write `eval/score.py`. Load a prediction JSON and a reference JSON in the format in `docs/brief.md`. Build the pairwise Euclidean distance matrix between predicted and reference `ostium_xyz_mm`. Match one-to-one with `scipy.optimize.linear_sum_assignment`, then reject any matched pair further apart than a threshold. Report, for thresholds 3, 5 and 10 mm: TP, FP, FN, precision, recall, F1, mean and max ostium distance over matched pairs, mean angle in degrees between predicted and reference `direction_xyz`, and mean absolute radius error. Also report whether each predicted seed lies within the reference radius of the reference seed. Aggregate across cases both micro (pooled) and macro (mean of per-case F1). Print a per-case table and a summary row. Add `--sweep min_radius` support: re-score a directory of predictions produced at different config values and print F1 against the swept value.

**5 · Intensity and candidates** *(18:30, P2)*
> Implement `intensity.py` and `candidates.py`. `profile_aorta(case, cfg)`: erode the aorta mask by 2 mm to avoid partial-volume wall voxels, take the CT values inside, and return median, 10th percentile and IQR, plus derived thresholds `t_vessel = max(a_med - cfg.k_vessel*(a_med - a_p10), cfg.frac_vessel*a_med, 120.0)`, `t_bone = a_med + cfg.bone_offset`, and `t_high = cfg.frac_high*a_med`. Log all of them. `candidate_mask(case, profile, cfg)`: hysteresis threshold with `skimage.filters.apply_hysteresis_threshold` using `t_high` as the seed level and `t_vessel` as the grow level; exclude voxels above `t_bone` dilated by 1.5 mm; union in the aorta mask; then remove any connected component not touching the aorta whose volume exceeds `cfg.max_stray_cc_ml`. Return a bool `[z,y,x]` array. Everything from `cfg`, no literals, vectorised scipy/skimage only, no per-voxel Python loops.

**6 · Aorta frame and forbidden surface** *(16:40, P1)*
> Implement `aorta_frame.py`. Build the centreline by taking, for each axial slice containing the aorta mask, the centroid of the largest 2D connected component, then smoothing the sequence over ~10 mm. Build `wall_np` as the mask minus its one-voxel erosion. `outward_normal(frame, zyx)` returns the normalised vector from the centreline point at that slice to the wall point, computed in physical mm. Build `legal_wall_np` by removing from `wall_np`: (a) every wall voxel within `cfg.endcap_mm` = 4 mm of the topmost or bottommost slice containing mask voxels; (b) every wall voxel whose outward normal is within `cfg.endcap_angle_deg` = 35° of the local centreline tangent; (c) everything at or below the first slice where the mask splits into two components of comparable size (the iliac bifurcation), minus a 3 mm margin above it. Record each removed region in `frame.excluded` with a reason string. Also implement `clock_and_arclen(frame, xyz_mm)` returning clock position in hours with 12 o'clock = anterior (derive anterior from the image direction cosines in LPS, where anterior is −y — do not assume an array axis) and arc length in mm along the centreline from the superior end.

**7 · Instancing** *(18:30, P1)*
> Implement `instances.find_raw_branches(case, cand, frame, profile, cfg)`. Steps: remove from `cand` the aorta mask dilated by one voxel; label the remainder with 26-connectivity; for each component, find the `frame.legal_wall_np` voxels adjacent to it (its contact patch); label connected components of the contact patches over the wall surface, so one component with two distinct patches yields two candidates; for such components, assign every voxel to the nearest patch by geodesic distance inside the component using `skimage.graph.MCP_Geometric` with multiple seeds and its traceback; compute for each resulting instance its maximum geodesic distance from its patch in mm, its voxel set, patch area in mm², mean HU, and the ratio of mean HU to `profile.a_med`. Return a list of `RawBranch`. Vectorised, no per-voxel loops, all thresholds from `cfg`.

**8 · Per-branch geometry** *(20:30, P1)*
> Implement `geometry.measure(case, raw, frame, profile, cfg)`. Ostium: centroid of the contact patch, converted to physical mm with `TransformContinuousIndexToPhysicalPoint` (sub-voxel, do not round). Path: compute the Euclidean distance transform of the branch voxel set in mm; find the voxel at maximum geodesic distance from the patch, capped at 10 mm; trace a minimum-cost path from the ostium to it with cost `1/(EDT + 0.1)` so the path hugs the lumen centre; resample the path to 0.5 mm arc-length steps in physical mm. Seed: the path point at 5 mm arc length, then snapped to the local EDT maximum within a 1.5 mm neighbourhood. Direction: first principal component of the path points between 1 mm and 7 mm, oriented away from the ostium, normalised. Radius: the EDT value at the seed, in mm. Return `BranchGeom` with everything in physical mm and `truncated_by="length"`. Add a test against `eval/phantom.py` asserting ostium within 1.5 mm, radius within 0.4 mm and direction within 8° of truth, and asserting these still hold on the anisotropic and rotated phantom variants.

**9 · Visual check** *(22:00, P3)*
> Write a function in `src/report.py` that produces one PNG per case for verification. Three panels. Left: coronal maximum-intensity projection of the CT (`ct_np.max(axis=1)`) with the aorta mask boundary overlaid as a contour, detected ostia as dots, and direction vectors projected into the plane as arrows. Middle: the same for the sagittal MIP. Right: a vertical strip of axial slices, one per detected ostium, each cropped to ±40 mm around the aorta centreline, with a marker on the ostium and an in-plane arrow for the direction, labelled with the instance ID and radius. matplotlib only, no interactivity, consistent physical scaling, and it must not crash when there are zero detections.

**10 · Unrolled aortic map** *(23:30, P3)*
> Write a function in `src/report.py` that renders the "unrolled aorta": a 2D matplotlib chart where the x axis is arc length along the aortic centreline in mm from the superior end of coverage, and the y axis is clock position around the aortic circumference running 12 → 3 → 6 → 9 → 12 with 12 o'clock meaning anterior. Plot each detected branch as a circle whose marker size is proportional to its true radius in mm, annotated with instance ID, radius, clock position and takeoff angle relative to the local aortic axis. Shade horizontal bands labelled anterior / lateral / posterior. Plot excluded candidates as hollow grey markers with their reason. This is a clinical planning view — the reader should be able to check the whole case at a glance, so prioritise legibility over decoration. Then a second function wrapping this plus the verification PNG plus a sortable results table into one self-contained HTML file per case with all images inlined as base64 and no external dependencies.

---

## One page to keep on the wall

```
16:40  empty JSON runs                       ← all three
18:30  loader + phantom + legal wall
20:30  end-to-end on phantom  ← CRITICAL
22:00  real F1, predictions committed, v1-safe tag
01:00  F1 ~0.6, no crashes, 3 visual checks
01:45  SUBMITTABLE. sleep.
07:30  fresh clone, no network, works
09:00  feature freeze
10:15  demo rehearsed twice
10:45  SUBMIT
```

Never cut: end caps · adaptive thresholds · try/except · the exact CLI · README · coordinates.
