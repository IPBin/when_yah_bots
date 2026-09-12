# Branchseed Challenge — Team Roadmap

*A plan for four people with strong general problem-solving skills, no anatomy background, and a deadline.*

---

## 0. Read this page first

Three things decide whether you win, and none of them is "having the cleverest algorithm."

**1. The rubric is 45% "did you find the right number of branches."** Not "were you accurate," not "was it elegant." Detection count. A pipeline that reliably finds 9 of the 11 real branches with 1 false positive beats a beautiful pipeline that finds the 4 famous ones perfectly. Almost everything in this document serves that number.

**2. 15% of the score is free if you don't crash.** Compute efficiency (10%) and reproducibility (5%) are handed to teams who write a boring, single-threaded, `scipy`-only program that never throws an exception and has a one-line setup command. Many hackathon teams lose all 15 points to a dependency that needed internet access or a case that segfaulted.

**3. You cannot tune what you cannot measure.** You get reference answers for only a small development subset. Your first real deliverable is not a detector — it's a **scoring harness** and a **synthetic test phantom**. Teams that build these in hour 3 spend the rest of the event improving a number. Teams that skip them spend the rest of the event arguing about whether the output "looks right."

There is one more thing, and it's the tiebreaker between good teams:

**4. The brief contains a hidden ask.** "Display information in a unique way that will be useful for clinicians." Most teams will render a 3D blob with arrows. Section 10 shows you what the surgeons who'd actually use this look at, and how to build it in an afternoon. It's the cheapest differentiator on the board.

---

## 1. What the scoring actually rewards

| Category | Weight | What it really means for you |
|---|---|---|
| Branch discovery | 45% | Precision, recall, F1 on branch **instances**. Missing small branches and emitting duplicates are the two ways teams lose here. |
| Ostium localisation | 25% | Millimetre distance from your predicted opening to theirs. Dominated by (a) coordinate-convention correctness and (b) whether you put the point on the aortic wall vs. somewhere along the branch. |
| Daughter-instance quality | 15% | Seed point lies inside the right branch, direction follows the branch, radius is plausible. Pure geometry — fully testable on synthetic data. |
| Compute efficiency | 10% | Runtime + peak memory, CPU-only, 4 cores, 8 GB. Target < 60 s/case average. Crop aggressively and you'll land at 10–20 s. |
| Reproducibility | 5% | Valid output, documented setup, runs on unseen cases. Free points. |

Two sentences in the brief have outsized consequences:

- *"Predictions will be matched to references one-to-one, so duplicate detections count as false positives."* → You need a de-duplication step, and you need to be careful about the case where one real branch splits into two of your detections.
- *"its origin meets the minimum size specified with the final dataset"* → **The size cutoff is not yet known.** Make it a config value, not a number buried in your code, and produce a score-vs-cutoff curve so you can retune in 60 seconds when they announce it. This single parameter will swing your recall more than any other decision you make.

---

## 2. Crash course: the 20 minutes of domain knowledge you need

You don't need to learn anatomy. You need to learn enough to stop being surprised by the images.

### 2.1 The picture

The **aorta** is the body's main pipe. Blood leaves the heart, arcs over, and runs straight down in front of the spine. The stretch in the belly is the **abdominal aorta** — that's your "parent." Along the way, smaller pipes peel off it to supply organs. Those are your "daughters." At the bottom, the aorta forks into two pipes going to the legs (the **iliac arteries**) — that fork is explicitly out of scope.

An **ostium** is just the mouth: the hole in the aortic wall where a daughter pipe leaves. Think of a garden hose with smaller hoses spliced into its side. The ostium is the splice point.

### 2.2 The branches you should expect, top to bottom

This list matters because it tells you *how many detections is plausible*. Radii are approximate half-widths of the lumen (the open channel).

| Branch | Count | Direction off the aorta | Typical radius |
|---|---|---|---|
| Inferior phrenic | 2 | up/sideways, near the diaphragm | ~0.7 mm |
| **Celiac trunk** | 1 | straight forward (anterior) | ~3.5 mm |
| Middle suprarenal | 2 | sideways | ~0.5 mm |
| **Superior mesenteric (SMA)** | 1 | forward, ~1 cm below celiac | ~3.5 mm |
| **Renal arteries** | 2 (+ extras) | straight out left and right | ~2.5 mm |
| Accessory renal | 0–2, ~30% of people | sideways, near the main renals | ~1.5 mm |
| Gonadal | 2 | forward-and-sideways, steeply downward | ~0.7 mm |
| **Lumbar arteries** | 4 pairs = 8 | **backwards**, toward the spine | ~1.0 mm |
| **Inferior mesenteric (IMA)** | 1 | forward and slightly left | ~1.3 mm |
| Median sacral | 1 | backwards, at the very bottom | ~0.7 mm |

**Consequences you should internalise:**

- A fully-covered aorta can plausibly contain **10–20 eligible branches**, not 5. If your pipeline finds the celiac, SMA, and both renals and stops, your recall is ~30% and you have thrown away most of 45 points.
- The lumbar arteries point **backwards into the spine**. Bone is bright on CT. This is your single worst source of confusion, and it's where half of your missed branches will live.
- "Anatomical coverage varies" means some cases are cropped and genuinely contain 2 branches. Your count must be data-driven. Never hard-code "there should be a celiac here."
- A **common trunk** (the celiac is one — it divides into three vessels about 1–2 cm out) counts as **one** aortic daughter. So: trace outward from the aorta, and stop at the first fork.
- A vessel arising from another daughter is not your problem. Same rule handles it: only components touching the *aortic* wall count.

### 2.3 What CT actually gives you

A CT volume is a 3D array of numbers in **Hounsfield Units (HU)**, a calibrated density scale. Air is −1000, water is 0. Approximate values you'll meet:

| Tissue | HU |
|---|---|
| Lung / air | −1000 to −500 |
| Fat | −100 to −50 |
| Water / simple fluid | ~0 |
| Muscle, unenhanced blood, liver | 30 to 80 |
| **Contrast-filled artery (your target)** | **200 to 500** |
| Enhanced kidney tissue | 100 to 250 |
| Cancellous (inner) bone | 100 to 300 |
| **Cortical (outer) bone, calcified plaque** | **500 to 1900** |

These are CT **angiograms** (CTA): iodine dye was injected, so arteries glow. That's the whole basis of your detector — the daughters are bright tubes physically attached to a bright tube you've been given a map of.

The three traps in that table:

1. **Bone overlaps your target range.** The spine sits directly behind the aorta and the lumbar arteries run toward it.
2. **Calcified plaque** in the aortic wall is very bright and sits exactly where ostia are. It looks like a tiny bump. Reject by size and by failure to extend ≥5 mm.
3. **Enhanced organs** (kidney cortex especially) are bright and sit right at the end of the renal arteries. Your region-growing will happily flood into a kidney if your threshold is too low.

A key mitigation, and one of the strongest ideas in this document: **calibrate everything against the aorta you were given.** Arteries carry the same dye as the aorta at the same moment, so their lumen HU is close to the aortic lumen HU. Measure the aortic lumen's median and spread *in this case*, and set thresholds relative to it. This automatically handles differences in contrast timing, scanner, and patient between cases — which is exactly what will break a hard-coded `HU > 200`.

### 2.4 Slices and axes

- **Axial** = the horizontal cross-section (the "salami slice" shown in the brief). Usually the third array axis.
- **Coronal** = front-to-back split (like a door).
- **Sagittal** = left-to-right split.
- **Anterior/posterior** = front/back. **Superior/inferior** = up/down. **Left/right** are the *patient's*, so on an axial slice viewed conventionally, patient-left appears on the image's right.

