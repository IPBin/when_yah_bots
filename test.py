import argparse
import json
import os
import matplotlib.pyplot as plt
import numpy as np

# SimpleITK is required for proper physical coordinate mapping
import SimpleITK as sitk
from scipy.ndimage import binary_dilation, label
from sklearn.decomposition import PCA


def detect_aortic_branches(image_path: str, mask_path: str) -> dict:
    """Detects direct daughter arteries branching from the supplied parent aorta mask."""
    # Load images with SimpleITK to preserve physical coordinates and directions
    img_sitk = sitk.ReadImage(image_path)
    mask_sitk = sitk.ReadImage(mask_path)

    # Convert to NumPy arrays (Z, Y, X order)
    img_np = sitk.GetArrayFromImage(img_sitk)
    mask_np = sitk.GetArrayFromImage(mask_sitk) > 0

    # 1. Isolate Search Zone (Dilation ring around aortic wall)
    # Exclude cropped volume ends (top and bottom slices) to prevent false end-caps
    struct_elem = np.ones((3, 3, 3), dtype=bool)
    dilated_mask = binary_dilation(mask_np, structure=struct_elem, iterations=3)
    wall_ring = dilated_mask & (~mask_np)

    # Mask out top and bottom z-slices (cropped boundaries)
    wall_ring[0:2, :, :] = False
    wall_ring[-2:, :, :] = False

    # 2. Extract Vessel Brightness & Local Contrast Ring
    # Standard CTA window thresholding for contrast-filled vessels (~150 to 800 HU)
    vessel_mask = (img_np > 150) & wall_ring

    # Connected component analysis to isolate individual candidate daughter origins
    labeled_branches, num_features = label(vessel_mask, structure=struct_elem)

    daughters = []
    branch_count = 1

    for feature_id in range(1, num_features + 1):
        branch_voxels = np.argwhere(labeled_branches == feature_id)

        # Filter out small noise artifacts (minimum physical size criteria)
        if len(branch_voxels) < 15:
            continue

        # --- Ostium Center Calculation ---
        # Physical center of the opening where the daughter leaves the aorta
        mean_voxel_zyx = branch_voxels.mean(axis=0)

        # Convert Z, Y, X array indices to X, Y, Z SimpleITK Index
        ostium_idx = (
            int(round(mean_voxel_zyx[2])),
            int(round(mean_voxel_zyx[1])),
            int(round(mean_voxel_zyx[0])),
        )

        ostium_xyz_mm = img_sitk.TransformIndexToPhysicalPoint(ostium_idx)

        # --- Direction Vector via PCA ---
        # Convert voxel indices to physical coordinates for PCA orientation analysis
        physical_pts = np.array([
            img_sitk.TransformIndexToPhysicalPoint((int(v[2]), int(v[1]), int(v[0])))
            for v in branch_voxels
        ])

        pca = PCA(n_components=3)
        pca.fit(physical_pts)
        direction = pca.components_[0]  # Primary orientation vector

        # Ensure vector points AWAY from the aortic centroid
        aorta_voxels = np.argwhere(mask_np)
        aorta_center_zyx = aorta_voxels.mean(axis=0)
        aorta_center_xyz = img_sitk.TransformIndexToPhysicalPoint((
            int(round(aorta_center_zyx[2])),
            int(round(aorta_center_zyx[1])),
            int(round(aorta_center_zyx[0])),
        ))

        from_aorta_vec = np.array(ostium_xyz_mm) - np.array(aorta_center_xyz)
        if np.dot(direction, from_aorta_vec) < 0:
            direction = -direction  # Flip direction to point outwards

        # Normalize direction vector
        direction_unit = direction / np.linalg.norm(direction)

        # --- Daughter Seed Position (5mm outward along path) ---
        seed_xyz_mm = np.array(ostium_xyz_mm) + (5.0 * direction_unit)

        # --- Local Radius Estimation ---
        # Approximate radius based on maximum cluster spatial dispersion
        distances = np.linalg.norm(physical_pts - np.array(ostium_xyz_mm), axis=1)
        radius_mm = float(np.percentile(distances, 75)) / 2.0
        radius_mm = max(1.0, min(radius_mm, 8.0))  # Bound to realistic anatomical vessel sizes

        daughters.append({
            "instance_id": f"branch_{branch_count:03d}",
            "parent_instance_id": "aorta",
            "ostium_xyz_mm": [round(c, 2) for c in ostium_xyz_mm],
            "seed_xyz_mm": [round(c, 2) for c in seed_xyz_mm.tolist()],
            "radius_mm": round(radius_mm, 2),
            "direction_xyz": [round(d, 3) for d in direction_unit.tolist()],
        })
        branch_count += 1

    return {
        "case_id": os.path.basename(image_path).split(".")[0],
        "parent": {"instance_id": "aorta"},
        "daughters": daughters,
    }


