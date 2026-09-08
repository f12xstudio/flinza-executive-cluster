import os
import gzip
import time
import subprocess
from config import DATA_DIR

URL = "https://raw.githubusercontent.com/growthenginenowoslawski/shopify-master-list/main/shopify_master_list.csv.gz"
TOTAL_BYTES = 53716578
NUM_CHUNKS = 8

GZ_OUTPUT = os.path.join(DATA_DIR, "shopify_master_list.csv.gz")
CSV_OUTPUT = os.path.join(DATA_DIR, "shopify_master_list.csv")

def download_chunk(idx, start, end, chunk_file):
    cmd = [
        "curl.exe", "--ssl-no-revoke", "-s",
        "-r", f"{start}-{end}",
        "-o", chunk_file,
        URL
    ]
    p = subprocess.Popen(cmd)
    return p

def main():
    print(f"[*] Initiating 8-worker parallel segmented download for 1.9M Shopify Master List ({TOTAL_BYTES / 1024 / 1024:.2f} MB)...", flush=True)
    chunk_size = TOTAL_BYTES // NUM_CHUNKS
    chunk_files = []
    processes = []
    start_time = time.time()

    for i in range(NUM_CHUNKS):
        start = i * chunk_size
        end = (i + 1) * chunk_size - 1 if i < NUM_CHUNKS - 1 else TOTAL_BYTES - 1
        chunk_file = os.path.join(DATA_DIR, f"master_chunk_{i}.tmp")
        chunk_files.append(chunk_file)
        p = download_chunk(i, start, end, chunk_file)
        processes.append((i, p, chunk_file, end - start + 1))

    # Monitor progress
    while any(p.poll() is None for _, p, _, _ in processes):
        downloaded = 0
        for _, _, cf, _ in processes:
            if os.path.exists(cf):
                downloaded += os.path.getsize(cf)
        
        pct = (downloaded / TOTAL_BYTES) * 100
        bar_len = 24
        filled = int(bar_len * (downloaded / TOTAL_BYTES))
        bar = "=" * filled + "-" * (bar_len - filled)
        elapsed = time.time() - start_time
        speed_kb = (downloaded / 1024 / elapsed) if elapsed > 0 else 0
        rem_sec = ((TOTAL_BYTES - downloaded) / 1024 / speed_kb) if speed_kb > 0 else 0

        print(
            f"[{bar}] {pct:5.1f}% | Downloaded: {downloaded / 1024 / 1024:5.1f}/{TOTAL_BYTES / 1024 / 1024:.1f} MB | "
            f"Speed: {speed_kb:.1f} KB/s | ETA: {rem_sec:.1f}s",
            flush=True
        )
        time.sleep(3)

    # Check that all processes finished with code 0
    for i, p, cf, expected_size in processes:
        if p.returncode != 0:
            print(f"[!] Warning: Chunk {i} exited with code {p.returncode}")
        actual_size = os.path.getsize(cf) if os.path.exists(cf) else 0
        print(f"[*] Chunk {i} completed: {actual_size:,}/{expected_size:,} bytes")

    # Combine chunks
    print("[*] Merging 8 chunks into shopify_master_list.csv.gz...", flush=True)
    with open(GZ_OUTPUT, "wb") as f_out:
        for cf in chunk_files:
            with open(cf, "rb") as f_in:
                f_out.write(f_in.read())
            os.remove(cf)

    print(f"[OK] Successfully assembled: {os.path.getsize(GZ_OUTPUT):,} bytes", flush=True)

    # Decompress to CSV
    print("[*] Decompressing gzip archive to full CSV (1.9M rows)...", flush=True)
    decompress_start = time.time()
    total_lines = 0
    with gzip.open(GZ_OUTPUT, "rt", encoding="utf-8", errors="ignore") as f_in:
        with open(CSV_OUTPUT, "w", encoding="utf-8", newline="") as f_out:
            for line in f_in:
                f_out.write(line)
                total_lines += 1
                if total_lines % 250000 == 0:
                    print(f"[*] Decompressed {total_lines:,} rows...", flush=True)

    dec_time = time.time() - decompress_start
    csv_size_mb = os.path.getsize(CSV_OUTPUT) / 1024 / 1024
    print(f"\n[DONE] Successfully extracted {total_lines:,} Shopify stores into {CSV_OUTPUT} ({csv_size_mb:.1f} MB in {dec_time:.1f}s)!", flush=True)

if __name__ == "__main__":
    main()