### 2.5 The coordinate gotcha that will cost you 25 points

`ostium_xyz_mm` must be in physical millimetres, obtained through SimpleITK. A voxel index `(i,j,k)` becomes a physical point via three things: **origin** (where voxel 0,0,0 sits in space), **spacing** (mm per voxel, often non-cubic like 0.7×0.7×1.0), and **direction cosines** (a 3×3 matrix describing how the array axes are rotated relative to the patient).

Do it like this, always:

```python
import SimpleITK as sitk
img = sitk.ReadImage("orig1.nii")
# index order is (x, y, z) = (i, j, k) — the OPPOSITE of numpy's [k, j, i]
p_mm = img.TransformContinuousIndexToPhysicalPoint((float(i), float(j), float(k)))
```

Four rules, violate none of them:

1. **`sitk.GetArrayFromImage` returns `[z, y, x]`.** SimpleITK's own index methods take `(x, y, z)`. Every conversion between numpy indexing and SimpleITK indexing is a reversal. Write two helper functions, `np_to_sitk_index` and `sitk_to_np_index`, use them everywhere, and never reverse a tuple inline.
2. **Never compute distances or directions in voxel units.** Convert both endpoints to physical mm first, *then* subtract. This makes anisotropic spacing and rotated direction cosines handle themselves.
3. **SimpleITK works in LPS** (x→patient-left, y→posterior, z→superior), while NIfTI files and 3D Slicer are **RAS**. The sign of x and y flips between them. Since the brief mandates SimpleITK, do everything in SimpleITK and you're consistent with the graders. But the moment you compare against a point you clicked in Slicer, negate x and y.
4. **`TransformContinuousIndexToPhysicalPoint`, not `TransformIndexToPhysicalPoint`**, for centroids. Your ostium centre is an average of voxel positions and lands between voxels. Rounding it away costs you sub-millimetre accuracy for free, and ostium localisation is 25% of the score.

---

## 3. The problem as an engineering spec

Strip the anatomy and here's the actual task:

> **Input:** a 3D scalar field (CT, in HU) and a binary mask marking one connected tube inside it (the aorta).
> **Output:** a list of every *other* bright tube that is physically fused to the given tube, where "bright" is defined relative to the given tube's own interior. For each, report the fusion point, an outward unit direction, a point 5 mm out along it, and its local half-width.
> **Constraints:** a tube counts only if it extends ≥5 mm beyond the parent wall and exceeds an unknown minimum size. The parent tube's flat cut ends are not fusion points. The bottom fork is not a fusion point. One instance per real tube, no duplicates.

That reads like a connected-components problem, because it essentially is one. The hard parts are all *separation* problems:

- separating branches from bone, veins, and enhancing organs;
- separating two nearby branches that your threshold has bridged into one blob;
- separating a genuine branch from the aorta's own cropped end face;
- separating "one branch that forks 8 mm out" from "two branches."

Notice what the task is *not*: it is not segmentation, not classification, not naming, not deep learning. With 25 cases, a handful of reference annotations, and a no-GPU no-internet evaluation box, **classical image processing is the correct answer** and you should say so confidently in your demo. If you want a learned component, the right place is one small decision — accept or reject a candidate — trained on features you already computed, pickled into the repo (Section 7.6). Not end-to-end.

---

## 4. The recommended pipeline

Ten stages. Each is independently testable, which is what lets four people work at once. Stage numbers map to module names in Section 5.

```
CT + aorta mask
   │
   ├─ 1. Load, validate, crop to ROI, resample to 1 mm isotropic
   ├─ 2. Profile the aortic lumen → adaptive HU thresholds
   ├─ 3. Build "bright vessel candidate" mask; suppress bone
   ├─ 4. Aorta centreline; wall surface; outward normals; clock frame
   ├─ 5. Mark forbidden surface: cropped end caps + iliac bifurcation
   ├─ 6. Candidate components: bright stuff touching the legal wall
   ├─ 7. Split/merge contact patches → one instance per real ostium
   ├─ 8. Per branch: proximal centreline, stop at first fork
   ├─ 9. Per branch: seed @5 mm, direction, radius @seed
   └─ 10. Eligibility gate + de-duplication → JSON + visual report
```

### Stage 1 — Load, crop, resample

**Crop first.** Take the aorta mask's bounding box, pad by 50 mm in every direction, and throw away everything else. This is the single biggest runtime win available: you go from a 512×512×600 volume to maybe 150×150×450, a 15× reduction. Do it before anything else touches the data.

**Then resample to 1.0 mm isotropic** with linear interpolation for the CT and nearest-neighbour for the mask. Reasons:

- Every morphological operation (dilation, distance transform, skeletonisation) assumes cubic voxels. On 0.7×0.7×1.0 data, a "5 mm dilation" is three different distances depending on direction, and your geometry silently skews.
- Distance transforms become directly readable in mm.
- It bounds runtime: a case scanned at 0.5 mm slices no longer costs 4× as much.

The crucial property: **the resampled image still carries a valid origin/spacing/direction**, so `TransformContinuousIndexToPhysicalPoint` on the resampled grid returns correct physical mm in the original coordinate system. You never have to convert back manually. Verify this with an assertion in your tests (Section 8.2) — take a voxel in the original, find its physical point, map it into the resampled grid, map back, and check you're within 0.5 mm.

Consider 0.8 mm isotropic if runtime allows; lumbar arteries at ~1 mm radius are 2 voxels wide at 1.0 mm and only marginally resolvable. Make the resample spacing a config value and test both.

Also here: sanity-validate the inputs. Same geometry between image and mask? Mask non-empty? Mask a single connected component? Log warnings, never crash.

### Stage 2 — Profile the aortic lumen (the case-adaptive core)

```
aorta_core = binary_erosion(aorta_mask, radius=2mm)   # avoid partial-volume wall voxels
lumen_hu   = CT[aorta_core]
A_med  = median(lumen_hu)
A_p10  = 10th percentile(lumen_hu)
A_iqr  = interquartile range
```

Derive your thresholds from these, e.g.:

- `T_vessel = max(A_med - 2.0 * (A_med - A_p10), 0.55 * A_med, 120)` — the floor at 120 HU stops you flooding into unenhanced soft tissue on a poorly-timed scan.
- `T_bone = A_med + 300` (roughly) — above this, treat as bone/calcification candidate.

Expose all of these as config multipliers. Log the derived values for every case; when a case behaves oddly, this log tells you why in one glance.

**Why this matters:** contrast timing varies enormously between patients. One case's aorta may sit at 480 HU and another's at 210 HU. A fixed `>200` threshold finds nothing in the second case and floods into the kidneys in the first. Aorta-relative thresholding is the difference between a pipeline that works on 20 of 25 cases and one that works on 8.

Also record `A_med` for later use as a *similarity* test: a component whose mean HU is within ~25% of `A_med` is very likely an artery; a component sitting at 100 HU is a vein or an organ, even if it's technically above threshold. Veins in an arterial-phase scan are consistently darker than arteries, and this test is nearly free.

### Stage 3 — Candidate mask and bone suppression

```
bright = CT > T_vessel
bone   = (CT > T_bone)  dilated by ~1.5 mm
candidate = bright & ~bone & roi
candidate |= aorta_mask         # make sure the parent is fully included
```

