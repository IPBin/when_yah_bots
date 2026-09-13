# Branchseed Challenge

Automatic detection of arterial branches arising from the abdominal aorta in CTA volumes.

## Setup
pip3 install SimpleITK numpy scipy scikit-image PyYAML matplotlib

## Run
python3 run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json

## Method
Classical image processing pipeline: adaptive aorta-relative thresholding, hysteresis candidate masking, bone suppression, end-cap exclusion, contact-patch instancing with geodesic separation, EDT-based radius estimation.

## Known limitations
- Lumbar arteries under ~1mm radius may be missed
- Case 24 has non-orthonormal direction cosines and fails to load
- Heavy wall calcification can produce occasional false positives
