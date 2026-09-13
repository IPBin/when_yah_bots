"""
JSON writer + visual checks (§9.1) + unrolled aortic map (§9.2) + optional
self-contained HTML report (§9.3).

Owner: P3 (visual checks, unrolled map); P2/run.py for the JSON writer.
"""

import argparse
import json

import matplotlib
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.io_geom import Case, mm_to_idx, load_case
from src.aorta_frame import AortaFrame, build_frame, clock_and_arclen


def write_prediction_json(case_id: str, daughters: list, excluded: list, meta: dict, output_path: str) -> None:
    """Write the required prediction JSON for one case.

    Args:
        case_id: the case identifier string.
        daughters: list of dicts, one per accepted branch, each with
            instance_id, parent_instance_id ("aorta"), ostium_xyz_mm,
            seed_xyz_mm, radius_mm, direction_xyz (unit vector), confidence,
            clock_position (hours), arclen_from_top_mm, takeoff_angle_deg.
            See branchseed_playbook.md §5.10 for the exact schema.
        excluded: list of dicts, each with at least {"reason": str,
            "ostium_xyz_mm": [x, y, z]} (§5.5).
        meta: dict with at least runtime_s, a_med_hu, t_vessel_hu, warnings
            (list of str).
        output_path: path to write the JSON file to.

    Returns:
        None. Always writes a valid JSON file, even when `daughters` and
        `excluded` are empty.
    """
    raise NotImplementedError


def _direction_idx_delta(case: Case, ostium_mm, direction_xyz, length_mm):
    """Voxel-index delta [dz, dy, dx] of an arrow from `ostium_mm` along
    `direction_xyz` for `length_mm`, via `mm_to_idx` (so it is correct on
    any grid, regardless of direction cosines)."""
    start_idx = mm_to_idx(case, ostium_mm)
    end_idx = mm_to_idx(case, np.asarray(ostium_mm) + np.asarray(direction_xyz) * length_mm)
    return end_idx - start_idx


def _draw_mip_panel(ax, mip, mask_proj, points_rc, deltas_rc, title):
    """Draw one MIP panel: image, aorta-mask contour, ostia dots, arrows.

    Args:
        ax: matplotlib axes.
        mip: 2D array, the maximum-intensity projection (HU).
        mask_proj: 2D bool array, the projected aorta mask, same shape.
        points_rc: list of (row, col) marker positions (voxel units).
        deltas_rc: list of (drow, dcol) arrow deltas matching `points_rc`.
        title: panel title.
    """
    ax.imshow(mip, cmap="gray", aspect="equal", vmin=-100, vmax=500)
    if mask_proj.any():
        ax.contour(mask_proj.astype(float), levels=[0.5], colors="cyan", linewidths=1.0)
    for (r, c), (dr, dc) in zip(points_rc, deltas_rc):
        ax.plot(c, r, "o", color="red", markersize=5)
        ax.arrow(c, r, dc, dr, color="yellow", head_width=2.5, length_includes_head=True)
    ax.set_title(title)
    ax.set_xticks([])
    ax.set_yticks([])


