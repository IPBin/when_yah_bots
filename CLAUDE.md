# Branchseed Challenge

## Task
Detect arteries branching directly off a given abdominal aorta mask in CTA volumes.
Output JSON with ostium_xyz_mm, seed_xyz_mm, radius_mm, direction_xyz per branch.
Full spec: docs/brief.md (verbatim challenge brief).
Team plan / module ownership / git workflow: docs/team_playbook.md (read this first —
it supersedes branchseed_playbook.md, which is kept only for domain background/rationale).
Scoring: 45% detection F1, 25% ostium distance, 15% geometry, 10% runtime, 5% repro.

## Hard rules
- Numpy arrays are ALWAYS [z,y,x]. SimpleITK tuples are ALWAYS (x,y,z).
  Conversions live only in src/io_geom.py. Never reverse a tuple inline.
- All coordinates crossing a module boundary are physical mm via
  TransformContinuousIndexToPhysicalPoint. Never voxel indices.
- Never compute a distance or direction in voxel units. Convert to mm first.
- No numeric constants in src/. Everything from config/default.yaml.
- No per-voxel Python loops. Vectorised numpy / scipy.ndimage / skimage only.
- Target <60s per case, <8GB RAM, 4 CPU cores, no GPU, NO INTERNET at runtime.
  Never add a dependency that downloads weights or data.
- DO NOT implement: vesselness/Frangi filtering, fork detection, half-max radius,
  any learned model, any pretrained segmentation network. See playbook section 5.11.
- Every public function needs a docstring stating the units of every argument.

## Commands
Install: pip install -r requirements.txt
Run one: python run.py --image X.nii --aorta-mask Y.nii --output out.json
Run all: python eval/batch.py --data data/ --out results/
Score:   python eval/score.py --pred results/ --ref data/reference/
Test:    pytest tests/ -q
