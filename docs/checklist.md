# Submission checklist (branchseed_playbook.md §11.1)

- [x] Source code in the repo, `main` runs
- [x] `requirements.txt` with **pinned versions**
- [x] README with exactly **one** setup command and **one** run command
- [x] The CLI works verbatim: `python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json`
- [x] Accepts both `.nii` and `.nii.gz` (verified against real dev cases: mix of both extensions)
- [x] No manual point placement anywhere; fully automatic
- [x] Predictions for the whole development set, committed (`results/predictions/`, 5/5 real dev cases)
- [x] Visual checks for ≥3 cases, committed as files (`results/visual_checks/`, orig20/21/22)
- [x] Variable number of detections demonstrated (0, 2, 7, 8, 2 across the 5 dev cases)
- [x] Empty `daughters` list handled and tested (orig19 currently yields 0 detections)
- [x] `parent_instance_id == "aorta"` on every daughter; all instance IDs unique (checked by `eval/batch.validate_schema`, 0 schema errors on the dev set)
- [x] Physical coordinate system preserved and verified on anisotropic + rotated phantoms (`tests/test_pipeline_integration.py`, full `run_case` through real NIfTI I/O, identity vs. 0.7/0.7/2.0mm rotated grid)
- [ ] Runs on all 25 cases, no case-specific code paths, no crashes (only 5/25 real cases available so far)
- [x] Verified with **no network** and no GPU, in a **fresh clone and fresh venv** (pip install -r requirements.txt + CLI run rehearsed in a scratch venv)
- [x] Average runtime and peak memory measured and stated in the README (0.7-4.5s/case, 65-252MB/case on the dev set)
- [x] Five-minute demo covering method, runtime and known failure cases (`docs/demo_script.md`)
- [x] Known-failure section in the README
