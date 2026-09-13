# Branchseed Challenge — 2-Person Team Playbook

**This is the canonical planning document for this repo, going forward.** It supersedes `branchseed_playbook.md` (kept at the repo root for archival/reference only — that version was written for a 3-person team and is not updated further). This file is written for **2 people, each on their own laptop, each driving their own AI coding agent**, working against the same shared git repo.

Read `docs/brief.md` first — it is the verbatim challenge specification and the source of truth for output schema and edge cases. This file is the *plan*: how we split the work, how we avoid blocking each other, and what "done" looks like.

---

## 0. Ground truth on where we are right now

This is not a green-field project. As of writing:

- **Implemented and tested (47 passing tests):** `src/io_geom.py`, `src/intensity.py`, `src/candidates.py`, `src/aorta_frame.py`, `src/instances.py`, `src/geometry.py`, `src/gate.py`, `eval/score.py`, `eval/phantom.py`, most of `src/report.py`, `run.py`.
- **Still stubbed (`raise NotImplementedError`):** `eval/batch.py` (both `validate_schema` and `main`), `src/report.write_prediction_json` (dead code right now — `run.py` writes the prediction JSON inline instead).
- **Not yet done against real data:** everything so far has only been validated against `tests/synth.py` (a hand-built cylinder) and `eval/phantom.py` (the official synthetic phantom). No case from the real ~25-case dataset has been run through the pipeline yet.
- **Config lives in `config/default.yaml`.** Every numeric threshold in `src/` must come from there — no exceptions, no matter how small.
- **`CLAUDE.md`** at the repo root is the standing context file every AI agent session should read first — it has the hard coordinate/config/scope rules. Keep it in sync with this file if either changes.

Read the code before writing more of it. Docstrings state units for every argument — that convention must be preserved.

---

## 1. What actually wins this (recap of the brief + rubric)

| Category | Weight | What it really means |
|---|---|---|
| Branch discovery | 45% | P/R/F1 on instances, one-to-one matched. Duplicates count as false positives. |
| Ostium localisation | 25% | Physical mm distance to the reference ostium centre. |
| Daughter-instance quality | 15% | Seed on the matched daughter, direction follows the path, radius consistent with the lumen. |
| Compute efficiency | 10% | Runtime + peak memory, 4 CPU cores, 8 GB RAM, no GPU, no internet, ~60s/case target (not yet finalised). |
| Reproducibility | 5% | Valid output, documented setup, runs on unseen cases without crashing. |

Two brief details with outsized consequences, confirmed verbatim in `docs/brief.md`:

- **"Predictions will be matched to references one-to-one, so duplicate detections count as false positives."** De-duplication is not optional (`src/gate.dedup` already implements this).
- **"its origin meets the minimum size specified with the final dataset"** — the size cutoff (`min_radius_mm` in config) is not yet announced. Expect to re-tune it once it's published; keep a sweep script ready (`eval/score.py --sweep min_radius`).
- **Proximal path definition (brief, exact):** trace up to 10 mm beyond the ostium **or until the first downstream bifurcation, whichever occurs first**. `cfg['trace_max_mm']` already encodes the 10 mm cap; the bifurcation-stop condition is not yet explicitly implemented in `src/geometry.py` — worth checking/adding if time allows (currently the path just runs to the geodesic-extent-capped target, which implicitly stops around forks because `find_raw_branches` treats a common trunk as one instance, but an explicit early-stop-at-first-fork rule is not there).

Everything else in this document exists to serve the 45% and the 25%.

---

## 2. The two roles

The module ownership split below is already reflected in the `Owner: PX` comments at the top of each file, so adopting it costs nothing — it just collapses three original roles into two:

### Person A — "Detector & Geometry" (owns 45% + 15% of the score)

Files: `src/aorta_frame.py`, `src/instances.py`, `src/geometry.py`, `src/gate.py`, plus threshold tuning in `config/default.yaml` under their own keys (see §4 for the shared-file protocol).

Responsibilities:
- Centreline, wall surface, forbidden-surface (end caps + iliac fork) — `aorta_frame.py`.
- Contact-patch instancing and the geodesic-race split logic — `instances.py`.
- Per-branch geometry: ostium, path, seed, direction, radius — `geometry.py`.
- Eligibility gate + de-duplication — `gate.py`.
- Once real data is available: recall-hunting loop (log every rejection with its reason, sweep `min_radius_mm`, fix false-positive causes one at a time).
- Deciding whether to add the brief's explicit "stop at first downstream bifurcation" rule to the path trace in `geometry.py`.

### Person B — "Pipeline, Eval & Delivery" (owns 25% + 10% + 5% + submission)

Files: `src/io_geom.py`, `src/intensity.py`, `src/candidates.py`, `eval/batch.py`, `eval/score.py`, `eval/phantom.py`, `src/report.py`, `README.md`, `requirements.txt`, `docs/checklist.md`.

