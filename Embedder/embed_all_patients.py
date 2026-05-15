"""
scripts/embed_all_patients.py
=============================
Run this ONCE before starting the system.
Embeds all patient EHR and anamnesis files and saves indexes to disk.

Usage:
    python scripts/embed_all_patients.py
"""

import os
import logging

from Embedder.embedder import Embedder
from Embedder.embedder_config import BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


def embed_all_patients(patients_dir: str = os.path.join(BASE_DIR, "data", "patients")) -> None:
    """
    Walks through all patient folders and embeds
    both ehr.json and anamnesis.json for each.

    Skips if already cached and unchanged.

    IN:
        patients_dir → path to patients folder
    OUT:
        None → indexes saved to disk per patient
    """

    # Check patients directory exists
    if not os.path.exists(patients_dir):
        logger.error(f"Patients directory not found: {patients_dir}")
        return

    # Get all patient folders
    patient_folders = sorted([
        f for f in os.listdir(patients_dir)
        if os.path.isdir(os.path.join(patients_dir, f))
    ])

    if not patient_folders:
        logger.warning("No patient folders found")
        return

    logger.info(f"Found {len(patient_folders)} patients: {patient_folders}")

    # Track results
    results = {
        "success": [],
        "skipped": [],
        "failed":  [],
    }

    # Loop through each patient
    for patient_id in patient_folders:
        info_dir = os.path.join(patients_dir, patient_id, "information")

        if not os.path.exists(info_dir):
            logger.warning(f"{patient_id}: No information/ folder found — skipping")
            results["skipped"].append(patient_id)
            continue

        # Embed both files
        for data_type in ["ehr", "anamnesis"]:
            file_path = os.path.join(info_dir, f"{data_type}.json")

            if not os.path.exists(file_path):
                logger.warning(f"{patient_id}: {data_type}.json not found — skipping")
                results["skipped"].append(f"{patient_id}/{data_type}")
                continue

            logger.info(f"Processing {patient_id}/{data_type}...")

            index, chunk_map = Embedder.embed_patient_file(file_path)

            if index is not None and chunk_map:
                logger.info(f"✓ {patient_id}/{data_type} → {len(chunk_map)} chunks")
                results["success"].append(f"{patient_id}/{data_type}")
            else:
                logger.error(f"✗ {patient_id}/{data_type} → failed")
                results["failed"].append(f"{patient_id}/{data_type}")

    # Print summary
    print("\n" + "=" * 50)
    print("EMBEDDING COMPLETE")
    print("=" * 50)
    print(f"✓ Success : {len(results['success'])}")
    print(f"⚠ Skipped : {len(results['skipped'])}")
    print(f"✗ Failed  : {len(results['failed'])}")

    if results["failed"]:
        print(f"\nFailed files:")
        for f in results["failed"]:
            print(f"  - {f}")

    print("=" * 50)


if __name__ == "__main__":
    embed_all_patients()