# 5-minute demo script

Talking points + exact commands for the submission demo (checklist item:
"Five-minute demo covering method, runtime and known failure cases").

## 1. Method (60s)
Classical image-processing pipeline, no learned model:
adaptive aorta-relative HU thresholding -> hysteresis candidate mask ->
bone/end-cap/iliac-fork exclusion -> contact-patch instancing with geodesic
separation -> per-branch ostium/seed/direction/radius from the aortic wall
geometry. Every threshold lives in `config/default.yaml`, nothing hardcoded
in `src/`.

## 2. Run one case live (60s)
```
python run.py --image dataset/orig21.nii.gz --aorta-mask dataset/mask21.nii --output demo_out.json
```
Point out: works on both `.nii` and `.nii.gz`, physical mm coordinates in
the output, `branch_NNN` IDs with `parent_instance_id: "aorta"`.

## 3. Batch + visual check (60s)
```
python eval/batch.py --data dataset --out results/predictions
```
Open `results/visual_checks/orig22_check.png` (8 detections, our densest
dev case) -- coronal/sagittal MIP with ostia + direction arrows, plus a
per-branch axial crop.

## 4. Runtime & memory (30s)
From `results/predictions/batch_summary.csv` on the 5-case dev set:
0.7-4.5s/case, 65-252MB peak (Python-heap; SimpleITK native allocations
push true RSS somewhat higher) -- both well inside the 60s/8GB budget.

## 5. Known failure cases (60s)
- `orig19`: zero detections. The candidate mask is populated (66k voxels)
  but no raw branch instance survives -- either a genuinely branch-free
  short aortic segment, or an instancing edge case worth a closer look.
- Lumbar arteries under ~1mm radius are missed (below `min_radius_mm`,
  which is still unannounced by the organizers -- swept 0.5-2.0mm via
  `eval/score.py --sweep min_radius` once reference data exists).
- Heavy wall calcification occasionally produces a false positive.
- Case 24 (non-orthonormal direction cosines) fails to load.

## 6. Close (30s)
Full test suite: `pytest tests/ -q` (49 passing, includes an anisotropic +
rotated-grid coordinate regression test). Fresh-venv, no-network install
rehearsed against the pinned `requirements.txt`.
