#!/usr/bin/env bash
# ==============================================================================
# FLINZA WORKS: 24/7 CLOUD HARVESTER DEPLOYMENT (LINUX VPS / EC2 / DIGITALOCEAN)
# 100% Autonomous — Runs 24/7 Even When Your Laptop Is Completely Turned Off!
# ==============================================================================

set -e

echo "=================================================================="
echo "🚀 DEPLOYING FLINZA TURBO HARVESTER TO 24/7 CLOUD VPS"
echo "=================================================================="

# 1. Update system & install dependencies
echo "[*] Installing system dependencies (Python 3, tmux, curl, dns, git)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv tmux curl wget unzip zip dnsutils

# 2. Setup Python virtual environment
echo "[*] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 3. Install required Python packages (with curl_cffi and async dns)
echo "[*] Installing high-speed scraper libraries..."
pip install --upgrade pip
pip install curl_cffi dnspython aiodns uvloop httpx

# 4. Ensure directories exist
mkdir -p data data/verified_5k data/batch_zips data/raw_extracted

# 5. Check / download 1.9M Shopify Master List if not present
CSV_PATH="data/shopify_master_list.csv"
GZ_PATH="data/shopify_master_list.csv.gz"
GZ_URL="https://raw.githubusercontent.com/growthenginenowoslawski/shopify-master-list/main/shopify_master_list.csv.gz"

if [ ! -f "$CSV_PATH" ] || [ $(wc -c <"$CSV_PATH") -lt 100000000 ]; then
    echo "[*] Downloading 1.9M Shopify Master List (~51 MB compressed)..."
    wget -q --show-progress -O "$GZ_PATH" "$GZ_URL"
    echo "[*] Decompressing to full 1.9M-row CSV..."
    gzip -dc "$GZ_PATH" > "$CSV_PATH"
    echo "[OK] Master database ready: $(ls -lh $CSV_PATH | awk '{print $5}')"
else
    echo "[OK] Master database already present: $(ls -lh $CSV_PATH | awk '{print $5}')"
fi

# 6. Kill previous session if exists
tmux kill-session -t flinza_harvest 2>/dev/null || true

# 7. Launch Harvester inside detached tmux session
echo "[*] Launching 150-worker turbo harvester inside detached tmux session 'flinza_harvest'..."
tmux new-session -d -s flinza_harvest "
    source venv/bin/activate
    python3 -u colab_blitz_harvester.py --concurrency 150 --master-csv $CSV_PATH 2>&1 | tee -a data/harvest_cloud.log
"

echo "=================================================================="
echo "✅ HARVESTER IS NOW RUNNING SAFELY 24/7 IN THE CLOUD!"
echo "   You can now CLOSE THIS TERMINAL and TURN OFF YOUR LAPTOP."
echo "   The scraper will continue harvesting at 150-250 stores/sec."
echo "=================================================================="
echo ""
echo "Useful Commands (whenever you log back in):"
echo "  • View live progress screen: tmux attach -t flinza_harvest"
echo "  • Detach from view:          Press [Ctrl + B] then [D]"
echo "  • View live text logs:       tail -f data/harvest_cloud.log"
echo "  • Stop the harvester:        tmux kill-session -t flinza_harvest"
echo "  • Download your verified zip: Use scp or sftp"
echo "=================================================================="