Responsibilities:
- Loader, crop, resample, coordinate conversions — `io_geom.py` (already done; maintain and fix bugs found against real data).
- Aortic HU profiling and candidate mask — `intensity.py`, `candidates.py` (already done; maintain).
- **Implement `eval/batch.py`** — the biggest open task: walk `data/subjectNNN/`, run every case, write predictions + a runtime/memory CSV, validate schema, never let one case's failure stop the batch.
- Visual checks (§9.1 of the old playbook) and the unrolled aortic map (§9.2) in `src/report.py` — mostly done, verify against real cases once available.
- README, exact-pinned `requirements.txt`, the fresh-clone/no-network rehearsal, the submission checklist walk-through.
- Own the scoring loop once real predictions exist: run `eval/score.py`, report P/R/F1 at 3/5/10 mm, keep the `min_radius_mm` sweep current.

`run.py` and `config/default.yaml` are **shared files** — see §4 for how to edit them without stepping on each other.

If one person finishes their list early, the next highest-value thing is always: **run `eval/batch.py` over real data and read the rejection log** (once it exists) — that's where actual score comes from, not more unit tests on synthetic data.

---

## 3. Git workflow — minimizing waiting and merge conflicts

The goal: **both people push and pull constantly, but almost never touch the same lines.** This is achievable because the module split above is already disjoint at the file level.

### 3.1 Branching

- `main` is always green (`pytest tests/ -q` passes) and always produces valid JSON on the phantom.
- Each person works on their own long-lived branch: `a-detector`, `b-pipeline`. Never work directly on `main`.
- Merge to `main` via fast, frequent small commits — **every 30–60 minutes**, not once at the end of a session. Small diffs are easy to review and never pile up into a scary merge.
- Before merging: `git pull --rebase origin main` on your branch first, resolve locally, then push. Whoever finds a conflict resolves it themselves — don't wait on a call.

### 3.2 Why conflicts should be rare

- Person A never edits `src/io_geom.py`, `src/intensity.py`, `src/candidates.py`, `eval/*.py`, `src/report.py`, `README.md`.
- Person B never edits `src/aorta_frame.py`, `src/instances.py`, `src/geometry.py`, `src/gate.py`.
- The only files both people touch are `run.py` and `config/default.yaml`. Rules for those:
  - **`config/default.yaml`**: only ever *add* new keys or change the *value* of a key you own (see §4). Never delete a key. Never reformat the whole file (no wholesale re-indentation).
  - **`run.py`**: it's a thin wrapper calling the stage functions in order — it should barely change once the stage list is fixed. If you need to change it, keep the diff to the smallest possible hunk, and check `git log run.py` before you start editing to see if it changed recently.
  - **`tests/`**: each person owns the test files for their own modules (`test_aorta_frame.py`, `test_instances.py`, `test_geometry.py`, `test_gate.py` = A; `test_io_geom.py`, `test_score.py`, `test_report.py` = B). `tests/synth.py` is shared infrastructure — treat it like `config/default.yaml` (additive only).

### 3.3 Staying in sync without a call

- Push to your branch after every small win, even mid-task — it costs nothing and lets the other person `git fetch` and look at your diff whenever they want, asynchronously.
- Keep `docs/checklist.md` as the single shared "state of the world" doc — tick items as they become true, so a glance at it (after a `git pull`) tells you what's left without a conversation.
- If you want to run the *other* person's not-yet-merged code (e.g. to test integration), pull their branch directly rather than waiting for a merge to `main`.
- Agree on one merge-to-main sync point roughly every 2 hours (not a hard blocking meeting — just "I'll merge my branch to main around X:00, pull after that if you want my updates").

### 3.4 If a conflict does happen

- `config/default.yaml` conflicts: almost always trivial (both added a new key) — keep both keys, done in 30 seconds.
- `run.py` conflicts: rare, since the stage list is fixed; resolve by re-reading both diffs and keeping the union of calls in the same stage order as the file's docstring already documents.
- Never resolve a conflict by guessing — if a hunk is unclear, ping the other person even if it costs a short wait; a wrong resolution here (e.g. dropping a stage call) is worse than a two-minute delay.

---

## 4. Config ownership convention

To make `config/default.yaml` edits close to conflict-free, prefix a comment on new/actively-tuned keys with who's driving it right now. Example:

```yaml
min_radius_mm: 0.8   # owner: A — sweeping 0.5-2.0, see eval/score.py --sweep min_radius
bone_offset: 300.0    # owner: B — tune only after real-data profiling
```

This is a courtesy convention, not enforced by tooling — but it means a glance at the file tells you who's mid-experiment on a value before you change it out from under them.

---

## 5. Hard rules (do not relitigate these — carried over from `CLAUDE.md`)