def generate_clinician_visual_check(
    image_path: str, mask_path: str, results: dict, vis_output_path: str
):
    """Generates a clinician-facing visual check plotting CT slice, aorta mask,

    ostia points, and daughter direction vectors.
    """
    img_sitk = sitk.ReadImage(image_path)
    mask_sitk = sitk.ReadImage(mask_path)

    img_np = sitk.GetArrayFromImage(img_sitk)
    mask_np = sitk.GetArrayFromImage(mask_sitk)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        f"Clinician Verification Dashboard — {results['case_id']}",
        fontsize=14,
        fontweight="bold",
    )

    # 1. Axial View (Middle Slice containing branches)
    if results["daughters"]:
        # Find Z index of first detected ostium
        first_ostium_xyz = results["daughters"][0]["ostium_xyz_mm"]
        first_ostium_idx = img_sitk.TransformPhysicalPointToIndex(
            first_ostium_xyz
        )
        z_slice = first_ostium_idx[2]
    else:
        z_slice = img_np.shape[0] // 2

    axes[0].imshow(img_np[z_slice, :, :], cmap="gray", vmin=-100, vmax=400)
    axes[0].contour(mask_np[z_slice, :, :], colors="red", linewidths=1)
    axes[0].set_title(f"Axial Slice (Z={z_slice})")
    axes[0].axis("off")

    # Plot branches on Axial Slice
    for d in results["daughters"]:
        ost_idx = img_sitk.TransformPhysicalPointToIndex(d["ostium_xyz_mm"])
        if abs(ost_idx[2] - z_slice) < 3:  # If close to slice plane
            axes[0].plot(
                ost_idx[0], ost_idx[1], "go", markersize=6, label="Ostium"
            )
            # Plot direction projection
            seed_idx = img_sitk.TransformPhysicalPointToIndex(d["seed_xyz_mm"])
            axes[0].annotate(
                "",
                xy=(seed_idx[0], seed_idx[1]),
                xytext=(ost_idx[0], ost_idx[1]),
                arrowprops=dict(
                    arrowstyle="->", color="cyan", lw=2, mutation_scale=15
                ),
            )

    # 2. Maximum Intensity Projection (MIP) - Coronal View
    mip_coronal = np.max(img_np, axis=1)
    axes[1].imshow(mip_coronal, cmap="bone", vmin=-100, vmax=400)
    axes[1].set_title("Coronal MIP View")
    axes[1].axis("off")

    # 3. Daughter Summary & Clinical Legend
    axes[2].axis("off")
    summary_text = (
        f"Case: {results['case_id']}\n"
        f"Detected Branches: {len(results['daughters'])}\n"
        "-----------------------------------\n"
    )
    for d in results["daughters"]:
        summary_text += (
            f"• {d['instance_id']}: Radius={d['radius_mm']}mm\n"
            f"  Origin: {d['ostium_xyz_mm']}\n"
        )

    axes[2].text(
        0.05,
        0.95,
        summary_text,
        transform=axes[2].transAxes,
        fontsize=10,
        verticalalignment="top",
        family="monospace",
    )

    plt.tight_layout()
    plt.savefig(vis_output_path, dpi=150)
    plt.close()


def main():
    parser = argparse.ArgumentParser(
        description="Branchseed Challenge - Detection of Aortic Branch Origins"
    )
    parser.add_argument(
        "--image",
        type=str,
        required=True,
        help="Path to input CT image (.nii / .nii.gz)",
    )
    parser.add_argument(
        "--aorta-mask",
        type=str,
        required=True,
        help="Path to input parent aorta mask (.nii / .nii.gz)",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Path to output JSON predictions file",
    )
    parser.add_argument(
        "--vis-output",
        type=str,
        default="visual_check.png",
        help="Path to save visual check plot",
    )

    args = parser.parse_args()

    # Process and detect
    results = detect_aortic_branches(args.image, args.aorta-mask)

    # Export structured JSON prediction
    with open(args.output, "w") as f:
        json.dump(results, f, indent=4)

    # Export visual check output for clinician verification
    generate_clinician_visual_check(
        args.image, args.aorta-mask, results, args.vis_output
    )


if __name__ == "__main__":
    main()