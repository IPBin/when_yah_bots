# Scoreboard (real-data smoke tests, no reference annotations yet)

Dated notes on daughter counts / crashes seen while running the pipeline
against the real cases dropped into `dataset/` (orig19-23 + mask19-23). No
reference JSON is available for these cases yet, so this is a recall/crash
sanity log, not a scored F1 -- update it with real P/R/F1 once
`eval/batch.py` + reference annotations exist (§7 of the team playbook).

## 2026-09-13 -- Person A, recall-hunting pass #1

Before any change: 0/5 real cases produced a single daughter (orig19: 0
raw branches even touched the legal wall; the other 4 produced a handful of
raw branches, all rejected by `excessive_extent`/`insufficient_extent`).

Root causes found and fixed:

1. **`patch_bridge_mm` (new config key, default 6.0mm)** -- the fixed
   2-voxel dilation used to bridge the gap between a candidate branch
   component and its own contact patch on the legal wall (in both
   `instances.find_raw_branches`/`_split_component` and `geometry.measure`)
   was tuned against the synthetic phantom, where that gap is exactly the
   1-voxel aorta-mask buffer. On real segmentations the gap is up to
   5-6mm (partial-volume / mask-noise at the aortic wall), so almost every
   real branch component never touched the legal wall at all and silently
   produced zero raw branches. Made the dilation radius a config key
   (`cfg['patch_bridge_mm']`) instead of a hardcoded `iterations=2`.
2. **`run.run_case` had no per-candidate exception handling around
   `geometry.measure`** -- one degenerate raw branch (too few voxels for
   the MCP path solver to route to its own extent target) raised
   `ValueError: no minimum-cost path was found`, which propagated all the
   way up and discarded every other valid daughter for that case (case
   orig20 went from 8 plausible-looking raw branches to 0 daughters in the
   final JSON). Wrapped the per-branch `measure` call in
   `run.run_case` in its own try/except, logged as `rejected:
   measure_failed (...)`, so one bad candidate no longer sinks the whole
   case.

After both fixes, `python run.py` on the 5 real cases:

| case | daughters (post-fix) | runtime (s) |
|---|---|---|
| orig19 | 7 | 1.13 |
| orig20 | 9 | 2.06 |
| orig21 | 9 | 2.27 |
| orig22 | 8 | 5.96 |
| orig23 | 5 | 1.82 |

All well under the 60s/case target. No crashes. `pytest tests/ -q`: 49/49
passing (one test's tolerance in `tests/test_instances.py` had to widen to
scale with the new `patch_bridge_mm`-derived dilation radius).

Next: sweep `patch_bridge_mm` and `min_radius_mm` together once reference
annotations for these cases (or more real cases) are available -- right
now 5-9 daughters/case is a plausibility check, not a precision/recall
number. Also worth checking whether `excessive_extent`/`max_extent_mm`
(40mm) and `patch_too_large` (`patch_area_max_mm2`, 120mm^2) are still the
right cutoffs now that patches are found with a wider bridge (patches are
measurably larger post-fix, since the search radius is wider).

## 2026-09-13 -- Person A, recall-hunting pass #2 (regression fix)

Pass #1's `patch_bridge_mm` fix was a **fixed** dilation of `bridge_iters`
voxels applied to every component, which regressed the synthetic phantom
(`eval/phantom.py`, `data/phantom_p3/`): the phantom went from 1/1 correct
daughters (committed `data/phantom_p3/prediction.json`) to 0/1, because
dilating a whole tubular component by ~4 voxels smears its "shadow" across
a much wider strip of the legal wall than the true, tight ostium contact
point -- `patch_area_mm2` on the phantom's real branch blew up from ~9mm^2
to 236-298mm^2, past `patch_area_max_mm2` (120mm^2), and its
`geodesic_extent_mm` also shrank under `min_extent_mm` because the wider
patch ends up closer (in geodesic terms) to the target voxel.

Fix: made the bridge **adaptive** instead of fixed. `find_raw_branches` now
tries `bridge_iters = 1, 2, ..., max_bridge_iters` (the latter from
`cfg['patch_bridge_mm']`) and stops at the *first* iteration where the
dilated component touches the legal wall, using that (minimal) patch. This
keeps the phantom's tight 1-voxel gap exactly as tight as before while
still finding real cases' wider (up to ~6mm) gaps when a 1-2 voxel bridge
genuinely isn't enough.

Result: phantom back to 1/1 correct daughter (`ostium_xyz_mm` matches the
committed reference exactly: `[59.5, 49.5, 80.0]`). Real cases *improved*
over pass #1 (tighter patches -> less over-rejection):

| case | daughters (pass #1, fixed bridge) | daughters (pass #2, adaptive bridge) |
|---|---|---|
| orig19 | 7 | 8 |
| orig20 | 9 | 12 |
| orig21 | 9 | 17 |
| orig22 | 8 | 11 |
| orig23 | 5 | 7 |

Runtimes unchanged (1.7-6.6s/case, still far under the 60s target).
`pytest tests/ -q`: 49/49 passing. This is the sharper lesson for future
threshold work on this repo: **always re-check the phantom after any
change that could touch patch geometry**, not just the real-case daughter
counts -- the phantom is the only ground truth we currently have.