def visual_check(case: Case, frame: AortaFrame, daughters: list, output_path: str, cfg: dict) -> None:
    """Render the required per-case verification PNG (§9.1).

    Args:
        case: loaded `Case` (for the CT and aorta mask arrays, [z,y,x]).
        frame: `AortaFrame` for this case (unused directly here beyond the
            aorta mask already on `case`; kept for interface symmetry with
            `unrolled_map` and future wall-surface overlays).
        daughters: list of accepted-branch dicts as in
            `write_prediction_json` (ostium_xyz_mm, direction_xyz, etc.).
        output_path: path to write the PNG to.
        cfg: parsed config. Uses report_axial_half_window_mm (mm) and
            report_arrow_length_mm (mm).

    Returns:
        None. Three panels: coronal MIP, sagittal MIP, and an axial-slice
        strip (one slice per ostium). Must not crash with zero detections.
    """
    half_window_mm = float(cfg["report_axial_half_window_mm"])
    arrow_len_mm = float(cfg["report_arrow_length_mm"])
    iso_mm = float(cfg["iso_mm"])
    half_window_vox = half_window_mm / iso_mm

    ct_np = case.ct_np
    aorta_np = case.aorta_np
    nz, ny, nx = ct_np.shape

    coronal_mip = ct_np.max(axis=1)  # (z, x)
    coronal_mask = aorta_np.max(axis=1)
    sagittal_mip = ct_np.max(axis=2)  # (z, y)
    sagittal_mask = aorta_np.max(axis=2)

    ostium_idx = []  # (z, y, x) per daughter
    arrow_deltas = []  # (dz, dy, dx) per daughter
    for d in daughters:
        idx_zyx = mm_to_idx(case, d["ostium_xyz_mm"])
        ostium_idx.append(idx_zyx)
        arrow_deltas.append(_direction_idx_delta(case, d["ostium_xyz_mm"], d["direction_xyz"], arrow_len_mm))

    n_axial = max(len(daughters), 1)
    fig = plt.figure(figsize=(10, 5 + 3 * n_axial))
    gs = fig.add_gridspec(2, 1, height_ratios=[5, 3 * n_axial])
    top_gs = gs[0].subgridspec(1, 2)
    ax_coronal = fig.add_subplot(top_gs[0, 0])
    ax_sagittal = fig.add_subplot(top_gs[0, 1])

    coronal_points = [(z, x) for z, y, x in ostium_idx]
    coronal_deltas = [(dz, dx) for dz, dy, dx in arrow_deltas]
    _draw_mip_panel(ax_coronal, coronal_mip, coronal_mask, coronal_points, coronal_deltas, "Coronal MIP")

    sagittal_points = [(z, y) for z, y, x in ostium_idx]
    sagittal_deltas = [(dz, dy) for dz, dy, dx in arrow_deltas]
    _draw_mip_panel(ax_sagittal, sagittal_mip, sagittal_mask, sagittal_points, sagittal_deltas, "Sagittal MIP")

    bottom_gs = gs[1].subgridspec(n_axial, 1)
    if not daughters:
        ax = fig.add_subplot(bottom_gs[0, 0])
        ax.text(0.5, 0.5, "No detections", ha="center", va="center")
        ax.set_xticks([])
        ax.set_yticks([])
    else:
        for i, (d, (z, y, x), (dz, dy, dx)) in enumerate(zip(daughters, ostium_idx, arrow_deltas)):
            ax = fig.add_subplot(bottom_gs[i, 0])
            z_idx = int(round(np.clip(z, 0, nz - 1)))
            y_lo = int(np.clip(np.floor(y - half_window_vox), 0, ny))
            y_hi = int(np.clip(np.ceil(y + half_window_vox), 0, ny))
            x_lo = int(np.clip(np.floor(x - half_window_vox), 0, nx))
            x_hi = int(np.clip(np.ceil(x + half_window_vox), 0, nx))
            crop = ct_np[z_idx, y_lo:y_hi, x_lo:x_hi]
            ax.imshow(crop, cmap="gray", aspect="equal", vmin=-100, vmax=500)
            ax.plot(x - x_lo, y - y_lo, "o", color="red", markersize=5)
            ax.arrow(x - x_lo, y - y_lo, dx, dy, color="yellow", head_width=2.5, length_includes_head=True)
            ax.set_title(f"{d['instance_id']} · r={d['radius_mm']:.1f} mm")
            ax.set_xticks([])
            ax.set_yticks([])

    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def unrolled_map(case: Case, frame: AortaFrame, daughters: list, excluded: list, output_path: str, cfg: dict) -> None:
    """Render the unrolled aortic map (§9.2), the clinician-facing view.

    Args:
        case: loaded `Case`.
        frame: `AortaFrame` for this case (for arc length / clock frame).
        daughters: list of accepted-branch dicts (as above).
        excluded: list of excluded-candidate dicts (as above).
        output_path: path to write the PNG to.
        cfg: parsed config. Uses report_marker_min_pt and
            report_marker_scale_pt (marker size = min_pt + scale_pt *
            radius_mm, points).

    Returns:
        None. x-axis: arc length (mm) from the superior end of coverage;
        y-axis: clock position (12 -> 3 -> 6 -> 9 -> 12, 12 = anterior);
        each branch a circle sized by its true radius, annotated with
        instance_id, radius, clock position and takeoff angle; excluded
        candidates as hollow grey markers with their reason.
    """
    min_pt = float(cfg["report_marker_min_pt"])
    scale_pt = float(cfg["report_marker_scale_pt"])

    fig, ax = plt.subplots(figsize=(11, 6))

    ax.axhspan(-0.6, 2.0, color="#fde8d8", zorder=0)
    ax.axhspan(10.0, 12.6, color="#fde8d8", zorder=0)
    ax.axhspan(2.0, 4.0, color="#e6f0fa", zorder=0)
    ax.axhspan(8.0, 10.0, color="#e6f0fa", zorder=0)
    ax.axhspan(4.0, 8.0, color="#eaeaea", zorder=0)

    xs, ys, sizes, labels = [], [], [], []
    for d in daughters:
        arclen = d.get("arclen_from_top_mm")
        clock = d.get("clock_position")
        if arclen is None or clock is None:
            clock, arclen = clock_and_arclen(frame, np.asarray(d["ostium_xyz_mm"]))
        radius_mm = float(d["radius_mm"])
        takeoff = d.get("takeoff_angle_deg")
        xs.append(arclen)
        ys.append(clock % 12.0)
        sizes.append((min_pt + scale_pt * radius_mm) ** 2)
        takeoff_str = f"{takeoff:.0f}°" if takeoff is not None else "n/a"
        labels.append(f"{d['instance_id']} · r={radius_mm:.1f} mm · {arclen:.1f} mm · {clock % 12.0:.1f}h · {takeoff_str}")

    branch_handle = None
    if xs:
        branch_handle = ax.scatter(
            xs, ys, s=sizes, facecolors="tab:red", edgecolors="black", linewidths=1.0, zorder=3,
            label="detected branch",
        )
        for x, y, label in zip(xs, ys, labels):
            # keep annotations for near-the-top points below the marker so they
            # never collide with the title; everything else goes above-right.
            xytext = (6, -12) if y < 0.6 else (6, 6)
            va = "top" if y < 0.6 else "bottom"
            ax.annotate(label, (x, y), textcoords="offset points", xytext=xytext, fontsize=8, va=va)

    ex_xs, ex_ys, ex_labels = [], [], []
    for e in excluded:
        clock, arclen = clock_and_arclen(frame, np.asarray(e["ostium_xyz_mm"]))
        ex_xs.append(arclen)
        ex_ys.append(clock % 12.0)
        ex_labels.append(e.get("reason", "excluded"))
    excluded_handle = None
    if ex_xs:
        excluded_handle = ax.scatter(
            ex_xs, ex_ys, s=60, facecolors="none", edgecolors="grey", zorder=2,
            label="excluded candidate",
        )
        for x, y, label in zip(ex_xs, ex_ys, ex_labels):
            xytext = (6, -12) if y < 0.6 else (6, -10)
            ax.annotate(label, (x, y), textcoords="offset points", xytext=xytext, fontsize=7, color="grey")

    # Small margin above 12 and below 0 keeps per-marker annotations clear of
    # the title and the axis frame; the shaded bands still line up with the
    # true 0-12 clock range since axhspan below is drawn in data coordinates.
    ax.set_ylim(12.6, -0.6)
    ax.set_yticks([0.0, 3.0, 6.0, 9.0, 12.0])
    ax.set_yticklabels(["12", "3", "6", "9", "12"])
    ax.set_ylabel("clock position (12 = anterior)")
    ax.set_xlabel("arc length from superior end (mm)")
    fig.suptitle("Unrolled aortic map", y=0.99, fontsize=13)
    ax.margins(x=0.08)

    # "anterior" wraps around both ends of the clock axis (0h and 12h are the
    # same position), so label both halves of that band, not just one.
    for y, label in (
        (1.0, "anterior"), (3.0, "lateral"), (6.0, "posterior"), (9.0, "lateral"), (11.0, "anterior"),
    ):
        ax.text(
            -0.06,
            y,
            label,
            fontsize=8,
            color="#555555",
            va="center",
            ha="right",
            transform=ax.get_yaxis_transform(),
        )

    handles = [h for h in (branch_handle, excluded_handle) if h is not None]
    if handles:
        # Anchored above the axes (not "upper right" inside the plot) so the
        # legend box never overlaps a marker or its annotation, wherever they
        # land on the map.
        ax.legend(
            handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.02),
            ncol=len(handles), fontsize=8, framealpha=0.9, borderaxespad=0.0,
        )

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.90))
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def _cli_main() -> None:
    """CLI entry point: render one case's §9.1 verification PNG from real
    files, for ad hoc / manual use (`eval/batch.py` is the batch path).

    Usage:
        python -m src.report --image dataset/orig1.nii --mask dataset/mask1.nii \\
            --prediction results/subject001.json --output-png results/subject001_check.png
    """
    parser = argparse.ArgumentParser(description="Render the §9.1 verification PNG for one case.")
    parser.add_argument("--image", required=True, help="Path to the CT volume (.nii or .nii.gz).")
    parser.add_argument("--mask", required=True, help="Path to the binary aorta mask (.nii or .nii.gz).")
    parser.add_argument("--prediction", required=True, help="Path to the prediction JSON (§5.10 schema).")
    parser.add_argument("--output-png", required=True, dest="output_png", help="Path to write the PNG to.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to the YAML config.")
    args = parser.parse_args()

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    case = load_case(args.image, args.mask, cfg)
    frame = build_frame(case, cfg)

    with open(args.prediction, "r") as f:
        prediction = json.load(f)

    visual_check(case, frame, prediction.get("daughters", []), args.output_png, cfg)


if __name__ == "__main__":
    _cli_main()
