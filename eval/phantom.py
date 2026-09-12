"""
Synthetic phantom generator (§8.2). Produces a CTA-like NIfTI volume plus its
exact reference JSON, with caller-specified branch geometry, spacing and
direction cosines (to regression-test coordinate handling on anisotropic /
rotated grids).

Owner: P3.
"""


def make_phantom(
    branches: list,
    spacing=(1.0, 1.0, 1.0),
    direction=None,
    shape=(160, 160, 160),
    include_spine=False,
    include_calcification=False,
    include_vein=False,
    fork_branch=False,
):
    """Generate a synthetic CTA phantom and its exact reference JSON.

    Args:
        branches: list of dicts, each specifying a branch cylinder with keys
            such as position_mm, direction_xyz (unit vector), radius_mm,
            length_mm.
        spacing: (sx, sy, sz) mm per voxel (SimpleITK order) of the output
            grid. Use anisotropic values (e.g. (0.7, 0.7, 2.0)) to test
            coordinate-handling robustness.
        direction: optional 3x3 direction cosine matrix (row-major, flattened
            length-9 sequence) for the output SimpleITK image. None means
            identity.
        shape: (nx, ny, nz) voxel grid size (SimpleITK order).
        include_spine: add a 700 HU slab 25 mm posterior to the aorta.
        include_calcification: add a 900 HU, 2 mm radius sphere in the
            aortic wall.
        include_vein: add a dimmer (120 HU) parallel cylinder.
        fork_branch: make one branch fork into two at 7 mm from its ostium.

    Returns:
        (ct_image, aorta_mask_image, reference): SimpleITK images (HU int16,
        uint8 mask) on the given grid, background 40 HU, a vertical aorta
        cylinder (radius 10 mm, 350 HU) plus its own mask, the requested
        branch cylinders (320 HU), a 0.8 mm Gaussian blur and 15 HU Gaussian
        noise; and `reference`, a dict in the exact §5.10 output schema with
        ostium_xyz_mm on the aortic surface, seed_xyz_mm at 5 mm along the
        branch axis, true radius_mm and true unit direction_xyz, all
        computed via TransformContinuousIndexToPhysicalPoint so they share
        the same physical frame as the generated images.
    """
    raise NotImplementedError
