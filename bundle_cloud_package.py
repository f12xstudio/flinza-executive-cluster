import os
import zipfile

ZIP_NAME = "flinza_cloud_worker_pack.zip"
INCLUDE_FILES = [
    "launch_cluster.py",
    "cluster_worker.py",
    "cloud_runner.py",
    "clean_and_reclassify_niches.py",
    "email_verifier.py",
    "config.py",
    "normalize_headers.py",
    "prepare_cluster_slices.py",
    "Google_Colab_Lead_Harvest.ipynb",
    "deploy_cloud.sh",
    "Dockerfile",
    "docker-compose.yml",
    "requirements.txt"
]

def main():
    print(f"[*] Packaging standalone cloud deployment bundle into {ZIP_NAME}...")
    with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in INCLUDE_FILES:
            if os.path.exists(f):
                zf.write(f, f)
                print(f"  + Added {f}")

        # Include slices
        slices_dir = os.path.join("data", "cluster_slices")
        if os.path.exists(slices_dir):
            for fname in os.listdir(slices_dir):
                if fname.startswith("slice_") and fname.endswith(".csv"):
                    full_p = os.path.join(slices_dir, fname)
                    arcname = os.path.join("data", "cluster_slices", fname)
                    zf.write(full_p, arcname)
                    print(f"  + Added slice: {arcname}")

        # Include verified files
        v_dir = os.path.join("data", "verified_5k")
        if os.path.exists(v_dir):
            for fname in os.listdir(v_dir):
                if fname.endswith(".csv"):
                    full_p = os.path.join(v_dir, fname)
                    arcname = os.path.join("data", "verified_5k", fname)
                    zf.write(full_p, arcname)
                    print(f"  + Added verified: {arcname}")

    size_mb = os.path.getsize(ZIP_NAME) / (1024 * 1024)
    print(f"\n[OK] Package created: {ZIP_NAME} ({size_mb:.2f} MB)")
    print(f"[*] Turnkey ready for Google Colab, Kaggle, AWS, DigitalOcean, or Docker VPS!")

if __name__ == "__main__":
    main()
