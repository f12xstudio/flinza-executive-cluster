import os
import sys
import csv
import json
import time
import subprocess
from config import DATA_DIR

SLICES_DIR = os.path.join(DATA_DIR, "cluster_slices")
VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")
MASTER_VERIFIED_CSV = os.path.join(VERIFIED_DIR, "instantly_master_ultra_verified.csv")

NICHE_FILES = {
    "Jewelry": os.path.join(VERIFIED_DIR, "jewelry_real_inboxes.csv"),
    "Fashion & Apparel": os.path.join(VERIFIED_DIR, "fashion_apparel_real_inboxes.csv"),
    "Fashion Accessories": os.path.join(VERIFIED_DIR, "fashion_accessories_real_inboxes.csv"),
    "Health & Supplements": os.path.join(VERIFIED_DIR, "health_supplements_real_inboxes.csv"),
    "Extended DTC": os.path.join(VERIFIED_DIR, "extended_dtc_real_inboxes.csv")
}

CSV_HEADERS = [
    "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website", "Title",
    "Meta Ads Library URL", "Niche", "Country", "Instagram", "Facebook",
    "LinkedIn", "TikTok", "Twitter_X", "MX_Status", "DMARC_Status",
    "SPF_Status", "Gravatar_Found", "Deliverability_Score", "Personalized Icebreaker"
]