Bone suppression by threshold alone is imperfect: dense contrast can exceed 500 HU and cancellous bone falls below it. Two upgrades, in order of cost:

1. **Morphological reasoning.** Bone in the abdomen is *large and blobby/plate-like*; vessels are *thin and tubular*. After thresholding, run a connected-component pass and discard any non-aorta component larger than some generous volume (say 50 cm³) that isn't attached to the aorta. Cheap, catches the vertebrae wholesale.
2. **Vesselness filtering.** `sitk.ObjectnessMeasureImageFilter` (Hessian-based, this is the Frangi/Sato family) scores each voxel on how tube-like its neighbourhood is, at a given scale. Run it at 2–3 scales (σ ≈ 0.8, 1.5, 3.0 mm) on the cropped ROI, take the max, and use it as a *soft gate* — e.g. require `vesselness > v_min` for small candidates while letting large obviously-attached ones through. Set `ObjectDimension=1` for tubes. On a cropped ROI at 1 mm this takes a few seconds, which your budget can absorb.

Start with (1). Add (2) only if your false-positive rate near the spine is hurting, and measure whether it actually helps — vesselness filters also attenuate the short proximal stumps you care about, so it is not automatically a win.

A third technique worth 10 minutes: **hysteresis**. Grow from a high, confident threshold (`0.85 * A_med`) outward, permitting expansion into voxels above a lower threshold (`0.55 * A_med`) only where connected to confident seed voxels. `skimage.filters.apply_hysteresis_threshold` does this in one call. It substantially reduces leakage into organs while keeping thin distal lumen.

### Stage 4 — Centreline, wall surface, and the clock frame

The abdominal aorta runs roughly vertically, which permits a dead-simple and very robust centreline:

```
for each axial slice k where aorta_mask has voxels:
    take the largest connected component in that slice
    centreline[k] = centroid of that component
smooth centreline over k with a spline or a ~10 mm moving average
```

This is more reliable for near-vertical vessels than 3D skeletonisation, which produces spurs you then have to prune. If a case has a very tortuous or aneurysmal aorta you can fall back to `skimage.morphology.skeletonize_3d` plus longest-path pruning — but validate visually before assuming you need it.

From the centreline you get three things you'll use constantly:

