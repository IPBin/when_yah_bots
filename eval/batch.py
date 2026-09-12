"""
Batch runner (§5.9, §6). Runs the full pipeline over every case in a data
directory, writes predictions, a runtime/memory CSV, and validates schema.
Never lets one case's failure stop the batch.

Owner: P1 + P2.
"""

import argparse


def validate_schema(prediction: dict) -> list:
    """Validate a prediction dict against the required output schema.

    Args:
        prediction: parsed prediction JSON (§5.10).

    Returns:
        list of str, one per schema violation found (empty list if valid).
        Checks: unique instance_id values, parent_instance_id == "aorta" on
        every daughter, unit-length direction_xyz vectors, three finite
        coordinates in ostium_xyz_mm / seed_xyz_mm.
    """
    raise NotImplementedError


def main() -> None:
    """CLI entry point: run the pipeline over every case in a data directory.

    Walks `--data` for `subjectNNN/` folders, runs `run.run_case` on each,
    writes one prediction JSON per case under `--out`, plus a CSV of
    per-case runtime, peak memory, branch count and derived thresholds.
    """
    parser = argparse.ArgumentParser(description="Run branchseed over a directory of cases.")
    parser.add_argument("--data", required=True, help="Directory containing subjectNNN/ case folders.")
    parser.add_argument("--out", required=True, help="Directory to write prediction JSON + CSV to.")
    parser.add_argument("--config", default="config/default.yaml", help="Path to the YAML config.")
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    main()
