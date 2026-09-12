# Submission checklist (branchseed_playbook.md §11.1)

- [ ] Source code in the repo, `main` runs
- [ ] `requirements.txt` with **pinned versions**
- [ ] README with exactly **one** setup command and **one** run command
- [ ] The CLI works verbatim: `python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json`
- [ ] Accepts both `.nii` and `.nii.gz` (the data is `.nii`, the brief's example is `.nii.gz`)
- [ ] No manual point placement anywhere; fully automatic
- [ ] Predictions for the whole development set, committed
- [ ] Visual checks for ≥3 cases, committed as files
- [ ] Variable number of detections demonstrated (a case with many, a case with few)
- [ ] Empty `daughters` list handled and tested
- [ ] `parent_instance_id == "aorta"` on every daughter; all instance IDs unique
- [ ] Physical coordinate system preserved and verified on anisotropic + rotated phantoms
- [ ] Runs on all 25 cases, no case-specific code paths, no crashes
- [ ] Verified with **no network** and no GPU, in a **fresh clone and fresh venv**
- [ ] Average runtime and peak memory measured and stated in the README
- [ ] Five-minute demo covering method, runtime and known failure cases
- [ ] Known-failure section in the README
