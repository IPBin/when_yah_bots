# Branchseed Challenge — Team Playbook

**One document. 3 people. 16:00 Saturday → submit 10:45 Sunday.**

This supersedes every earlier draft. It is the only file you should be working from, and the only one you should upload as LLM context.

---

## 0. How to use this document

- **§1–§2** are for the three of you in the first forty minutes: what the scoring rewards, who owns what, and the clock.
- **§3–§4** are the domain knowledge you need. You don't need to learn anatomy, only enough to stop being surprised by the images.
- **§5–§8** are the technical spec: the pipeline, the module contracts, the config, the test tooling, the visualisation.
- **§9** is how to get working code out of the LLMs, including a prompt pack you can paste in clock order.
- **§10–§12** are risks, the submission checklist, and a one-page wall sheet.

**If you are an LLM reading this as context:** §6 (module contracts), §7 (config), and §5 (pipeline stages) are normative. §5.11 lists techniques that are deliberately **out of scope for this build** — do not implement them, do not suggest them. All coordinate conventions in §3.5 are hard rules.

---

## 1. What actually wins this

Three facts about the rubric, and one hidden ask.

**1. 45% of the score is "did you find the right number of branches."** Not accuracy, not elegance. Detection count, as precision/recall/F1 over branch instances. A pipeline that reliably finds 9 of 11 real branches with 1 false positive beats a beautiful pipeline that nails the 4 famous ones. Almost everything below serves that number.

**2. 15% is free if you don't crash.** Compute efficiency (10%) and reproducibility (5%) go to whoever writes a boring, `scipy`-only program that never throws and has a one-line setup command. Teams routinely lose all 15 to a dependency that needed internet or a case that crashed.

**3. You cannot tune what you cannot measure.** You get reference answers for a small dev subset only. Your first deliverables are a **scoring harness** and a **synthetic phantom** (§7). Build them before the detector. Teams that do this spend the night improving a number; teams that skip it spend the night arguing about whether the output looks right.

**4. The hidden ask:** *"display information in a unique way that will be useful for clinicians"* sits under **minimum working prototype**, so it's a requirement, not a bonus. Most teams will render a 3D blob with arrows. §8.2 shows you what surgeons actually look at. It's the cheapest differentiator on the board and it doubles as your best debugging tool.

### The rubric, decoded

| Category | Weight | What it really means |
|---|---|---|
| Branch discovery | 45% | P/R/F1 on instances. Missing small branches and emitting duplicates are the two ways to lose here. |
| Ostium localisation | 25% | Millimetre distance to their ostium. Dominated by coordinate-convention correctness and by whether your point sits on the aortic wall. |
| Daughter-instance quality | 15% | Seed inside the right branch, direction follows it, radius plausible. Pure geometry — fully testable on synthetic data. |
| Compute efficiency | 10% | Runtime + memory, CPU-only, 4 cores, 8 GB, target < 60 s/case. Crop aggressively and you'll land near 20 s. |
| Reproducibility | 5% | Valid output, documented setup, runs on unseen cases. Free. |

### Two sentences in the brief with outsized consequences

- *"Predictions will be matched to references one-to-one, so duplicate detections count as false positives."* → you need de-duplication, and you need care where one real branch splits into two detections.
- *"its origin meets the minimum size specified with the final dataset"* → **the size cutoff is not yet announced.** It lives in `config/default.yaml` as `min_radius_mm` and nowhere else. It will swing your recall more than any other decision you make. Produce a score-vs-cutoff curve so you can retune in sixty seconds when they publish it.

---

## 2. Roles and the clock

### Roles

| | Owns | Score exposure |
|---|---|---|
| **P1 — Detector** | `aorta_frame`, `instances`, `geometry`, `gate` | 45% + 15% |
| **P2 — Foundations & signal** | `io_geom`, `intensity`, `candidates`, `run.py`, packaging, README, profiling, the fresh-clone rehearsal | 25% + 10% + 5% |
| **P3 — Feedback & delivery** | `phantom`, `score`, `batch`, visual checks, unrolled map, demo | makes the other two able to improve |

P1 has the largest and hardest job. From 22:00 everyone works on P1's problem against the shared scoreboard — the roles only hold through the build phase.

Give P1 and P3 the Claude Code sessions (§9.4). P2's modules are small and well-specified enough for chat.

**You are not hand-writing this pipeline.** Three people with basic CS backgrounds cannot type ~800 lines of correct 3D image processing in 18 hours. One person owns one module, prompts for it with a tight contract from §6, then reviews, tests and integrates. Your bottleneck is specification quality, not typing speed.

### The clock

Times are hard, gates are pass/fail. If you fail a gate, cut from §5.11 — never slide the schedule, because 01:45 and 10:45 don't move.

**16:00–16:40 · Setup (all three, one room)**
- Read the brief aloud once. Write every requirement as a line in `docs/checklist.md`. About twenty. This is your definition of done and your 10:30 final pass.
- Create the repo skeleton from §6: modules with exact signatures, `config/default.yaml` from §7, `CLAUDE.md` from §9.2, `docs/brief.md` with the challenge text pasted in.
- Unzip the data, load one case, print its shape, spacing and direction matrix.
- Say the frozen rules out loud: numpy is `[z,y,x]`, SimpleITK is `(x,y,z)`, conversions live only in `io_geom`, everything crossing a module boundary is physical mm, no constants outside config.
- **Gate:** all three can run the exact CLI and get a valid file with `"daughters": []`.

**16:40–18:30 · Block 1**
- **P2:** `io_geom` — load, validate, crop to bbox + 50 mm, resample to 1 mm isotropic, `idx_to_mm` / `mm_to_idx`, round-trip test.
- **P1:** `aorta_frame` — slice-centroid centreline, wall surface, outward normals, **legal wall with end caps excluded**. Write against a hand-built numpy cylinder until the loader lands ~17:30.
- **P3:** `phantom.py` first (both others need it), then 20 minutes with three real cases in a viewer: find the aorta, find the celiac and SMA, probe HU inside the aorta and inside a branch, count visible branches. Share screenshots.
- **Gate 18:30:** loader works on a real case; phantom writes a volume plus its exact reference JSON; P1 can show a legal-wall mask with the end caps visibly gone.

**18:30–20:30 · Block 2**
- **P2:** `intensity` + `candidates`.
- **P1:** `instances` — components, contact patches, one instance per patch, geodesic extent.
- **P3:** `score.py` and `batch.py`. Test the scorer against a hand-written fake prediction; you don't need a detector to test a scorer.
- **Gate 20:30 (critical):** end-to-end run on the phantom produces sane non-empty JSON. Not there by **21:00** → start cutting.

**20:30–22:00 · Geometry and first real numbers**
- **P1:** `geometry` (path, seed, direction, EDT radius) then `gate`.
- **P2:** full batch over all 25 cases, fix every crash, add the per-case try/except, time it.
- **P3:** score against dev references and the phantom; publish the scoreboard where all three can see it.
- **Gate 22:00:** a real F1 number, whatever it is. Commit predictions. Tag `v1-safe`. **You are now submittable, twelve hours early.**

**22:00–01:00 · Make the number go up (all three)**
Strictly in this order, re-scoring after each change:
1. **Recall.** Log every rejected candidate with its reason. Are misses absent from the candidate mask, or killed by the gate? One reason usually accounts for most.
2. **Sweep `min_radius_mm`** 0.5 → 2.0. Plot F1. Sit mid-plateau, not on a spike.
3. **False positives by cause.** Look at them one at a time. They cluster into three or four causes (missed end cap, bone, iliac fork, organ leak). Fix by cause; tightening a global threshold trades 3 FPs for 5 FNs and nets nothing.
4. **De-duplication.**
5. **Ostium accuracy** — sub-voxel centroid, mid-wall nudge. 25% of the score for ~30 minutes.