- **Wall surface**: `aorta_mask & ~binary_erosion(aorta_mask, 1 voxel)`.
- **Outward normal** at a wall voxel: normalise `(wall_point_mm − centreline_point_mm)`, using the centreline point at the same slice. Good enough, and more stable than surface-mesh normals.
- **Clock angle**: in the axial plane, angle of the outward normal measured from anterior = 12 o'clock, increasing toward patient-left. Anterior is `−y` in LPS, so build the frame from the image's direction cosines rather than assuming an array axis. This powers both a sanity check (celiac/SMA near 12 o'clock, renals near 3 and 9, lumbars near 5–7) and the clinician view in Section 10.
- **Arc length** along the centreline from the superior end of coverage — the other axis of the Section 10 view.

### Stage 5 — Forbidden surface (the end-cap trap)

**This is the most commonly fumbled requirement in the brief,** and it's called out explicitly: *"The flat superior and inferior ends created by cropping are not branch origins."*

Here's why it bites. The aorta mask stops at the edge of the annotated region, but the *actual* aorta continues, full of bright contrast. So the aorta's flat top face has a large, bright, perfectly-attached blob hanging off it that extends far more than 5 mm. A naive pipeline reports that as a giant branch. It will do so on **every single case**, costing you 25 false positives.

Fix: exclude from the searchable wall surface

- all wall voxels within ~4 mm of the topmost and bottommost slices of the aorta mask;
- any wall voxel whose outward normal is within ~35° of the local centreline tangent (i.e. it's part of a cap, not the side wall).

**The iliac bifurcation** needs the same treatment, since the terminal fork is out of scope. Detect it: walk down the slices and find the first slice where the aorta mask has two separate components of comparable size. Exclude the wall from a few mm above that point downward. If the mask ends *just above* the bifurcation, the end-cap rule already covers it.

**Design suggestion that will impress judges:** don't silently drop these. Put them in a separate top-level key in your output:

```json
"excluded_candidates": [
  {"reason": "superior_end_cap", "ostium_xyz_mm": [...]},
  {"reason": "iliac_bifurcation", "ostium_xyz_mm": [...], "note": "optional extension"}
]
```

The `daughters` list stays clean for scoring, and you've visibly demonstrated that you read and understood the edge-case section. The brief even says the iliacs "may be evaluated separately as an optional extension" — so having them already computed and labelled is a free bonus if they do.

### Stage 6 — Candidate components

```
non_aorta = candidate & ~binary_dilation(aorta_mask, 1 voxel)
label each connected component of non_aorta (26-connectivity)
keep components adjacent to the LEGAL wall surface from Stage 5
```

For each kept component compute, in mm:
- **contact patch** = the legal wall voxels adjacent to it;
- **maximum geodesic distance** from the contact patch through the component (i.e. how far out the tube goes without leaving the lumen) — this is your ≥5 mm eligibility test, and it must be geodesic, not Euclidean, because branches curve;
- volume, mean HU, max vesselness, elongation.

Geodesic distance inside a binary mask from a seed set: `skimage.graph.MCP_Geometric` or `scipy.ndimage.distance_transform_edt` on a masked domain via an MCP traversal. `MCP_Geometric(costs=ones_inside_component, sampling=(1,1,1)).find_costs(seed_indices)` gives you a distance field in mm directly. This one object does most of the work in Stages 6, 7, and 8 — learn it properly.

### Stage 7 — From contact patches to instances

This stage is where the 45% is won or lost. Two failure directions, and you need both guards:

**Over-merging.** Celiac and SMA are ~10 mm apart; the two renals face each other; accessory renals sit beside main renals. Partial-volume blur or a slightly low threshold bridges them into one component, and you report 1 branch where there are 2. The brief is explicit: *"Two nearby origins must be returned as two instances when they are separate at the aortic wall."*

The clean solution: **instance-per-contact-patch, not instance-per-component.** Run connected components *on the contact patches over the wall surface*. Each distinct patch is a candidate ostium. Then run a **multi-seed geodesic race** through the shared component: every voxel is assigned to whichever patch reaches it first (`MCP_Geometric.find_costs` with multiple seeds returns a `traceback` array that gives you exactly this). Now a bridged blob splits into two branches, each with its own path.

**Over-splitting.** Noise, a calcification sitting in the ostium, or a stair-step artefact can break one contact patch into two, and you report 2 branches where there's 1 — and duplicates count as false positives. Guard: merge two patches if their centroids are within ~3 mm **and** their outward paths, sampled at 5 mm, diverge by less than ~30°. Two real branches 3 mm apart at the wall almost always head in clearly different directions; a split artefact produces two paths going the same way.

Keep the merge distance small and the angle test strict. The brief's explicit instruction to separate nearby origins means the graders' reference annotation *does* separate them, so bias your parameters toward splitting.

### Stage 8 — Proximal path, stopping at the first fork

For each instance, from its ostium centre, build a short centreline outward:

1. Compute the Euclidean distance transform (EDT) of the branch's voxel set — this gives "distance to the vessel edge," maximal along the centre.
2. Find the target: the voxel at maximum geodesic distance from the ostium, capped at 10 mm.
3. Trace a path from ostium to target that prefers the vessel centre, by running Dijkstra/MCP with cost `1 / (EDT + ε)`. This is the standard cheap centreline trick and it keeps the path off the wall.
4. **Detect the first fork** and truncate there: walk the geodesic distance field outward in ~1 mm shells, and at each shell count connected components of `{branch voxels at this geodesic distance}`. When the count goes from 1 to 2 and both parts persist for ≥2 mm, that's the bifurcation. Truncate the path just before it.

That last step directly implements two brief requirements at once: *"trace the proximal branch for up to 10 mm beyond the ostium or until the first downstream bifurcation, whichever occurs first"* and *"a common trunk has one direct aortic origin, even if it divides shortly afterwards."* Say so in your demo — showing you implemented a stated requirement deliberately reads very differently from hoping it worked out.

### Stage 9 — Seed, direction, radius

**Ostium centre.** Centroid of the contact patch, in physical mm, via `TransformContinuousIndexToPhysicalPoint`. Optionally nudge it onto the mid-wall surface (halfway between the eroded and dilated mask boundaries) — the reference is "the centre of the opening," which is a surface, so mid-wall is the least biased choice. A systematic 1 mm bias here is 1 mm off your 25% category on every branch; worth 20 minutes of care.

**Seed.** Point on the proximal path at 5 mm arc length from the ostium, arc length measured in mm. If the path is shorter than 5 mm the branch shouldn't have passed eligibility. Then **snap the seed to the lumen centre**: within the axial-perpendicular plane at that point, move to the local maximum of the EDT. The brief scores "whether the seed lies on the matched daughter," so centring it buys margin against everyone's respective errors.

**Direction.** Unit vector from the ostium into the branch. Don't use just two points — fit a line (PCA) to the path samples from 1 mm to ~7 mm, and orient it away from the ostium. Robust to a single bad voxel. Compute this from physical-mm points only.

**Radius.** Two methods; implement the first, upgrade to the second if time allows:

1. *EDT method:* radius = EDT value at the seed, in mm. One line. Biased by your threshold (a tight threshold shrinks the apparent lumen) but consistent.
2. *Half-max area method:* extract the plane through the seed perpendicular to the direction (`sitk.Resample` with a rotated direction matrix, or trilinear sampling on a sampled grid). Set `T_half = (A_local_lumen + A_background) / 2` using local values. Take the connected region above `T_half` containing the seed, measure its area `A`, report `r = sqrt(A / π)`. This is the standard vessel-sizing approach in clinical software and is notably less threshold-dependent.

Report both in your JSON during development (`radius_mm` plus `radius_mm_edt`) so you can compare against the dev references and pick the better one. Ship only the required field.

### Stage 10 — Eligibility gate and de-duplication

Final gate, every threshold from config:

| Test | Default | Rationale |
|---|---|---|
| Geodesic extent beyond wall | ≥ 5.0 mm | Stated in brief |
| Radius at seed | ≥ `min_radius_mm` (**start 0.8, tune**) | The unknown size rule — your biggest lever |
| Contact patch area | ≥ ~3 mm², ≤ ~120 mm² | Too small = noise; too large = end cap or leak |
| Mean HU vs aortic median | within ~30% | Rejects veins and organs |
| Path straightness | tortuosity < ~2.0 over 10 mm | Rejects paths that snake through leaked tissue |
| Not on forbidden surface | — | Stage 5 |
| Not a duplicate | ostia > 3 mm apart **or** directions > 30° apart | Duplicates are false positives |

Then write JSON. And wrap **every case** in a try/except that, on any failure, still writes a valid file with an empty `daughters` list and a `"warnings"` field. A crash on one hidden case can cost you far more than that case's score, because "successful execution on unseen cases" is the reproducibility criterion.

### What to build if you're behind schedule

Stages 1, 2, 3 (threshold only), 4 (slice centroids), 5 (end caps), 6, 7 (patch components, no merge logic), 9 (EDT radius, two-point direction), 10 (basic gate). That's a complete, respectable submission and it is genuinely achievable in one long day. Everything else is upside.

---

## 5. Repository layout and module contracts

The point of writing contracts down *before* coding is that four people (and four LLM sessions) can then work simultaneously without merge hell. Agree on these in the first 30 minutes and treat them as frozen.

```
branchseed/
├── run.py                  # the required CLI, thin wrapper only
├── requirements.txt
├── README.md
├── config/
│   └── default.yaml        # EVERY threshold lives here
├── src/
│   ├── io_geom.py          # S1: load, validate, crop, resample, index<->mm
│   ├── intensity.py        # S2: aortic lumen profile, adaptive thresholds
│   ├── candidates.py       # S3: bright mask, bone suppression, vesselness
│   ├── aorta_frame.py      # S4/S5: centreline, wall, normals, clock, forbidden
│   ├── instances.py        # S6/S7: components, contact patches, split/merge
│   ├── geometry.py         # S8/S9: path, fork stop, seed, direction, radius
│   ├── gate.py             # S10: eligibility + dedup
│   └── report.py           # JSON writer + the clinician view
├── eval/
│   ├── score.py            # the scoring harness
│   ├── phantom.py          # synthetic ground-truth generator
│   └── batch.py            # run all cases, emit a results table
└── tests/
```

**Frozen interfaces.** These are the only things that cross module boundaries:

```python
# io_geom.py
@dataclass
class Case:
    ct: sitk.Image              # cropped, 1mm isotropic, HU
    aorta: sitk.Image           # same grid, uint8
    ct_np: np.ndarray           # [z,y,x] float32 view
    aorta_np: np.ndarray        # [z,y,x] bool
    case_id: str
def load_case(image_path, mask_path, cfg) -> Case
def idx_to_mm(case, zyx) -> np.ndarray      # accepts float, returns (3,) in mm
def mm_to_idx(case, xyz_mm) -> np.ndarray   # returns float [z,y,x]

# intensity.py
@dataclass
class Profile:
    a_med: float; a_p10: float; a_iqr: float
    t_vessel: float; t_bone: float; t_high: float
def profile_aorta(case, cfg) -> Profile

# candidates.py
def candidate_mask(case, profile, cfg) -> np.ndarray   # bool [z,y,x]

# aorta_frame.py
@dataclass
class AortaFrame:
    centreline_mm: np.ndarray     # (N,3) superior -> inferior
    wall_np: np.ndarray           # bool, all wall voxels
    legal_wall_np: np.ndarray     # bool, wall minus forbidden
    excluded: list[dict]          # end caps / bifurcation, with reasons
def build_frame(case, cfg) -> AortaFrame
def outward_normal(frame, zyx) -> np.ndarray
def clock_and_arclen(frame, xyz_mm) -> tuple[float, float]  # hours, mm

# instances.py
@dataclass
class RawBranch:
    patch_zyx: np.ndarray         # (M,3) contact patch voxels
    voxels_zyx: np.ndarray        # (K,3) assigned branch voxels
    geodesic_extent_mm: float
    mean_hu: float
def find_raw_branches(case, cand, frame, profile, cfg) -> list[RawBranch]

# geometry.py
@dataclass
class BranchGeom:
    ostium_mm: np.ndarray; seed_mm: np.ndarray
    direction: np.ndarray; radius_mm: float
    path_mm: np.ndarray           # (P,3) for the visualisation
    truncated_by: str             # "length" | "bifurcation"
def measure(case, raw: RawBranch, frame, profile, cfg) -> BranchGeom
```

Rules that prevent 90% of integration pain:

- **All coordinates crossing a module boundary are physical mm.** Voxel indices stay inside the module that owns them.
- **Numpy arrays are always `[z, y, x]`.** SimpleITK tuples are always `(x, y, z)`. Conversions happen only inside `io_geom.py`.
- **No module reads a constant that isn't in `cfg`.** No exceptions, including "temporary" ones.
- **Every function is pure** (no global state, no writing files) except `run.py` and `report.py`. This is what makes them unit-testable and what makes an LLM able to write one correctly in isolation.

---

## 6. Dividing four people

The natural instinct is to split the pipeline into four and assign one part each. Don't — Stage 7 depends on Stage 4 depends on Stage 1, so three people would spend the first six hours blocked. Split by **axis of risk** instead:

**Person A — Foundations & correctness** (`io_geom`, `run.py`, packaging, `tests/`)
Owns the coordinate system, which means A owns 25% of the score. Builds the CLI and a stub pipeline that emits valid empty JSON *in hour one*, so everyone else always has something runnable. Owns `requirements.txt`, the README, the one-command setup, and the final "clean clone into a fresh venv and run it" rehearsal. Owns the phantom tests jointly with D.

**Person B — Signal & candidates** (`intensity`, `candidates`)
Owns "can we see the branches at all." Spends the first hours *looking at the data*: opens cases in a viewer, measures HU inside aortas and inside branches, finds out how bad the bone problem is, whether veins bridge, whether kidneys flood. B's deliverable is a candidate mask with **high recall** — a mask that contains every real branch, even at the cost of junk. Junk is C's problem. Under-inclusion is unrecoverable.

**Person C — Instancing & geometry** (`aorta_frame`, `instances`, `geometry`, `gate`)
Owns the 45% and the 15%. The hardest and most interesting work: end-cap suppression, patch splitting, the geodesic race, path tracing, radius estimation. C should not be distracted with anything else once the pipeline runs.

**Person D — Measurement, visualisation & delivery** (`eval/`, `report`, demo)
Owns the feedback loop, which is the highest-leverage seat on the team for the first six hours. Builds the scoring harness, the batch runner, and the results table. Then builds the clinician view (Section 10) and owns the README, the visual checks, and the five-minute demo. D also runs the profiler and owns the 10% compute score.

Sequencing so nobody blocks:

- **Hours 0–2:** A builds the stub CLI + loader. D builds the phantom generator and the scorer against a *hardcoded fake prediction* — you don't need a real pipeline to test a scorer. B opens the data and starts measuring. C writes `aorta_frame` against synthetic input from D's phantom.
- **Hours 2–8:** B and C work against the phantom and 2–3 real cases. A wires the stages together as they land. D's batch table becomes the team's shared scoreboard.
- **Mid-event:** everyone converges on tuning against the scoreboard. C leads; B feeds thresholds; D reports.
- **Last quarter:** feature freeze. A does the fresh-clone rehearsal. D does the demo. B and C only tune config values, no code.

**Non-negotiables:** short-lived branches, PRs merged within the hour, and `main` always runs. One person (A) is the integrator with a veto on merges. If you skip this you will spend the final three hours debugging a merge instead of tuning, which is the classic way to lose a hackathon you were winning.

---

## 7. The hour-by-hour plan

Scaled for roughly 48 hours; compress proportionally if you have 24. **Each phase ends at a gate.** If you fail a gate, cut scope rather than sliding the schedule — and note that the gates are ordered so that failing a late gate still leaves you with a submittable project.

### Phase 0 — Hours 0–1: agree and split
- Read the brief aloud together, once. Write down every requirement as a checklist item (there are ~20). This checklist is your definition of done.
- Freeze the interfaces in Section 5 and the config file keys.
- Create the repo with the full directory skeleton, empty modules with signatures and docstrings, `requirements.txt`, and a `CLAUDE.md` (Section 9).
- **Gate:** everyone can clone, install, and run `python run.py --image ... --aorta-mask ... --output out.json` and get a valid file with `"daughters": []`.

### Phase 1 — Hours 1–4: see the data, measure the data
- B: open 5 cases in a viewer. Find the aorta, find the celiac and SMA, find a lumbar artery. Screenshot each and share — **the whole team should be able to recognise a branch by sight before writing detection logic.** 3D Slicer is free, handles NIfTI, and has a built-in HU probe.
- B: tabulate per case: aortic lumen median HU, branch lumen HU, bone HU, how many branches you can count by eye. That last column is provisional ground truth for cases with no reference.
- D: phantom generator (Section 8.2) + scorer (Section 8.1).
- A: loader, crop, resample, index↔mm helpers, with tests.
- **Gate:** `eval/score.py` produces P/R/F1/distance numbers on a fake prediction vs. the phantom, and everyone knows what a branch looks like.

### Phase 2 — Hours 4–12: first end-to-end detections
- All stages implemented at their simplest: threshold, components, patches, EDT radius, two-point direction. No vesselness, no merge logic, no fork detection.
- End-cap suppression **must** be in this phase — without it your numbers are meaningless noise.
- **Gate:** you produce non-zero, non-absurd detections on all dev cases, and the scoreboard shows a real F1. Even 0.35 is fine. You now have a number to improve, which changes everything about how the rest of the event feels.

### Phase 3 — Hours 12–24: make the number go up
This is the core of the event. Work strictly in this order, re-scoring after each change:

1. **Recall first.** Are you missing branches because they're not in B's candidate mask, or because C's gate is rejecting them? Instrument this: log every rejected candidate with the reason. Usually 70% of misses are one reason, and fixing it is a single line.
2. **Then the size gate sweep.** Run `min_radius_mm` from 0.5 to 2.0 in steps and plot F1. Find the plateau, sit in the middle of it. This tells you how sensitive you are to the organisers' unannounced cutoff.
3. **Then precision.** Look at your false positives *visually*, one by one. They will cluster into 3–4 causes (bone, end cap you missed, vein bridge, kidney leak). Fix by cause, not by tightening a global threshold — a global tighten trades 3 FPs for 5 FNs and nets you nothing.
4. **Then splitting/merging.** Fork detection, geodesic race, duplicate merge.
5. **Then ostium and radius accuracy** — the 25% and part of the 15%. Mid-wall nudging, sub-voxel centroids, half-max radius.
- **Gate:** F1 above ~0.7 on dev cases, mean ostium error under ~3 mm, no crashes on any of the 25 cases.

### Phase 4 — Hours 24–34: the clinician view and robustness
- D builds the unrolled aortic map (Section 10) and per-case HTML reports.
- A: profile runtime and memory; cut the worst offender; confirm you're inside 60 s and 8 GB with margin. Test in a fresh venv with no network.
- B/C: robustness pass. Run on the weirdest cases (shortest coverage, most calcification). Add the try/except safety net. Make sure a case with 0 eligible branches produces a clean empty list rather than an error.
- **Gate:** all 25 cases run in one batch command, under budget, with HTML reports generated.

### Phase 5 — Hours 34–44: tune, don't build
- **Feature freeze.** From here, only config values and bug fixes.
- Leave-one-out discipline: if you have N reference cases, tune on N−1 and check the held-out one. With very few cases, prefer parameters that are *flat* (a plateau) over parameters that are *optimal* (a spike). A spike is overfitting and will not survive the hidden test set.
- Write the README: one setup command, one run command, a method summary, a documented config table, and a **known failure cases** section. Judges reward this honesty disproportionately.
- Generate the required visual checks for ≥3 cases and the dev-set predictions.

### Phase 6 — Hours 44–48: rehearse
- Fresh clone, fresh virtual environment, no network, run the exact CLI from the brief. Fix whatever breaks (there will be something — there always is).
- Record/rehearse the five-minute demo (Section 11.2). Time it. Five minutes means five.
- Final checklist pass against the ~20 requirements you wrote down in Phase 0.

---

## 8. Your two most important tools

### 8.1 The scoring harness (`eval/score.py`)

Build this before your detector. It should take a prediction JSON and a reference JSON and output:

```
case         n_ref  n_pred  TP  FP  FN  precision  recall    F1  ost_mm(mean/max)  ang°  dr_mm
subject001      11      10   9   1   2      0.90    0.82  0.86        2.1 / 4.8    12.4   0.31
```

Implementation notes:

- **Matching must be one-to-one.** Use `scipy.optimize.linear_sum_assignment` on the pairwise ostium-distance matrix, then reject matches exceeding a threshold. Greedy nearest-neighbour matching gives optimistic, misleading numbers when two branches are close — exactly the situation you're trying to get right.
- The graders' matching threshold is unknown. Report at 3, 5, and 10 mm. If your F1 collapses between 10 mm and 5 mm, your localisation is your bottleneck, not your detection.
- Also compute: angle between predicted and reference direction; `|r_pred − r_ref|`; and whether the seed lies within the reference branch's radius of the reference proximal centreline (that's the "seed lies on the matched daughter" test).
- Aggregate two ways: **micro** (pool all branches) and **macro** (average per-case F1). Report both; they diverge when one case dominates, and knowing which is which prevents you from chasing a phantom improvement.

### 8.2 The synthetic phantom (`eval/phantom.py`)

This is the idea that most levels the playing field for a team without anatomy knowledge, and almost nobody does it.

Generate a NIfTI volume containing:
- a vertical cylinder of radius 10 mm at 350 HU (the "aorta"), plus its exact binary mask;
- N cylinders of known radius branching off at known positions, known directions, known lengths, at 320 HU;
- background at 40 HU, with Gaussian noise and a light blur to mimic partial volume;
- optionally: a bright slab behind it (the "spine" at 700 HU), a small 900 HU blob on the wall (a "calcification"), a dimmer parallel cylinder (a "vein" at 120 HU), and a branch that forks 7 mm out (a "common trunk").

Because you generated it, you know the exact reference JSON. Now you can test things you can never test on real data:

- Is my ostium within 1 mm of the true one? (**validates the 25% category**)
- Is my radius within 0.3 mm of the true radius? Is it biased high or low?
- Is my direction within 5°?
- Does my fork detection stop at 7 mm on the trunk case?
- **Does my coordinate handling survive anisotropic spacing and non-identity direction cosines?** Generate the same phantom at 0.7×0.7×2.0 mm spacing and with a rotated direction matrix. If your output points move, you have a bug that is silently costing you on every real case. This test alone is worth building the phantom for.
- Does a short phantom (cropped so only 2 branches exist) yield exactly 2, with no end-cap false positives?

A phantom takes about an hour to write and gives you an infinite, perfectly-labelled dataset for every geometric component of the score. It also gives you a regression test suite, so you can refactor at hour 30 without fear.

### 8.3 Getting more ground truth

Reference outputs come with only a small dev subset. Two ways to expand your signal:

1. **Count-only labels.** Each teammate independently counts visible branches on each of the 25 cases in a viewer. It's slow for full annotation but fast for counting. Comparing your predicted count to a human count catches systematic recall failures across the whole set, even without positions.
2. **Click ostia in 3D Slicer.** Place fiducial points at branch openings, export to JSON/FCSV, convert to your reference format. Two people doing 5 cases each gets you 10 more labelled cases in an hour or two. **Remember the RAS→LPS flip**: negate x and y when importing Slicer coordinates into SimpleITK space. Validate the flip by clicking a point you can identify unambiguously and checking your converted coordinate lands on the same voxel.

Even rough extra labels beat tuning against three cases, because tuning against three cases is how you build something that scores 0.85 on dev and 0.45 on the hidden set.

---

## 9. Getting real work out of the LLMs

You have four chat subscriptions and $25 of Claude Code credit. These are different tools and should be used for different things.

### 9.1 The division

| Tool | Best for | Avoid |
|---|---|---|
| Chat (Claude Pro, Gemini Pro) | Algorithm brainstorming, "explain what a Frangi filter does," writing one self-contained function, reviewing a diff you paste in, debugging a stack trace | Multi-file refactors, anything needing to see your actual data |
| Claude Code ($25) | Tasks where reading/running the repo is the point: wiring modules, writing the test suite, refactors, and above all **running your pipeline on real cases and iterating on the output** | Open-ended discussion, long conversations you could have had in chat for free |

The reason to reserve the credits for Claude Code is that it can execute your code and inspect results. That closes the loop. A chat model guessing why your detector missed the left renal artery is much less useful than an agent that can run the case, print the rejection log, and check.

### 9.2 Set up `CLAUDE.md` in hour one

Claude Code reads a `CLAUDE.md` from your project root at the start of every session. Put the non-obvious, project-specific rules there — the conventions that differ from what any tool would default to. Keep it short and specific; a bloated one gets followed less consistently. Something like:

```markdown
# Branchseed Challenge

## Task
Detect arteries branching directly off a given abdominal aorta mask in CTA volumes.
Output: JSON with ostium_xyz_mm, seed_xyz_mm, radius_mm, direction_xyz per branch.
Full spec: see docs/brief.md. Scoring: 45% detection F1, 25% ostium distance,
15% geometry quality, 10% runtime, 5% reproducibility.

## Hard rules
- Numpy arrays are ALWAYS [z,y,x]. SimpleITK tuples are ALWAYS (x,y,z).
  Conversions live only in src/io_geom.py. Never reverse a tuple inline.
- All coordinates crossing a module boundary are physical mm, obtained via
  TransformContinuousIndexToPhysicalPoint. Never voxel indices.
- Never compute a distance or direction in voxel units. Convert to mm first.
- No numeric constants in src/. Everything from config/default.yaml.
- No per-voxel Python loops. Use scipy.ndimage / skimage vectorised ops.
- Target: <60s per case, <8GB RAM, 4 CPU cores, no GPU, NO INTERNET at runtime.
  Do not add a dependency that downloads weights or data.
- Every public function needs a docstring stating units of every argument.

## Commands
Install: pip install -r requirements.txt
Run one: python run.py --image X.nii --aorta-mask Y.nii --output out.json
Run all: python eval/batch.py --data data/ --out results/
Score:   python eval/score.py --pred results/ --ref data/reference/
Test:    pytest tests/ -q
```

Use plan mode for anything touching more than one file — review the plan before it writes code. Start a fresh session per task rather than letting one conversation sprawl; long contexts cost more and drift more.

### 9.3 How to prompt for code that actually works

The difference between a useful and useless LLM session on this project is almost entirely about how much context you provide. Four habits:

**Give the contract, not the vibe.** Compare:

> ❌ "Write code to find branches coming off the aorta in a CT scan."

> ✅ "Implement `find_raw_branches(case, cand, frame, profile, cfg) -> list[RawBranch]` per the signatures below. `cand` is a bool numpy array `[z,y,x]` of candidate vessel voxels at 1 mm isotropic. `frame.legal_wall_np` is a bool array of aortic wall voxels that are allowed to host an ostium. Steps: (1) remove voxels in the aorta dilated by one voxel; (2) 26-connected components; (3) for each component, find adjacent legal wall voxels = contact patch; (4) label connected components of the contact patches over the wall; (5) for components with multiple patches, assign each voxel to the nearest patch by geodesic distance inside the component using `skimage.graph.MCP_Geometric`; (6) return one RawBranch per patch with its geodesic extent in mm and mean HU. Use only numpy, scipy.ndimage, skimage. No Python loops over voxels. Every threshold from `cfg`."

The second one gets working code on the first try. It took two minutes to write and saves an hour.

**Paste the relevant brief text.** When asking about anything spec-driven (end caps, common trunks, output format), paste that exact paragraph. Models will otherwise invent plausible-but-wrong requirements, and you'll build to them.

**Demand tests alongside.** "Also write a pytest that builds a 60×60×60 synthetic array with a 10 mm cylinder and two known branches, and asserts the function returns exactly 2 with extents within 1 mm." This catches the 20% of generated code that looks right and isn't.

**Ask for the failure mode.** End prompts with: "Then list the three ways this function will produce wrong results on real data, and what I should check." Models are good at this and it points your debugging directly at the real problems.

**One more, specific to medical imaging:** always say which library. Models fluidly mix `nibabel`, `SimpleITK`, `itk`, and `pydicom` conventions, which have *different* axis orders and coordinate conventions. Mixed-convention code is the number one source of silent coordinate bugs. Pin it: "SimpleITK only for I/O and geometry; numpy/scipy/skimage for array work."

### 9.4 Spending the $25 well

Rough allocation:

- **~20%** — Phase 0/1: repo scaffold, the loader with tests, the phantom generator. High value: these are well-specified, and agentic file creation is faster than copy-pasting from chat.
- **~15%** — the scoring harness and batch runner. Well-specified, tedious, easy to get right, boring to write by hand.
- **~40%** — Phase 3 debugging loops. This is the highest-value use: "run subject004, print every rejected candidate with its rejection reason and its distance to the nearest reference ostium, and tell me what the dominant failure mode is." Nothing else you own can do that.
- **~15%** — the HTML report / visualisation. Lots of fiddly plotting code.
- **~10%** — reserve. Something will break at hour 44.

Use the free chat subscriptions for everything conversational, for asking the same algorithm question three different ways, and for reviewing diffs. Don't burn agent credits on discussion.

### 9.5 Where LLMs will confidently mislead you on this project

Worth knowing in advance, because each of these has cost teams hours:

- **Axis order.** Generated code will mix up `[z,y,x]` and `(x,y,z)`. Assume it's wrong until your phantom test passes.
- **Hard-coded HU thresholds.** Models love `blood > 200`. Your case-adaptive profile (Stage 2) is better; insist on it.
- **Suggesting a pretrained model.** TotalSegmentator, nnU-Net, and friends will come up. They need downloads, often a GPU, and would blow your runtime budget on a CPU-only offline box. They're also solving a different problem (naming known structures) than yours (discovering unnamed ones). Politely decline.
- **`skeletonize_3d` on the whole candidate mask.** Sounds right, produces a spur-covered mess that takes longer to clean up than to avoid. Geodesic paths from known seeds are better here.
- **Forgetting the end caps.** No model will spontaneously remember that the cropped aortic ends aren't branches. You have to tell it.

---

## 10. The clinician view (your differentiator)

The brief asks for two separate things and most teams will conflate them:

1. *"a simple visual check for at least three cases showing the aorta mask, detected ostia and daughter-direction arrows"* — a verification tool, explicitly not required to be fancy.
2. *"display information in a unique way that will be useful for clinicians"* — listed under **minimum working prototype**, i.e. it's a requirement, and it's the one where taste shows.

Build both. The first is 45 minutes. The second is where you win the room.

### 10.1 The verification view (required, keep it cheap)

Per case, a single PNG with three panels:
- **Coronal maximum-intensity projection** (`ct_np.max(axis=1)`) with the aorta mask outline overlaid, detected ostia as dots, and direction arrows projected into the plane. MIPs make vessels look like vessels, which makes errors instantly obvious.
- **Sagittal MIP**, same overlay. Anterior branches (celiac, SMA, IMA) are unmistakable here.
- **A strip of axial slices**, one per detected ostium, each cropped to ±40 mm around the aorta, with a marker on the ostium and an arrow for the direction. This is the panel a judge will actually scrutinise, because it's the one where they can independently verify you're right.

matplotlib, no interactivity needed.

### 10.2 The unrolled aortic map (the differentiator)

Here's the domain insight that makes this land. When surgeons plan a **fenestrated stent graft** — a fabric tube placed inside a diseased aorta, which must have holes cut in it precisely where the branches leave — the numbers they need for each branch are:

1. **Distance** along the aorta from a fixed landmark, and
2. **Clock position** around the circumference (12 o'clock = anterior), and
3. **Diameter** of the branch, and
4. **Takeoff angle** relative to the aortic axis.

That's *exactly* the four quantities your pipeline computes. And the standard way to present them is a **cylindrical unrolling**: cut the aorta lengthwise and flatten it into a rectangle.

So: plot a 2D chart.
- **X axis:** arc length along the aortic centreline, in mm, from the superior end of the supplied coverage.
- **Y axis:** clock position, 12 → 3 → 6 → 9 → 12.
- **Each branch:** a circle at its (distance, clock) position, with **radius scaled to the true vessel radius**, annotated `branch_003 · r=2.6 mm · 14.2 mm · 3 o'clock · 78°`.
- Shade horizontal bands for anterior / lateral / posterior to make the pattern readable at a glance.

On a normal case this produces an immediately legible signature: two dots near 12 o'clock at the top (celiac, SMA), a pair facing each other at 3 and 9 (the renals), a small one near 1–2 o'clock lower down (IMA), and a regular ladder of small dots around 5 and 7 o'clock (the lumbars). **A clinician can check your entire output in three seconds** — and so can a judge. If your unrolled map shows the renals at 4 and 8 o'clock instead of 3 and 9, you have a bug, visibly.

That last property is why this is worth building even ignoring the rubric: it is simultaneously the best debugging tool you will have and the most impressive thing in your demo. It also directly answers "unique way that will be useful for clinicians" with something real rather than decorative, and it gives you a confident answer to the inevitable judge question *"who would use this and how?"*

### 10.3 Wrap it in one self-contained HTML file per case

One `report_subject001.html` with no external dependencies (inline the images as base64, inline the CSS):

- header: case ID, runtime, number of branches, derived HU thresholds;
- the unrolled map;
- a sortable table: instance ID, distance from top of coverage, clock position, radius, takeoff angle, path length, whether truncated by length or by a fork, confidence;
- the axial verification strip;
- an interactive 3D view (plotly, `include_plotlyjs='inline'`): the aorta as a mesh (`skimage.measure.marching_cubes` on the mask), ostia as markers, directions as cones;
- the excluded candidates with their reasons — showing what you *deliberately* rejected is a strong signal of engineering maturity.

A single file, openable by double-clicking, no server, no install. Judges can poke at it themselves, which is worth more than any slide.

---

## 11. Delivery

### 11.1 Submission checklist

Straight from the brief — verify each one physically, don't assume:

- [ ] Source code in the repo, `main` branch runs
- [ ] `requirements.txt` (or `environment.yml`) with **pinned versions**
- [ ] README with exactly **one** setup command and **one** run command
- [ ] The CLI works verbatim: `python run.py --image image.nii.gz --aorta-mask aorta_mask.nii.gz --output prediction.json`
- [ ] Accepts both `.nii` and `.nii.gz` (the data is `.nii`, the brief's example is `.nii.gz` — support both)
- [ ] No manual point placement anywhere; fully automatic
- [ ] Predictions for the whole development set, committed
- [ ] Visual checks for ≥3 cases, committed as files
- [ ] Variable number of detections (demonstrate a case with many and a case with few)
- [ ] Empty `daughters` list handled correctly and tested
- [ ] `parent_instance_id == "aorta"` on every daughter; all instance IDs unique
- [ ] Physical coordinate system preserved and verified
- [ ] Runs on all 25 cases with no case-specific code paths and no crashes
- [ ] Verified with **no network access** and no GPU, in a **fresh clone and fresh venv**
- [ ] Average runtime and peak memory measured and stated in the README
- [ ] Five-minute demo covering method, runtime, and known failure cases
- [ ] Known-failure section in the README

The "fresh clone, fresh venv, no network" rehearsal is not optional and must not happen in the final hour. Do it at hour 34 and again at hour 46.

### 11.2 The five-minute demo

Judges see many demos. Structure beats polish. Suggested budget:

- **0:00–0:30 — The problem, in their words.** "Given the aorta, find every artery leaving it, without knowing in advance which or how many." One sentence on why it matters (stent graft planning needs the position of every branch, and the anatomy varies per patient).
- **0:30–1:45 — Method, one slide, the pipeline diagram.** Emphasise the two ideas that are actually yours: *aorta-relative adaptive thresholding* (works across contrast timing) and *instance-per-contact-patch with a geodesic race* (separates branches that touch). Name the edge cases you handled deliberately: cropped end caps, common trunks, iliac bifurcation.
- **1:45–3:00 — Results, with numbers.** Precision/recall/F1, mean ostium error in mm, mean direction error in degrees, radius error. Show the score-vs-size-threshold curve — it demonstrates you understood that the cutoff is a parameter, not a guess. State runtime and peak memory.
- **3:00–4:00 — The clinician view.** Live, in a browser. Let the unrolled map speak. Point out how you'd verify a case in three seconds.
- **4:00–4:40 — Known failure cases.** Be specific and unembarrassed: "we miss lumbar arteries under 0.8 mm radius"; "heavy wall calcification produces a false positive about once every three cases"; "one case has a stent whose metal artefact breaks our threshold." Then say what you'd do next. **This section wins trust.** Teams that claim everything works are assumed to have not looked.
- **4:40–5:00 — Close.** One sentence: what it does, how fast, what it would need to be usable.

Rehearse with a timer. Whoever speaks least in normal conversation should get a defined section — judges notice a team where one person does everything.

---

## 12. Risk register

The failures that actually sink teams on a task like this, and the cheapest mitigation for each.

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Coordinate convention bug (axis order, RAS/LPS, spacing) | Catastrophic — all 25% of localisation, silently | Phantom test with anisotropic spacing and rotated direction cosines, in Phase 1 | A |
| Cropped end caps reported as branches | ~25 false positives, wrecks precision | Stage 5, implemented in Phase 2 not Phase 4 | C |
| Recall collapse from too-tight size gate | Half of the 45% | Sweep the threshold; sit on a plateau; log every rejection with its reason | C |
| Only finding the 4 famous branches | Same as above | Know that 10–20 is plausible; count by eye on real cases early | B |
| Bone/spine contamination | False positives posteriorly, where lumbars live | Bone threshold + component size rule + optional vesselness | B |
| Threshold leak into kidney/liver | Giant merged components, missed renals | Hysteresis threshold; per-component volume sanity check with re-thresholding | B |
| Overfitting to 2–3 dev cases | Dev F1 0.85, hidden F1 0.45 | Expand labels by clicking fiducials; prefer flat parameters; leave-one-out | D |
| A crash on a hidden case | Loses that case *and* the reproducibility marks | try/except per case, always emit valid JSON | A |
| Dependency needs internet or a GPU | Total failure on the eval box | Pin everything; rehearse offline in a fresh venv | A |
| Runtime blowup on a large volume | Loses the 10% | Crop to aorta bbox + 50 mm first; resample to 1 mm; profile at hour 24 | A |
| Merge conflict chaos in the last hours | Loses tuning time | Small PRs, one integrator, feature freeze at hour 34 | A |
| Two people build the same thing | Loses a person-day | Frozen interfaces in hour one; a shared task board | all |
| Nobody owns the demo | Great project, forgettable presentation | D owns it from hour 0 and rehearses twice | D |

### Runtime budget (target, 1 mm isotropic, cropped ROI)

| Stage | Budget |
|---|---|
| Load + crop + resample | 3 s |
| Aortic profile | < 1 s |
| Candidate mask + bone suppression | 3 s |
| Vesselness (optional, 3 scales) | 8 s |
| Centreline + wall + forbidden surface | 2 s |
| Components + contact patches | 3 s |
| Geodesic race + per-branch paths (×15) | 8 s |
| Seed/direction/radius (×15) | 2 s |
| JSON + report | 2 s |
| **Total** | **~32 s** |

That leaves comfortable margin under 60 s. Peak memory at 1 mm on a cropped ROI should sit well under 2 GB in float32. If you exceed either, the first thing to cut is vesselness, and the second is to relax to 1.2 mm isotropic.

---

## 13. Stretch goals, in value order

Only after Phase 3's gate is met. Each is genuinely worth points or judge attention:

1. **A confidence score per branch** (combining vesselness, HU similarity to the aorta, geodesic extent, and patch quality). Include it in your JSON as an extra field. It costs nothing, it's honest, and it's exactly what a clinical tool would need for triage. It also lets you show a precision/recall trade-off curve instead of a single operating point — which is a far more sophisticated result to present.
2. **The iliac extension.** The brief says it "may be evaluated separately." You'll already have detected and labelled them in `excluded_candidates`; promoting them into a separate `optional_iliacs` list is nearly free.
3. **Multi-scale recovery pass.** Re-run detection at 0.6 mm isotropic *only* in a shell around the aorta, specifically hunting sub-millimetre branches that the 1 mm pass missed. Costs runtime; may buy real recall on lumbars. Measure before keeping.
4. **A tiny learned gate.** With ~100 labelled candidates (accept/reject) from your dev references, train a 20-tree random forest on features you already compute (radius, extent, mean HU ratio, vesselness, patch area, clock angle, takeoff angle). Pickle it into the repo — no internet needed, milliseconds to run. This is the legitimate "lightweight machine learning" the brief invites, and it typically beats hand-tuned thresholds on precision. Only do this if you have enough labels; with 30 examples it will overfit and hurt you.
5. **Left/right and organ-territory hints without naming.** You're forbidden from assigning anatomical names — but reporting clock position and takeoff angle conveys the same practical information without claiming an identification. Say this explicitly in the demo; it shows you read the constraint carefully rather than ignoring it.

---

## 14. If you only do five things

1. **Build the scorer and the synthetic phantom before the detector.** Everything downstream gets faster and safer.
2. **Handle the cropped aortic end caps on day one.** It's the single highest-frequency false positive in the whole task, and it's spelled out in the brief.
3. **Make every threshold case-adaptive against the aortic lumen, and every constant a config value.** Contrast timing varies; the size cutoff isn't announced yet.
4. **Assume 10–20 branches, not 5.** Log every rejected candidate with its reason, and go hunting for recall before you go hunting for precision.
5. **Build the unrolled aortic map.** Best debugging tool you'll have, and the thing judges will remember.

Good luck. The task is narrower than it looks, and the winning version of it is a careful 800-line classical pipeline with an excellent test harness — not a clever model.
