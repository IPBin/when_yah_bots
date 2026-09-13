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

## Performance
Measured with `eval/batch.py` over the 5-case dev set (`results/predictions/batch_summary.csv`), single process, 4 CPU cores, no GPU:
- Runtime: 0.7-4.5s/case, mean ~1.8s/case (well under the 60s/case target).
- Peak memory: 65-252 MB/case (Python-heap peak via `tracemalloc`; a lower bound on true RSS since it does not see memory allocated by SimpleITK's native extensions, but well within the 8GB budget with wide margin).

## Known limitations
- Lumbar arteries under ~1mm radius may be missed
- Case 24 has non-orthonormal direction cosines and fails to load
- Heavy wall calcification can produce occasional false positives
- One dev case (orig19) currently yields zero detections; under investigation