- Numpy arrays are **always** `[z, y, x]`. SimpleITK tuples are **always** `(x, y, z)`. Conversions live only in `src/io_geom.py`. Never reverse a tuple inline anywhere else.
- All coordinates crossing a module boundary are **physical mm**, produced via `TransformContinuousIndexToPhysicalPoint` (see the note in `docs/brief.md` on why this repo uses the continuous variant instead of the brief's literal `TransformIndexToPhysicalPoint`). Never pass a voxel index across a module boundary.
- Never compute a distance or direction in voxel units — convert to mm first, then subtract/normalize.
- **No numeric literal in `src/` outside of `config/default.yaml`.** If you catch yourself typing a bare number in a module, stop and add a config key instead.
- No per-voxel Python loops. Vectorised `numpy` / `scipy.ndimage` / `skimage` only (exceptions only where an skimage API genuinely requires seed iteration, as already commented in `instances.py`).
- Target <60 s/case, <8 GB RAM, 4 CPU cores, no GPU, **no internet at runtime**. Never add a dependency that downloads weights or data.
- **Do not implement** (per the old playbook §5.11, still correct): vesselness/Frangi filtering, explicit fork/bifurcation detection beyond what contact-patch instancing already gives for free, half-max-area radius estimation, any learned/pretrained model (TotalSegmentator, nnU-Net, etc.), multi-scale recovery passes, interactive 3D viewers. These are all runtime or overfitting traps for an 18-hour build with ~25 cases.
- Every public function needs a docstring stating the units of every argument. This is what lets two people (and two AI agents) work on disjoint files without a shared mental model going stale.

---

## 6. Immediate task list (in priority order)

1. **Person B: paste the real dataset in, implement `eval/batch.py`.** This unblocks everything else — until this exists, nobody has a real F1 number, a real runtime number, or real predictions to commit.
2. **Person A: once `batch.py` produces real predictions, start the recall-hunting loop** from §7 below (this is where most of the score comes from).
3. **Person B: fix `requirements.txt` to exact pins** (`==`, not `>=`) and rehearse a fresh-clone/no-network install.
4. **Person B: fix `.gitignore`** — it currently excludes `data/` and `results/` wholesale, which will also silently swallow the dev-set predictions and visual-check PNGs the submission requires being committed. Either write those deliverables somewhere not covered by the blanket ignore (e.g. `docs/dev_predictions/`, `docs/visual_checks/`), or add explicit `!results/predictions/**.json`-style exceptions.
5. **Person A: decide on and (if time allows) implement the brief's explicit "stop path trace at first downstream bifurcation"** rule in `geometry.py`, distinct from the existing 10 mm hard cap.
6. **Both: once real data is in, re-run `pytest tests/ -q` and treat any regression as a same-day fix**, not a "later" item — this is the guardrail that keeps two people editing in parallel from silently breaking each other's assumptions.
7. **Person B: implement `src/report.write_prediction_json`** properly (or delete the stub) so there's one source of truth for the output schema, rather than `run.py` duplicating the dict construction inline.

---

## 7. The recall/precision loop (once real data + `batch.py` exist)

Re-score after every change, strictly in this order (carried over from the original playbook, still the right order):

1. **Recall first.** Turn on `cfg['log_rejections']`, run the batch, read every rejected candidate's reason. One cause usually explains most of the misses.
2. **Sweep `min_radius_mm`** from 0.5 to 2.0 via `eval/score.py --sweep min_radius`. Pick a value mid-plateau, not on a spike (a spike means overfitting to the dev cases).
3. **False positives by cause**, one at a time — they cluster (missed end cap, bone, iliac fork, organ leak). Fix the cause, don't just tighten a global threshold (that trades FPs for FNs and nets nothing).
4. **De-duplication** — verify `gate.dedup` isn't over- or under-merging on real cases.
5. **Ostium accuracy** — sub-voxel centroid, mid-wall nudge; cheap 25%-of-score wins.

Log both people's F1 numbers somewhere shared and dated (e.g. append a line per run to a `docs/scoreboard.md` or similar) so progress is visible without a call.

---

## 8. Submission checklist

Kept in `docs/checklist.md` — walk it line by line before submitting. Key items to double check given the current repo state:

- [ ] `eval/batch.py` implemented and run over all real cases, zero crashes
- [ ] Predictions for the whole dev set committed (check `.gitignore` doesn't eat them)
- [ ] Visual checks for ≥3 real cases committed as files
- [ ] `requirements.txt` uses exact pins, verified in a fresh clone with no network
- [ ] Average runtime and peak memory measured and stated in `README.md`
- [ ] `docs/brief.md` matches the real brief (done — verified against the source PDF)
- [ ] README known-limitations section reflects actually-observed failures, not guesses

---

## 9. Reference: original 3-person playbook

`branchseed_playbook.md` at the repo root has the full domain background (anatomy, HU ranges, coordinate conventions in more depth), the original prompt pack for AI agents, and the detailed rationale behind every config default. It is still accurate on all of that — only its clock/roles/team-size assumptions are superseded by this file. Read it once for context; use *this* file for day-to-day coordination.