NUM_WORKERS = 10
TARGET_PER_NICHE = 5000
CONCURRENCY_PER_WORKER = 15

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    print("=" * 72, flush=True)
    print(f"[+] LAUNCHING 10-WORKER TURBO CLUSTER ({NUM_WORKERS * CONCURRENCY_PER_WORKER} CONCURRENT REQUESTS)", flush=True)
    print(f"[*] Focused on: Jewelry, Accessories, Supplements, and Apparel (51,890 Stores)", flush=True)
    print("=" * 72, flush=True)

    os.makedirs(VERIFIED_DIR, exist_ok=True)
    for n, fpath in NICHE_FILES.items():
        if not os.path.exists(fpath):
            with open(fpath, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()

    if not os.path.exists(MASTER_VERIFIED_CSV):
        with open(MASTER_VERIFIED_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()

    seen_emails = set()
    niche_counts = {k: 0 for k in NICHE_FILES}

    for niche, fpath in NICHE_FILES.items():
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    em = r.get("Email", "").strip().lower()
                    if em:
                        seen_emails.add(em)
                        niche_counts[niche] += 1

    print(f"[*] Pre-loaded {len(seen_emails):,} existing verified inboxes across niches:")
    for n, cnt in niche_counts.items():
        print(f"    - {n:22}: {cnt:,} leads")

    # Clean old turbo worker outputs and progress files
    for wid in range(NUM_WORKERS):
        out_f = os.path.join(SLICES_DIR, f"turbo_slice_worker_{wid}_verified.csv")
        prog_f = os.path.join(SLICES_DIR, f"turbo_slice_progress_{wid}.json")
        log_f = os.path.join(SLICES_DIR, f"turbo_worker_{wid}.log")
        if os.path.exists(out_f):
            try: os.remove(out_f)
            except Exception: pass
        if os.path.exists(prog_f):
            try: os.remove(prog_f)
            except Exception: pass
        if os.path.exists(log_f):
            try: os.remove(log_f)
            except Exception: pass

    # Launch 10 turbo worker subprocesses
    processes = []
    log_handles = []
    for wid in range(NUM_WORKERS):
        cmd = [
            sys.executable, "-u", "cluster_worker.py",
            "--worker-id", str(wid),
            "--concurrency", str(CONCURRENCY_PER_WORKER),
            "--prefix", "turbo_slice"
        ]
        log_path = os.path.join(SLICES_DIR, f"turbo_worker_{wid}.log")
        lh = open(log_path, "w", encoding="utf-8")
        log_handles.append(lh)
        p = subprocess.Popen(cmd, stdout=lh, stderr=subprocess.STDOUT)
        processes.append((wid, p))
        print(f"[*] Started Turbo Worker {wid} (PID {p.pid})...")
        time.sleep(0.15)

    print(f"\n[+] All 10 Turbo Workers deployed and executing concurrently!\n", flush=True)

    worker_file_positions = {wid: 0 for wid in range(NUM_WORKERS)}
    total_stores = 51890
    start_time = time.time()
    last_print = 0

    while any(p.poll() is None for _, p in processes):
        # 1. Ingest newly verified rows
        for wid in range(NUM_WORKERS):
            out_f = os.path.join(SLICES_DIR, f"turbo_slice_worker_{wid}_verified.csv")
            if os.path.exists(out_f):
                try:
                    with open(out_f, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(worker_file_positions[wid])
                        new_content = f.read()
                        worker_file_positions[wid] = f.tell()

                    if new_content:
                        lines = new_content.strip().split("\n")
                        for line in lines:
                            line = line.strip()
                            if not line or line.startswith("First Name,"):
                                continue
                            parts = list(csv.reader([line]))
                            if not parts:
                                continue
                            row_vals = parts[0]
                            if len(row_vals) < len(CSV_HEADERS):
                                continue
                            rec = dict(zip(CSV_HEADERS, row_vals))
                            em = rec.get("Email", "").strip().lower()
                            if em and em not in seen_emails:
                                seen_emails.add(em)
                                niche = rec.get("Niche", "Extended DTC")
                                if niche in niche_counts:
                                    niche_counts[niche] += 1

                                if niche in NICHE_FILES:
                                    with open(NICHE_FILES[niche], "a", newline="", encoding="utf-8") as nf:
                                        writer = csv.DictWriter(nf, fieldnames=CSV_HEADERS)
                                        writer.writerow(rec)

                                with open(MASTER_VERIFIED_CSV, "a", newline="", encoding="utf-8") as mf:
                                    writer = csv.DictWriter(mf, fieldnames=CSV_HEADERS)
                                    writer.writerow(rec)
                except Exception:
                    pass

        # 2. Collect progress stats every 4 seconds
        now = time.time()
        if now - last_print >= 4.0:
            last_print = now
            total_scanned = 0
            active_workers = 0

            for wid, p in processes:
                if p.poll() is None:
                    active_workers += 1
                prog_file = os.path.join(SLICES_DIR, f"turbo_slice_progress_{wid}.json")
                if os.path.exists(prog_file):
                    try:
                        with open(prog_file, "r", encoding="utf-8") as pf:
                            pdata = json.load(pf)
                            total_scanned += pdata.get("scanned", 0)
                    except Exception:
                        pass

            elapsed = now - start_time
            speed = total_scanned / elapsed if elapsed > 0 else 0
            rem_stores = max(0, total_stores - total_scanned)
            rem_sec = (rem_stores / speed) if speed > 0 else 0
            rem_min = rem_sec / 60

            pct = (total_scanned / total_stores) * 100 if total_stores else 0
            bar_len = 24
            filled = min(bar_len, int(bar_len * (total_scanned / total_stores))) if total_stores else 0
            bar = "=" * filled + "-" * (bar_len - filled)

            total_verified = len(seen_emails)

            print(
                f"[TURBO-CLUSTER] [{bar}] {pct:5.1f}% | "
                f"Scanned: {total_scanned:,}/{total_stores:,} | "
                f"Total Verified: {total_verified:,} | "
                f"Speed: {speed:.1f}/s | "
                f"ETA: {rem_min:.1f}m | "
                f"Workers: {active_workers}/{NUM_WORKERS}",
                flush=True
            )

            niche_line = " | ".join(f"{k.split()[0]}: {v:,}/{TARGET_PER_NICHE:,}" for k, v in niche_counts.items())
            print(f"   --> Niche Targets: {niche_line}\n", flush=True)

            if all(v >= TARGET_PER_NICHE for v in niche_counts.values()):
                print("\n" + "=" * 72, flush=True)
                print("[*** SUCCESS ***] ALL 5 NICHES HIT 5,000+ ULTRA-VERIFIED LEADS!", flush=True)
                print("=" * 72, flush=True)
                for _, p in processes:
                    try: p.terminate()
                    except Exception: pass
                break

        time.sleep(1.0)

    for lh in log_handles:
        try: lh.close()
        except Exception: pass

    print("\n[+] Turbo Cluster run completed!", flush=True)
    print(f"[*] Final Total Verified Inboxes: {len(seen_emails):,}")
    for n, cnt in niche_counts.items():
        print(f"    - {n:22}: {cnt:,} leads")

if __name__ == "__main__":
    main()