P3 in this window: 22:00–23:30 the required visual checks (they're a submission requirement *and* how the others will diagnose false positives), then 23:30–01:00 the unrolled map.

- **Gate 01:00:** F1 ≈ 0.6+, zero crashes across all 25 cases, visual checks for ≥3 cases.

**01:00–01:45 · Lock in a submittable state**
**Hard rule: by 01:45 the repo is a complete valid submission.** Everything after is upside.
- **P2:** README — one setup command, one run command, method summary, config table, known failures, measured runtime and peak memory. Commit dev predictions and visual checks.
- **P1:** freeze the best config into `default.yaml`.
- **P3:** demo outline and the one method slide.

**01:45–07:00 · Sleep, all three at once.** Staggering costs more in coordination than it gains, and the specific failure mode of a sleep-deprived team here is a coordinate bug that silently eats 25% of the score and takes two hours to find. Set two alarms. If someone can't sleep, the useful solo task is rehearsing the demo, not touching code unsupervised.

**07:00–09:00 · Fresh eyes**
- **07:00–07:30, P2, before anything else:** fresh clone, fresh venv, **network disabled**, run the exact CLI from the brief. Something will break. Fix it now, not at 10:30.
- **P1:** remaining precision fixes; confirm parameters sit on a plateau — if a 10% threshold change swings F1 by 0.15 you're overfitted to the dev cases and the hidden set will punish you.
- **P3:** finish the unrolled map and the HTML report.
- **Gate 09:00 — feature freeze.** Config values and typos only.

**09:00–10:15 · Demo.** P3 leads, structure in §11.2, rehearse twice with a timer. Record it if a recording is required, and budget one retake. Final numbers into the README.

**10:15–10:45 · Submit.** Re-run the batch, commit predictions, walk `docs/checklist.md` line by line, submit at **10:45**. The last fifteen minutes are for the upload failing.

### Three rules that matter more at 18 hours than at 48

**Front-load the credits.** ~35% on the 16:40–20:30 build blocks, ~45% on the 22:00–01:00 debugging loop, ~20% reserve. Don't save credits for a tomorrow that's only four working hours long.

**Nothing blocks two people.** The contracts in §6 exist for this. If P1 needs the loader and it isn't ready, P1 writes against a numpy cylinder and integrates later. "I'll stub it" is always the right answer.

**A number at 22:00 beats a better algorithm at 02:00.** The gates are arranged so you're submittable at 22:00 and then improving a measured quantity. Teams that chase the elegant version and integrate at 03:00 find their coordinate bug at 09:00.

---

## 3. The domain knowledge you need

### 3.1 The picture

The **aorta** is the body's main pipe: blood leaves the heart, arcs over, runs down in front of the spine. The stretch in the belly is the **abdominal aorta** — that's your "parent," and you're given a binary mask of it. Smaller pipes peel off along the way to supply organs; those are your "daughters." At the bottom it forks into two pipes for the legs (the **iliac arteries**) — that fork is explicitly out of scope.

An **ostium** is just the mouth: the hole in the aortic wall where a daughter leaves. Garden hose with smaller hoses spliced into its side; the ostium is the splice.

### 3.2 The branches to expect, top to bottom

This table matters because it tells you *how many detections is plausible*.

| Branch | Count | Direction off the aorta | Typical radius |
|---|---|---|---|
| Inferior phrenic | 2 | up/sideways, near the diaphragm | ~0.7 mm |
| **Celiac trunk** | 1 | straight forward (anterior) | ~3.5 mm |
| Middle suprarenal | 2 | sideways | ~0.5 mm |
| **Superior mesenteric (SMA)** | 1 | forward, ~1 cm below celiac | ~3.5 mm |
| **Renal arteries** | 2 | straight out left and right | ~2.5 mm |
| Accessory renal | 0–2, ~30% of people | sideways, near the main renals | ~1.5 mm |
| Gonadal | 2 | forward-and-sideways, steeply down | ~0.7 mm |
| **Lumbar arteries** | 4 pairs = 8 | **backwards, toward the spine** | ~1.0 mm |
| **Inferior mesenteric (IMA)** | 1 | forward, slightly left | ~1.3 mm |
| Median sacral | 1 | backwards, at the very bottom | ~0.7 mm |

Consequences to internalise:

- A fully-covered aorta plausibly contains **10–20 eligible branches, not 5.** Find the celiac, SMA and both renals and stop, and your recall is ~30% — most of 45 points gone.
- **Lumbar arteries point backwards into the spine, and bone is bright on CT.** This is your worst confusion source and where half your misses will live.
- "Anatomical coverage varies" means some cases genuinely contain 2 branches. Your count must be data-driven. Never hard-code "there should be a celiac here."
- A **common trunk** (the celiac divides into three vessels 10–20 mm out) is **one** aortic daughter. Your contact-patch design (§5.7) handles this structurally — see §5.11.
- A vessel arising from another daughter isn't your problem: the same rule handles it, since only components touching the *aortic* wall count.

### 3.3 What CT gives you

A 3D array in **Hounsfield Units (HU)**, a calibrated density scale. Air −1000, water 0.

| Tissue | HU |
|---|---|
| Lung / air | −1000 to −500 |
| Fat | −100 to −50 |
| Muscle, unenhanced blood, liver | 30 to 80 |
| **Contrast-filled artery (your target)** | **200 to 500** |
| Enhanced kidney tissue | 100 to 250 |
| Cancellous (inner) bone | 100 to 300 |
| **Cortical bone, calcified plaque** | **500 to 1900** |

These are CT **angiograms**: iodine dye was injected, so arteries glow. That's the whole basis of your detector — the daughters are bright tubes physically attached to a bright tube you have a map of.

Three traps in that table:

1. **Bone overlaps your target range**, and the spine sits directly behind the aorta where the lumbars run.
2. **Calcified plaque** in the aortic wall is very bright and sits exactly where ostia are. It looks like a tiny bump. Reject by size and by failure to extend 5 mm.
3. **Enhanced organs** — kidney cortex especially — are bright and sit right at the end of the renal arteries. A low threshold floods into them.

**The key mitigation, and one of the strongest ideas in this document: calibrate everything against the aorta you were given.** Arteries carry the same dye at the same moment, so their lumen HU is close to the aortic lumen HU. Measure the aortic lumen's median and spread *in this case* and set thresholds relative to it. Contrast timing varies enormously between patients: one case's aorta sits at 480 HU, another's at 210. A fixed `> 200` finds nothing in the second and floods the kidneys in the first. This is the difference between working on 20 of 25 cases and working on 8.

Also record the aortic median for a *similarity* test: a component whose mean HU is within ~30% of it is very likely an artery; one sitting at 100 HU is a vein or an organ even if it's above threshold. Veins in an arterial-phase scan are consistently darker. Nearly free, and it kills a whole class of false positive.

### 3.4 Slices and axes

**Axial** = horizontal cross-section (the salami slice in the brief), usually the third array axis. **Coronal** = front-back split. **Sagittal** = left-right split. **Anterior/posterior** = front/back; **superior/inferior** = up/down; left and right are the *patient's*, so on a conventionally-viewed axial slice, patient-left appears on the image's right.

### 3.5 The coordinate rules (hard rules — 25% of the score)

A voxel index becomes a physical point via three things: **origin** (where voxel 0,0,0 sits), **spacing** (mm per voxel, often non-cubic like 0.7×0.7×1.0), and **direction cosines** (a 3×3 matrix describing how the array axes are rotated relative to the patient).

```python
import SimpleITK as sitk
img = sitk.ReadImage("orig1.nii")
# SimpleITK index order is (x, y, z) — the OPPOSITE of numpy's [z, y, x]
p_mm = img.TransformContinuousIndexToPhysicalPoint((float(i), float(j), float(k)))
```

1. **`sitk.GetArrayFromImage` returns `[z,y,x]`; SimpleITK's index methods take `(x,y,z)`.** Every conversion is a reversal. Write `np_to_sitk_index` and `sitk_to_np_index` helpers, use them everywhere, and never reverse a tuple inline.
2. **Never compute a distance or direction in voxel units.** Convert both endpoints to physical mm, *then* subtract. Anisotropic spacing and rotated direction cosines then handle themselves.
3. **SimpleITK works in LPS** (x → patient-left, y → posterior, z → superior); NIfTI files and 3D Slicer are **RAS**, so the signs of x and y flip between them. The brief mandates SimpleITK, so do everything in SimpleITK and you're consistent with the graders. The moment you compare against a point clicked in Slicer, negate x and y.
4. **Use `TransformContinuousIndexToPhysicalPoint`, not `TransformIndexToPhysicalPoint`.** Your ostium centre is an average of voxel positions and lands between voxels; rounding it away costs sub-millimetre accuracy for free.

---

## 4. The problem as an engineering spec

Strip the anatomy:

> **Input:** a 3D scalar field (CT, in HU) and a binary mask marking one connected tube inside it.
> **Output:** every *other* bright tube physically fused to the given tube, where "bright" is defined relative to the given tube's own interior. For each: the fusion point, an outward unit direction, a point 5 mm out along it, and its local half-width.
> **Constraints:** a tube counts only if it extends ≥5 mm beyond the parent wall and exceeds an unknown minimum size. The parent's flat cut ends are not fusion points. The bottom fork is not a fusion point. One instance per real tube, no duplicates.

That's essentially a connected-components problem. The hard parts are all *separation* problems:

- separating branches from bone, veins and enhancing organs;
- separating two nearby branches your threshold has bridged into one blob;
- separating a genuine branch from the aorta's own cropped end face;
- separating "one branch" from "two branches."

Note what it is **not**: not segmentation, not classification, not naming, not deep learning. With 25 cases, a handful of references, and a no-GPU no-internet evaluation box, **classical image processing is the correct answer.** Say so confidently in your demo.

---

## 5. The pipeline

Nine stages plus a scope list. Each is independently testable, which is what lets three people work at once.

```
CT + aorta mask
   │
   ├─ 1. Load, validate, crop to ROI, resample to 1 mm isotropic
   ├─ 2. Profile the aortic lumen → adaptive HU thresholds
   ├─ 3. Build the bright-candidate mask; suppress bone
   ├─ 4. Aorta centreline; wall surface; outward normals; clock frame
   ├─ 5. Mark the forbidden surface: cropped end caps + iliac fork
   ├─ 6. Candidate components: bright stuff touching the legal wall
   ├─ 7. Split contact patches → one instance per real ostium
   ├─ 8. Per branch: proximal path, seed, direction, radius
   └─ 9. Eligibility gate + de-duplication → JSON + visual report
```

### 5.1 Load, crop, resample  *(P2)*

**Crop first.** Aorta mask bounding box, padded 50 mm in every direction, discard the rest. This is the single biggest runtime win available: a 512×512×600 volume becomes maybe 150×150×450, a 15× reduction. Do it before anything else touches the data.

**Then resample to 1.0 mm isotropic**, linear for the CT, nearest-neighbour for the mask. Because:

- every morphological operation (dilation, distance transform) assumes cubic voxels; on 0.7×0.7×1.0 data a "5 mm dilation" is three different distances depending on direction, and your geometry silently skews;
- distance transforms become directly readable in mm;
- it bounds runtime — a case scanned at 0.5 mm slices no longer costs 4× as much.

The crucial property: **the resampled image still carries a valid origin/spacing/direction**, so `TransformContinuousIndexToPhysicalPoint` on the resampled grid returns correct physical mm in the original frame. You never convert back manually. Assert this in a test (§7.2).

Also validate inputs here: same geometry between image and mask, non-empty mask, single connected component. Log warnings; never crash.

### 5.2 Profile the aortic lumen  *(P2)*

```
aorta_core = binary_erosion(aorta_mask, radius=2mm)   # avoid partial-volume wall voxels
lumen_hu   = CT[aorta_core]
a_med, a_p10, a_iqr = median, 10th percentile, IQR
```

Derived thresholds, all multipliers from config:

- `t_vessel = max(a_med - k_vessel*(a_med - a_p10), frac_vessel*a_med, 120.0)` — the 120 HU floor stops you flooding into unenhanced soft tissue on a badly-timed scan.
- `t_high = frac_high * a_med` — the confident seed level for hysteresis.
- `t_bone = a_med + bone_offset`.

**Log all of these every run.** When a case misbehaves, this line tells you why at a glance.

### 5.3 Candidate mask and bone suppression  *(P2)*

```
seeds  = CT > t_high
grown  = apply_hysteresis_threshold(CT, t_vessel, t_high)   # skimage
bone   = dilate(CT > t_bone, 1.5mm)
candidate = (grown & ~bone & roi) | aorta_mask
then: drop any connected component not touching the aorta whose volume > max_stray_cc_ml
```

**Hysteresis** is the high-value move here: grow only from confident bright seeds into merely-bright voxels. One `skimage` call, and it substantially reduces leakage into kidney and liver while keeping thin distal lumen.

**Bone** by threshold alone is imperfect — dense contrast can exceed 500 HU and cancellous bone falls below it. The cheap fix that handles the vertebrae wholesale is the component-size rule above: bone in the abdomen is large and blobby, vessels are thin and tubular, and bone isn't connected to the aortic lumen. If posterior false positives still dominate at 23:00, tighten `bone_offset` and raise the minimum contact-patch area before reaching for anything cleverer.

### 5.4 Centreline, wall, clock frame  *(P1)*

The abdominal aorta runs roughly vertically, which permits a dead-simple and very robust centreline:

```
for each axial slice with aorta voxels:
    centreline[k] = centroid of the largest 2D connected component
smooth over k with a ~10 mm moving average or spline
```

This beats 3D skeletonisation for near-vertical vessels — skeletonisation produces spurs you then have to prune.

From the centreline you get three things you'll use constantly:

- **Wall surface:** `aorta_mask & ~binary_erosion(aorta_mask, 1 voxel)`.
- **Outward normal** at a wall voxel: normalise `(wall_point_mm − centreline_point_mm)` using the centreline point at the same slice. More stable than surface-mesh normals and good enough.
- **Clock angle:** in the axial plane, angle of the outward normal from anterior = 12 o'clock, increasing toward patient-left. Anterior is `−y` in LPS, so **build the frame from the image's direction cosines, never from an assumed array axis.** Plus **arc length** along the centreline from the superior end of coverage. These two power both a sanity check (celiac/SMA near 12, renals near 3 and 9, lumbars near 5–7) and the clinician view in §8.2.

### 5.5 The forbidden surface — the end-cap trap  *(P1, do not defer)*

**The most commonly fumbled requirement in the brief,** and it's stated explicitly: *"The flat superior and inferior ends created by cropping are not branch origins."*

Why it bites: the aorta mask stops at the edge of the annotated region, but the *actual* aorta continues, full of bright contrast. So the mask's flat top face has a large, bright, perfectly-attached blob hanging off it extending far more than 5 mm. A naive pipeline reports that as a giant branch — **on every single case, ~25 false positives.**

Remove from the searchable wall surface:

- all wall voxels within `endcap_mm` (4 mm) of the topmost and bottommost slices of the aorta mask;
- any wall voxel whose outward normal is within `endcap_angle_deg` (35°) of the local centreline tangent — i.e. it's part of a cap, not the side wall;
- everything at or below the first slice where the aorta mask splits into two components of comparable size (the **iliac fork**, out of scope), minus a 3 mm margin above.

**Don't silently drop these.** Record each with a reason and emit them in a separate top-level key:

```json
"excluded_candidates": [
  {"reason": "superior_end_cap", "ostium_xyz_mm": [...]},
  {"reason": "iliac_bifurcation", "ostium_xyz_mm": [...], "note": "optional extension"}
]
```

`daughters` stays clean for scoring, and you've visibly demonstrated you read the edge-case section. The brief says the iliacs "may be evaluated separately as an optional extension," so having them already computed and labelled is free upside.

### 5.6 Candidate components  *(P1)*

```
non_aorta = candidate & ~binary_dilation(aorta_mask, 1 voxel)
label 26-connected components
keep components adjacent to the LEGAL wall from 5.5
```

Per kept component compute, in mm: its **contact patch** (the legal wall voxels adjacent to it); its **maximum geodesic distance** from that patch through the component — your ≥5 mm eligibility test, and it must be geodesic not Euclidean because branches curve; plus volume, mean HU, and mean-HU ratio to `a_med`.

Geodesic distance inside a binary mask from a seed set: `skimage.graph.MCP_Geometric(costs=ones_inside, sampling=(1,1,1)).find_costs(seeds)` returns a distance field directly in mm. **This one object does most of the work in stages 6, 7 and 8 — learn it properly.**

### 5.7 From patches to instances  *(P1 — this is where the 45% is won)*

Two failure directions; you need the first guard for sure.

**Over-merging.** Celiac and SMA are ~10 mm apart; the renals face each other; accessory renals sit beside main renals. Partial-volume blur or a slightly low threshold bridges them into one component and you report 1 branch where there are 2. The brief is explicit: *"Two nearby origins must be returned as two instances when they are separate at the aortic wall."*

The fix is the central design decision of your detector: **one instance per contact patch, not per component.** Run connected components *on the contact patches over the wall surface*; each distinct patch is a candidate ostium. Then run a **multi-seed geodesic race** through the shared component — every voxel goes to whichever patch reaches it first, which `MCP_Geometric.find_costs` with multiple seeds gives you via its traceback array. A bridged blob splits cleanly into two branches, each with its own path.

This design also handles **common trunks** for free: the celiac has one hole in the aortic wall, so it's one patch, so it's one instance, regardless of what it does downstream.

**Over-splitting** is the mirror risk: noise or a calcification in the ostium breaks one patch into two, and duplicates count as false positives. The guard is to merge two patches whose centroids are within `dedup_dist_mm` (3 mm) **and** whose outward directions at 5 mm differ by less than `dedup_angle_deg` (30°). Two real branches 3 mm apart almost always head in clearly different directions; a split artefact produces two paths going the same way. **Keep the merge distance small** — the brief's instruction to separate nearby origins means the reference annotation does separate them, so bias toward splitting. This merge is on the cut line (§5.11); the split is not.

### 5.8 Per-branch geometry  *(P1)*

**Ostium.** Centroid of the contact patch in physical mm via `TransformContinuousIndexToPhysicalPoint`, sub-voxel, not rounded. Then nudge it to mid-wall (halfway between the eroded and dilated mask boundaries) — the reference is "the centre of the opening," which is a surface, so mid-wall is the least biased choice. A systematic 1 mm bias here costs you on every branch in a 25% category.

**Proximal path.** Compute the Euclidean distance transform (EDT) of the branch's voxel set — this is "distance to the vessel edge," maximal along the centre. Find the voxel at maximum geodesic distance from the ostium, capped at `trace_max_mm` (10 mm). Trace a minimum-cost path from ostium to target with cost `1/(EDT + 0.1)`, which keeps the path off the wall. Resample to 0.5 mm arc-length steps in physical mm.

**Seed.** The path point at `seed_arc_mm` (5 mm) arc length, then snapped to the local EDT maximum within a 1.5 mm neighbourhood. The brief scores "whether the seed lies on the matched daughter," so centring it buys margin against everyone's respective errors.

**Direction.** First principal component (PCA) of the path points between 1 mm and 7 mm, oriented away from the ostium, normalised. Don't use just two points — PCA is robust to one bad voxel. Physical mm only.

**Radius.** The EDT value at the seed, in mm. One line. Biased by your threshold (a tight threshold shrinks the apparent lumen) but consistent, which is what matters — and if the phantom shows a systematic bias you can correct it with a single config multiplier.

### 5.9 Eligibility gate and de-duplication  *(P1)*

Every threshold from config:

| Test | Config key | Default | Why |
|---|---|---|---|
| Geodesic extent beyond wall | `min_extent_mm` | 5.0 | Stated in the brief |
| Radius at seed | `min_radius_mm` | **0.8 — tune this first** | The unannounced size rule; your biggest lever |
| Contact patch area | `patch_area_min_mm2` / `max` | 3 / 120 | Too small = noise; too large = end cap or leak |
| Mean HU ratio to aortic median | `hu_ratio_min` | 0.70 | Rejects veins and organs |
| Path tortuosity over 10 mm | `tortuosity_max` | 2.0 | Rejects paths snaking through leaked tissue |
| Not on the forbidden surface | — | — | §5.5 |
| Not a duplicate | `dedup_dist_mm` / `dedup_angle_deg` | 3 / 30 | Duplicates are false positives |

Then write JSON. And wrap **every case** in a try/except that, on any failure, still writes a valid file with an empty `daughters` list and a `warnings` field. A crash on one hidden case costs more than that case's score, because "successful execution on unseen cases" is the reproducibility criterion.

### 5.10 Output format

Exactly as the brief specifies, plus two additive keys that cost nothing and demonstrate judgment:

```json
{
  "case_id": "subject001",
  "parent": {"instance_id": "aorta"},
  "daughters": [
    {
      "instance_id": "branch_001",
      "parent_instance_id": "aorta",
      "ostium_xyz_mm": [12.4, -31.8, 184.6],
      "seed_xyz_mm": [15.1, -29.7, 181.2],
      "radius_mm": 2.7,
      "direction_xyz": [0.56, 0.43, -0.71],
      "confidence": 0.91,
      "clock_position": 12.4,
      "arclen_from_top_mm": 41.2,
      "takeoff_angle_deg": 78.3
    }
  ],
  "excluded_candidates": [{"reason": "superior_end_cap", "ostium_xyz_mm": [...]}],
  "meta": {"runtime_s": 19.4, "a_med_hu": 342.0, "t_vessel_hu": 198.0, "warnings": []}
}
```

The required fields must be exactly right. `direction_xyz` must be a unit vector pointing from the ostium into the daughter. Every `instance_id` unique, every `parent_instance_id` equal to `"aorta"`. Verify with a schema check in `batch.py`.

### 5.11 Out of scope for this build — do not implement

Cut deliberately for the 18-hour window. If an LLM proposes any of these, decline.

| Cut | Why it's safe to cut |
|---|---|
| **Fork/bifurcation detection** along the proximal path | A common trunk has one hole in the aortic wall, so §5.7 already returns it as one instance. And the celiac forks 10–20 mm out while your seed sits at 5 mm — before the fork. Just cap the path at 10 mm. |
| **Vesselness / Frangi / Sato filtering** | Costs ~8 s/case and also attenuates the short proximal stumps you care about. The component-size rule in §5.3 handles the spine more cheaply. |
| **Half-max-area radius estimation** | EDT radius is consistent, and consistency is what the scorer measures. |
| **Random forest / learned accept-reject gate** | Needs ~100 labelled candidates you won't have. With 30 it overfits and hurts. |
| **Multi-scale recovery pass at 0.6 mm** | Runtime cost, speculative recall gain. |
| **Clicking fiducials in 3D Slicer for extra ground truth** | Too slow. Count branches by eye instead (§7.3). |
| **Interactive 3D plotly views** | Static MIPs plus the unrolled map are more convincing per minute spent. |
| **Any pretrained model** (TotalSegmentator, nnU-Net) | Needs downloads and usually a GPU; the evaluation box has neither. Also solves a different problem — naming known structures, not discovering unnamed ones. |

**Order of cuts if you fall behind a gate.** Top first:

1. Patch-merge logic in §5.7 (keep the splitting)
2. Iliac-fork special-casing in §5.5 (the end-cap rule usually covers it)
3. The HTML report wrapper (keep the PNGs and JSON)
4. Sub-voxel / mid-wall ostium refinement
5. The unrolled aortic map

**Never cut:** end-cap suppression · aorta-relative adaptive thresholding · the per-case try/except · the exact CLI signature · the README with one setup and one run command · coordinate correctness.

---

## 6. Repository layout and module contracts

Agree these in the first thirty minutes and treat them as frozen. This is what lets three people and three LLM sessions work simultaneously without merge hell.

```
branchseed/
├── run.py                  # the required CLI, thin wrapper only
├── requirements.txt
├── README.md
├── CLAUDE.md
├── config/default.yaml     # EVERY threshold lives here
├── docs/{brief.md,checklist.md}
├── src/
│   ├── io_geom.py          # S1: load, validate, crop, resample, index<->mm
│   ├── intensity.py        # S2: aortic profile, adaptive thresholds
│   ├── candidates.py       # S3: bright mask, bone suppression
│   ├── aorta_frame.py      # S4/S5: centreline, wall, normals, clock, forbidden
│   ├── instances.py        # S6/S7: components, contact patches, split
│   ├── geometry.py         # S8: path, seed, direction, radius
│   ├── gate.py             # S9: eligibility + dedup
│   └── report.py           # JSON writer + visual checks + unrolled map
├── eval/{score.py,phantom.py,batch.py}
└── tests/
```

### Frozen interfaces

```python
# io_geom.py                                                    [P2]
@dataclass
class Case:
    ct: sitk.Image              # cropped, 1mm isotropic, HU
    aorta: sitk.Image           # same grid, uint8
    ct_np: np.ndarray           # [z,y,x] float32
    aorta_np: np.ndarray        # [z,y,x] bool
    case_id: str
def load_case(image_path, mask_path, cfg) -> Case
def idx_to_mm(case, zyx) -> np.ndarray      # accepts float; point or (N,3)
def mm_to_idx(case, xyz_mm) -> np.ndarray   # returns float [z,y,x]

# intensity.py                                                  [P2]
@dataclass
class Profile:
    a_med: float; a_p10: float; a_iqr: float
    t_vessel: float; t_high: float; t_bone: float
def profile_aorta(case, cfg) -> Profile

# candidates.py                                                 [P2]
def candidate_mask(case, profile, cfg) -> np.ndarray   # bool [z,y,x]

# aorta_frame.py                                                [P1]
@dataclass
class AortaFrame:
    centreline_mm: np.ndarray     # (N,3) superior -> inferior
    wall_np: np.ndarray           # bool, all wall voxels
    legal_wall_np: np.ndarray     # bool, wall minus forbidden
    excluded: list[dict]          # end caps / iliac fork, with reasons
def build_frame(case, cfg) -> AortaFrame
def outward_normal(frame, zyx) -> np.ndarray
def clock_and_arclen(frame, xyz_mm) -> tuple[float, float]   # hours, mm

# instances.py                                                  [P1]
@dataclass
class RawBranch:
    patch_zyx: np.ndarray         # (M,3) contact patch voxels
    voxels_zyx: np.ndarray        # (K,3) assigned branch voxels
    geodesic_extent_mm: float
    patch_area_mm2: float
    mean_hu: float
    hu_ratio: float
def find_raw_branches(case, cand, frame, profile, cfg) -> list[RawBranch]

# geometry.py                                                   [P1]
@dataclass
class BranchGeom:
    ostium_mm: np.ndarray; seed_mm: np.ndarray
    direction: np.ndarray; radius_mm: float
    path_mm: np.ndarray           # (P,3) for the visualisation
    tortuosity: float
def measure(case, raw: RawBranch, frame, profile, cfg) -> BranchGeom

# gate.py                                                       [P1]
def accept(raw, geom, profile, cfg) -> tuple[bool, str]   # (keep?, reason)
def dedup(items, cfg) -> list
```

### Rules that prevent 90% of integration pain

- **All coordinates crossing a module boundary are physical mm.** Voxel indices stay inside the module that owns them.
- **Numpy arrays are always `[z,y,x]`; SimpleITK tuples are always `(x,y,z)`.** Conversions happen only in `io_geom.py`.
- **No module reads a constant that isn't in `cfg`.** No exceptions, including temporary ones.
- **Every function is pure** — no global state, no file writes — except `run.py` and `report.py`. This is what makes them unit-testable and what makes an LLM able to write one correctly in isolation.
- Short-lived branches, PRs merged within the hour, `main` always runs. **P2 is the integrator with a veto on merges.** Skip this and you'll spend the final three hours debugging a merge instead of tuning.

---

## 7. `config/default.yaml`

Create this at 16:10 and never write a numeric literal in `src/` again.

```yaml
# geometry / preprocessing
iso_mm: 1.0                 # isotropic resample spacing
roi_margin_mm: 50.0         # padding around the aorta bounding box

# intensity thresholds (all relative to the aortic lumen)
k_vessel: 2.0               # t_vessel = a_med - k_vessel*(a_med - a_p10)
frac_vessel: 0.55           # ...floored at frac_vessel * a_med
frac_high: 0.85             # hysteresis seed level
vessel_hu_floor: 120.0      # absolute floor, never threshold below this
bone_offset: 300.0          # t_bone = a_med + bone_offset
bone_dilate_mm: 1.5
max_stray_cc_ml: 50.0       # drop unattached components larger than this

# aortic frame / forbidden surface
centreline_smooth_mm: 10.0
endcap_mm: 4.0              # exclude wall within this of the mask's top/bottom
endcap_angle_deg: 35.0      # exclude wall whose normal aligns with the axis
iliac_margin_mm: 3.0

# branch tracing
trace_max_mm: 10.0
seed_arc_mm: 5.0
path_step_mm: 0.5
pca_window_mm: [1.0, 7.0]
seed_snap_mm: 1.5

# eligibility gate
min_extent_mm: 5.0
min_radius_mm: 0.8          # <<< THE UNANNOUNCED SIZE RULE. Sweep 0.5-2.0 first.
patch_area_min_mm2: 3.0
patch_area_max_mm2: 120.0
hu_ratio_min: 0.70
tortuosity_max: 2.0

# de-duplication
dedup_dist_mm: 3.0
dedup_angle_deg: 30.0

# runtime
verbose: true
log_rejections: true        # log every rejected candidate with its reason
```

`log_rejections` is not optional decoration — it's the instrument you'll use at 22:00 to find out why you're missing branches. Turn it on from the start.

---

## 8. Your two most important tools

### 8.1 The scoring harness — `eval/score.py`  *(P3, 18:30)*

Build this before the detector. Output shape:

```
case         n_ref  n_pred  TP  FP  FN  prec  recall    F1  ost_mm(mean/max)  ang°  dr_mm
subject001      11      10   9   1   2  0.90    0.82  0.86        2.1 / 4.8  12.4   0.31
```

- **Matching must be one-to-one.** `scipy.optimize.linear_sum_assignment` on the pairwise ostium-distance matrix, then reject matches over a threshold. Greedy nearest-neighbour gives optimistic, misleading numbers exactly when two branches are close — the situation you're trying to get right.
- The graders' matching threshold is unknown. **Report at 3, 5 and 10 mm.** If F1 collapses between 10 and 5 mm, localisation is your bottleneck, not detection.
- Also compute: angle between predicted and reference direction; `|r_pred − r_ref|`; and whether the seed lies within the reference radius of the reference proximal centreline (the "seed lies on the matched daughter" test).
- Aggregate **micro** (pooled) and **macro** (mean per-case F1). They diverge when one case dominates, and knowing which is which stops you chasing a phantom improvement.
- `--sweep min_radius`: re-score a directory of predictions generated at different config values and print F1 against the swept value.

### 8.2 The synthetic phantom — `eval/phantom.py`  *(P3, 16:40, build this first)*

The idea that most levels the playing field for a team without anatomy knowledge. Almost nobody does it.

Generate a NIfTI volume containing: background 40 HU; a vertical cylinder radius 10 mm at 350 HU (the aorta) plus its own binary mask; N branch cylinders at chosen positions, directions, radii and lengths at 320 HU; a 0.8 mm Gaussian blur for partial volume; 15 HU Gaussian noise. Optional extras: a 700 HU slab 25 mm posterior (a spine), a 900 HU 2 mm sphere in the aortic wall (a calcification), a dimmer 120 HU parallel cylinder (a vein), and a branch that forks at 7 mm (a trunk).

Because you generated it, you know the exact reference JSON. Now you can test things real data can never tell you:

- Is my ostium within 1 mm of truth? **(validates the 25% category)**
- Is my radius within 0.3 mm? Biased high or low? **(a systematic EDT bias is correctable with one config multiplier — but only if you can see it)**
- Is my direction within 5°?
- **Does my coordinate handling survive anisotropic spacing and non-identity direction cosines?** Generate the same phantom at 0.7×0.7×2.0 mm and with a rotated direction matrix. If your output points move, you have a bug silently costing you on every real case. **This test alone justifies the phantom.**
- Does a *short* phantom, cropped so only 2 branches exist, yield exactly 2 with no end-cap false positives?

An hour of work, an infinite perfectly-labelled dataset for every geometric part of the score, and a regression suite so you can change things at 00:30 without fear.

### 8.3 Extra ground truth, cheaply  *(P3, 20 minutes at 18:10)*

Reference outputs come with only a small dev subset. The affordable expansion is **count-only labels**: each of you independently counts visible branches on a handful of cases in a viewer (3D Slicer is free and opens NIfTI). Comparing your predicted count to a human count catches systematic recall failures across the whole set even without positions — and it's how you'll discover, if you have, that you're finding 4 branches where a human sees 12.

Tuning against three dev cases is how you build something that scores 0.85 on dev and 0.45 on the hidden set.

---

## 9. The clinician view

The brief asks for two separate things and most teams will conflate them. Build both.

### 9.1 The verification view — required, keep it cheap  *(P3, 22:00–23:30)*

*"a simple visual check for at least three cases showing the aorta mask, detected ostia and daughter-direction arrows."* One PNG per case, three panels, matplotlib only:

- **Coronal maximum-intensity projection** (`ct_np.max(axis=1)`) with the aorta mask boundary contoured, ostia as dots, directions as in-plane arrows. MIPs make vessels look like vessels, which makes errors instantly obvious.
- **Sagittal MIP**, same overlay. Anterior branches (celiac, SMA, IMA) are unmistakable here.
- **A strip of axial slices**, one per detected ostium, cropped to ±40 mm around the centreline, marker on the ostium, arrow for the direction, labelled with instance ID and radius. This is the panel a judge will actually scrutinise, because it's where they can independently verify you're right.

Must not crash with zero detections.

### 9.2 The unrolled aortic map — the differentiator  *(P3, 23:30–01:00)*

Here's the domain insight that makes this land. When surgeons plan a **fenestrated stent graft** — a fabric tube placed inside a diseased aorta, which must have holes cut in it precisely where the branches leave — the numbers they need per branch are:

1. **distance** along the aorta from a fixed landmark,
2. **clock position** around the circumference (12 o'clock = anterior),
3. **diameter** of the branch,
4. **takeoff angle** relative to the aortic axis.

That is *exactly* the four quantities your pipeline computes. And the standard way to present them is a **cylindrical unrolling**: cut the aorta lengthwise and flatten it into a rectangle.

So plot a 2D chart:

- **x axis:** arc length along the aortic centreline in mm from the superior end of coverage.
- **y axis:** clock position, 12 → 3 → 6 → 9 → 12.
- **each branch:** a circle sized by its true radius, annotated `branch_003 · r=2.6 mm · 14.2 mm · 3 o'clock · 78°`.
- shade horizontal bands for anterior / lateral / posterior.
- excluded candidates as hollow grey markers with their reason.

On a normal case this produces an immediately legible signature: two dots near 12 o'clock at the top (celiac, SMA), a facing pair at 3 and 9 (the renals), a small one near 1–2 lower down (the IMA), and a regular ladder of small dots around 5 and 7 (the lumbars). **A clinician can check your entire output in three seconds — and so can a judge.** If your map shows the renals at 4 and 8 instead of 3 and 9, you have a bug, visibly.

That last property is why it's worth building even ignoring the rubric: it is simultaneously the best debugging tool you'll have and the most impressive thing in your demo. It answers "useful for clinicians" with something real rather than decorative, and it gives you a confident answer to the inevitable *"who would use this and how?"*

### 9.3 Wrap it in one self-contained HTML file per case  *(only if ahead at 07:00)*

`report_subject001.html`, no external dependencies, images inlined as base64: header with case ID, runtime, branch count and derived thresholds; the unrolled map; a table of instance ID / distance / clock / radius / takeoff angle / confidence; the axial verification strip; the excluded candidates with reasons. One file, openable by double-click, no server. Judges can poke at it themselves, which is worth more than any slide.

---

## 10. Getting real work out of the LLMs

### 10.1 Which tool for what

| Tool | Best for | Avoid |
|---|---|---|
| Chat (Claude Pro, Gemini Pro) | Algorithm questions, "explain what a geodesic distance transform does," one self-contained function, reviewing a diff you paste in, debugging a stack trace | Multi-file refactors, anything needing to see your actual data |
| Claude Code ($25) | Tasks where reading and running the repo is the point: wiring modules, the test suite, and above all **running your pipeline on real cases and iterating on the output** | Open-ended discussion you could have had in chat for free |

Reserve the credits for Claude Code because it can execute your code and inspect results — that closes the loop. A chat model guessing why you missed the left renal artery is far less useful than an agent that runs the case, prints the rejection log, and checks.

### 10.2 `CLAUDE.md`, written at 16:10

Claude Code reads this from your project root at the start of every session. Keep it short and specific — put in the non-obvious project rules, not things derivable from the code.

```markdown
# Branchseed Challenge

## Task
Detect arteries branching directly off a given abdominal aorta mask in CTA volumes.
Output JSON with ostium_xyz_mm, seed_xyz_mm, radius_mm, direction_xyz per branch.
Full spec: docs/brief.md. Plan: docs/playbook.md.
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
```

Use plan mode for anything touching more than one file. Start a fresh session per task rather than letting one conversation sprawl — long contexts cost more and drift more.

### 10.3 How to prompt for code that works

**Give the contract, not the vibe.**

> ❌ "Write code to find branches coming off the aorta in a CT scan."
> ✅ "Implement `find_raw_branches(case, cand, frame, profile, cfg) -> list[RawBranch]` per the signatures below. `cand` is a bool numpy array `[z,y,x]` at 1 mm isotropic. `frame.legal_wall_np` is a bool array of aortic wall voxels allowed to host an ostium. Steps: (1) … (2) … Use only numpy, scipy.ndimage, skimage. No loops over voxels. Every threshold from `cfg`."

The second gets working code first try. It takes two minutes to write and saves an hour.

**Paste the relevant brief text** whenever the task is spec-driven (end caps, output format, eligibility). Models otherwise invent plausible-but-wrong requirements and you build to them.

**Demand tests alongside.** "Also write a pytest that builds a 60³ array with a 10 mm cylinder and two known branches and asserts the function returns exactly 2 with extents within 1 mm." This catches the 20% of generated code that looks right and isn't.

**Always name the library.** Models fluidly mix `nibabel`, `SimpleITK`, `itk` and `pydicom` conventions, which have *different* axis orders. Mixed-convention code is the number one source of silent coordinate bugs. Pin it: "SimpleITK only for I/O and geometry; numpy/scipy/skimage for array work."

**End every prompt with:** "Then list the three ways this will produce wrong results on real data and what I should check." Models are good at this and it points your debugging at the real problems.

### 10.4 Where LLMs will confidently mislead you here

- **Axis order.** Generated code mixes `[z,y,x]` and `(x,y,z)`. Assume it's wrong until the phantom test passes.
- **Hard-coded HU thresholds.** Models love `blood > 200`. Insist on §5.2.
- **Suggesting a pretrained model.** TotalSegmentator and nnU-Net will come up. Downloads, usually a GPU, wrong problem. Decline.
- **`skeletonize_3d` on the whole candidate mask.** Sounds right, produces a spur-covered mess. Geodesic paths from known seeds are better.
- **Forgetting the end caps.** No model spontaneously remembers that cropped aortic ends aren't branches. You have to tell it.

### 10.5 Spending the $25

~35% on the 16:40–20:30 build blocks (well-specified, agentic file creation beats copy-pasting from chat) · ~45% on the 22:00–01:00 debugging loop, which is the highest-value use — *"run subject004, print every rejected candidate with its reason and its distance to the nearest reference ostium, and tell me the dominant failure mode"* · ~20% reserve, because something will break at 07:15. Use the free chat subscriptions for everything conversational.

### 10.6 Prompt pack

Paste roughly in clock order. Each assumes `CLAUDE.md` and the §6 contracts are already in the repo. Append the "list three ways this will be wrong" line to all of them.

**1 · Scaffold** *(16:00, P2)*
> Create a Python project skeleton for the task in `docs/brief.md`, with the layout in `docs/playbook.md` §6. Create every module with the dataclasses and function signatures pasted below, full docstrings stating units, and `raise NotImplementedError` bodies. `run.py` must implement exactly `python run.py --image X --aorta-mask Y --output Z`, call the stages in order, support both `.nii` and `.nii.gz`, load `config/default.yaml`, and wrap everything in a try/except that always writes valid JSON with an empty `daughters` list on failure. Pin versions in `requirements.txt`: SimpleITK, numpy, scipy, scikit-image, PyYAML, matplotlib. Nothing that downloads at runtime. `[paste §6 interfaces and §7 config]`

**2 · Loader and coordinates** *(16:40, P2)*
> Implement `io_geom.py`. `load_case`: read both with SimpleITK; assert matching size/spacing/origin/direction (warn and resample the mask to the image grid rather than crashing if they differ); crop both to the aorta bounding box padded by `cfg.roi_margin_mm`, clipped to the volume; resample to `cfg.iso_mm` isotropic, linear for CT and nearest-neighbour for the mask; return the `Case` dataclass with both SimpleITK images and `[z,y,x]` numpy views. Implement `idx_to_mm` and `mm_to_idx` using `TransformContinuousIndexToPhysicalPoint` / `TransformPhysicalPointToContinuousIndex`, accepting floats and either a single point or `(N,3)`, remembering numpy is `[z,y,x]` and SimpleITK is `(x,y,z)`. Then `tests/test_io_geom.py` asserting a voxel→mm→voxel round trip within 0.5 mm, and asserting it still holds on a synthetic image with spacing `(0.7,0.7,2.0)` and a non-identity direction matrix.

**3 · Phantom** *(16:40, P3)*
> Write `eval/phantom.py` per `docs/playbook.md` §8.2: generate a synthetic CTA-like NIfTI volume plus its exact reference JSON. Background 40 HU; vertical cylinder radius 10 mm at 350 HU along z with its own binary mask written separately; N branch cylinders at caller-specified positions, directions, radii and lengths at 320 HU; 0.8 mm Gaussian blur; 15 HU Gaussian noise. Options for a 700 HU slab 25 mm posterior, a 900 HU 2 mm sphere in the aortic wall, a dimmer 120 HU parallel cylinder, and a branch forking at 7 mm. Write the reference JSON in the challenge's exact output format with `ostium_xyz_mm` on the aortic surface, `seed_xyz_mm` at 5 mm along the branch axis, the true radius and true unit direction — all through `TransformContinuousIndexToPhysicalPoint` so they're in the same physical frame. Expose `spacing` and `direction` arguments so I can generate anisotropic and rotated variants.

**4 · Aorta frame and forbidden surface** *(16:40, P1)*
> Implement `aorta_frame.py` per `docs/playbook.md` §5.4 and §5.5. Centreline: for each axial slice containing mask voxels, the centroid of the largest 2D connected component, smoothed over `cfg.centreline_smooth_mm`. `wall_np` = mask minus its one-voxel erosion. `outward_normal` returns the normalised vector from the centreline point at that slice to the wall point, in physical mm. `legal_wall_np` removes: (a) wall voxels within `cfg.endcap_mm` of the topmost or bottommost slice containing mask voxels; (b) wall voxels whose outward normal is within `cfg.endcap_angle_deg` of the local centreline tangent; (c) everything at or below the first slice where the mask splits into two comparable components, minus `cfg.iliac_margin_mm`. Record each removed region in `frame.excluded` with a reason string. Also `clock_and_arclen`, returning clock position in hours with 12 o'clock = anterior — **derive anterior from the image direction cosines in LPS, where anterior is −y; do not assume an array axis** — and arc length in mm from the superior end.

**5 · Scorer** *(18:30, P3)*
> Write `eval/score.py` per `docs/playbook.md` §8.1. Load a prediction and a reference JSON in the format in `docs/brief.md`. Build the pairwise Euclidean distance matrix between `ostium_xyz_mm` values, match one-to-one with `scipy.optimize.linear_sum_assignment`, reject matched pairs beyond a threshold. Report, at thresholds 3, 5 and 10 mm: TP, FP, FN, precision, recall, F1, mean and max ostium distance over matches, mean angle in degrees between directions, mean absolute radius error, and whether each predicted seed lies within the reference radius of the reference seed. Aggregate micro and macro. Print a per-case table plus a summary row. Add `--sweep min_radius` to re-score a directory of predictions produced at different config values and print F1 against the swept value.

**6 · Intensity and candidates** *(18:30, P2)*
> Implement `intensity.py` and `candidates.py` per `docs/playbook.md` §5.2 and §5.3. `profile_aorta`: erode the aorta mask by 2 mm, take CT values inside, return median / 10th percentile / IQR plus `t_vessel = max(a_med - cfg.k_vessel*(a_med-a_p10), cfg.frac_vessel*a_med, cfg.vessel_hu_floor)`, `t_high = cfg.frac_high*a_med`, `t_bone = a_med + cfg.bone_offset`. Log all of them. `candidate_mask`: `skimage.filters.apply_hysteresis_threshold` with `t_vessel` as the low level and `t_high` as the high level; exclude voxels above `t_bone` dilated by `cfg.bone_dilate_mm`; union in the aorta mask; then remove any connected component not touching the aorta whose volume exceeds `cfg.max_stray_cc_ml`. Return bool `[z,y,x]`. Vectorised only, no per-voxel loops, no literals.

**7 · Instancing** *(18:30, P1)*
> Implement `instances.find_raw_branches` per `docs/playbook.md` §5.6 and §5.7. Remove from `cand` the aorta mask dilated by one voxel; label with 26-connectivity; per component find the adjacent `frame.legal_wall_np` voxels (its contact patch); label connected components of the contact patches over the wall surface so one component with two distinct patches yields two candidates; for those, assign every voxel to the nearest patch by geodesic distance inside the component using `skimage.graph.MCP_Geometric` with multiple seeds and its traceback; compute per instance the maximum geodesic distance from its patch in mm, its voxel set, patch area in mm², mean HU, and the ratio of mean HU to `profile.a_med`. Return `list[RawBranch]`. Vectorised, all thresholds from `cfg`.

**8 · Per-branch geometry** *(20:30, P1)*
> Implement `geometry.measure` per `docs/playbook.md` §5.8. Ostium: contact-patch centroid via `TransformContinuousIndexToPhysicalPoint`, sub-voxel, not rounded, nudged to mid-wall. Path: EDT of the branch voxel set in mm; target = voxel at maximum geodesic distance from the patch capped at `cfg.trace_max_mm`; minimum-cost path from ostium to target with cost `1/(EDT+0.1)` so it hugs the lumen centre; resampled to `cfg.path_step_mm` arc-length steps in physical mm. Seed: path point at `cfg.seed_arc_mm` arc length, snapped to the local EDT maximum within `cfg.seed_snap_mm`. Direction: first principal component of path points within `cfg.pca_window_mm`, oriented away from the ostium, normalised. Radius: EDT value at the seed in mm. Tortuosity: path length divided by straight-line ostium-to-end distance. Then a test against `eval/phantom.py` asserting ostium within 1.5 mm, radius within 0.4 mm and direction within 8° of truth — **and asserting these still hold on the anisotropic and rotated phantom variants.**

**9 · Gate, dedup, batch** *(20:30, P1 + P2)*
> Implement `gate.accept` and `gate.dedup` per `docs/playbook.md` §5.9, returning `(keep, reason)` so rejections can be logged when `cfg.log_rejections`. Then `eval/batch.py`: walk a data directory of `subjectNNN/` folders, run the full pipeline on each, write one prediction JSON per case plus a CSV of per-case runtime, peak memory, branch count and derived thresholds; validate every output against the required schema (unique instance IDs, `parent_instance_id == "aorta"`, unit-length directions, three finite coordinates); never let one case's failure stop the batch.

**10 · Visual check** *(22:00, P3)*
> Write a function in `src/report.py` producing one verification PNG per case, per `docs/playbook.md` §9.1: three panels — coronal MIP with the aorta boundary contoured plus ostia dots and projected direction arrows; the same for sagittal; and a vertical strip of axial slices, one per ostium, cropped to ±40 mm around the centreline with a marker, an in-plane arrow, and a label of instance ID and radius. matplotlib only, consistent physical scaling, must not crash with zero detections.

**11 · Unrolled aortic map** *(23:30, P3)*
> Write a function in `src/report.py` rendering the unrolled aorta per `docs/playbook.md` §9.2: a 2D matplotlib chart, x = arc length along the aortic centreline in mm from the superior end, y = clock position running 12 → 3 → 6 → 9 → 12 with 12 o'clock meaning anterior. Each detected branch is a circle sized proportionally to its true radius, annotated with instance ID, radius, clock position and takeoff angle relative to the local aortic axis. Shade horizontal bands labelled anterior / lateral / posterior. Excluded candidates as hollow grey markers with their reason. This is a clinical planning view — prioritise legibility over decoration.

---

## 11. Delivery

### 11.1 Submission checklist

Copy into `docs/checklist.md` at 16:00 and verify each physically at 10:30.

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

The fresh-clone / no-network rehearsal happens at 07:00 **and** at 10:15. Not once, and never for the first time in the final hour.

### 11.2 The five-minute demo

- **0:00–0:30 — The problem in their words.** "Given the aorta, find every artery leaving it, without knowing in advance which or how many." One sentence on why: stent-graft planning needs the position of every branch, and the anatomy varies per patient.
- **0:30–1:45 — Method, one slide, the pipeline diagram.** Emphasise the two ideas that are actually yours: **aorta-relative adaptive thresholding** (works across contrast timing) and **one instance per contact patch with a geodesic race** (separates branches that touch, and handles common trunks structurally). Name the edge cases you handled deliberately: cropped end caps, common trunks, the iliac fork.
- **1:45–3:00 — Results, with numbers.** P/R/F1, mean ostium error in mm, mean direction error in degrees, radius error, runtime, peak memory. Show the **F1 vs `min_radius_mm` curve** — it proves you understood the size cutoff is a parameter rather than a guess.
- **3:00–4:00 — The clinician view,** live in a browser. Let the unrolled map speak. Point out how you'd verify a whole case in three seconds.
- **4:00–4:40 — Known failure cases.** Specific and unembarrassed: "we miss lumbars under 0.8 mm radius"; "heavy wall calcification gives about one false positive every three cases"; "one case has a stent whose metal artefact breaks our threshold." Then what you'd do next. **This section wins trust** — teams claiming everything works are assumed not to have looked.
- **4:40–5:00 — Close.** What it does, how fast, what it would need to be usable.

Rehearse with a timer. Give each person a defined section; judges notice when one person does all the talking.

---

## 12. Risks and budgets

| Risk | Impact | Mitigation | Owner |
|---|---|---|---|
| Coordinate convention bug | Catastrophic — all 25% of localisation, silently | Phantom test with anisotropic spacing and rotated direction cosines, by 18:30 | P2 |
| Cropped end caps reported as branches | ~25 false positives | §5.5, implemented in Block 1 not overnight | P1 |
| Recall collapse from too-tight size gate | Half of the 45% | Sweep `min_radius_mm`; sit on a plateau; log every rejection with its reason | P1 |
| Only finding the 4 famous branches | Same | Know that 10–20 is plausible; count by eye on real cases by 18:30 | P3 |
| Bone / spine contamination | False positives posteriorly, where the lumbars live | `bone_offset` + the stray-component rule + patch-area limits | P2 |
| Threshold leak into kidney or liver | Giant merged components, missed renals | Hysteresis threshold; stray-component volume rule | P2 |
| Overfitting to 2–3 dev cases | Dev 0.85, hidden 0.45 | Count-only labels; prefer flat parameters over spikes | P3 |
| A crash on a hidden case | Loses the case *and* the reproducibility marks | Per-case try/except, always emit valid JSON | P2 |
| Dependency needs internet or a GPU | Total failure on the eval box | Pin everything; offline fresh-venv rehearsal at 07:00 | P2 |
| Runtime blowup | Loses the 10% | Crop to bbox + 50 mm first; 1 mm isotropic; profile at 21:30 | P2 |
| Merge conflict chaos near the deadline | Loses tuning time | Small PRs, P2 integrates, feature freeze 09:00 | all |
| Two people build the same thing | Loses a person-day you don't have | Frozen contracts at 16:30 | all |
| Nobody owns the demo | Great project, forgettable presentation | P3 owns it from 16:00, rehearses twice | P3 |

### Runtime budget (1 mm isotropic, cropped ROI)

| Stage | Budget |
|---|---|
| Load + crop + resample | 3 s |
| Aortic profile | < 1 s |
| Candidate mask + bone suppression | 3 s |
| Centreline + wall + forbidden surface | 2 s |
| Components + contact patches | 3 s |
| Geodesic race + per-branch paths (×15) | 8 s |
| Seed / direction / radius (×15) | 2 s |
| JSON + report | 2 s |
| **Total** | **~23 s** |

Comfortable margin under 60 s. Peak memory at 1 mm on a cropped ROI should sit under 2 GB in float32. If you exceed either, relax to 1.2 mm isotropic.

### If you're ahead of schedule at 07:00

In value order: (1) a **confidence score** per branch combining HU ratio, geodesic extent, patch quality and radius — costs nothing, is honest, is what a clinical tool would need for triage, and lets you present a precision/recall curve instead of a single operating point; (2) promote the already-detected iliacs from `excluded_candidates` into an `optional_iliacs` list for the brief's optional extension; (3) the HTML report wrapper (§9.3).

---

## 13. The wall sheet

```
16:40  empty JSON runs via the exact CLI          all three
18:30  loader + phantom + legal wall (end caps gone)
20:30  end-to-end on the phantom        ← CRITICAL
22:00  real F1, predictions committed, tag v1-safe
01:00  F1 ~0.6, zero crashes, 3 visual checks
01:45  SUBMITTABLE — then sleep
07:30  fresh clone, no network, works
09:00  feature freeze
10:15  demo rehearsed twice
10:45  SUBMIT
```

**Five things, if you do nothing else:**

1. Build the scorer and the phantom before the detector.
2. Handle the cropped aortic end caps in Block 1.
3. Every threshold case-adaptive against the aortic lumen; every constant in config.
4. Assume 10–20 branches, not 5. Log every rejection with its reason and hunt recall before precision.
5. Build the unrolled aortic map.

**Never cut:** end caps · adaptive thresholds · try/except · the exact CLI · README · coordinates.

The task is narrower than it looks. The winning version is a careful ~800-line classical pipeline with an excellent test harness — not a clever model.
