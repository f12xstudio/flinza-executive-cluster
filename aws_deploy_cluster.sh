#!/usr/bin/env bash
# ==============================================================================
# FLINZA CLUSTER AWS SPOT DEPLOYER (Consume AWS Credits)
# ==============================================================================
# Usage: ./aws_deploy_cluster.sh <SLICE_ID> <TOTAL_SLICES>
# Example: ./aws_deploy_cluster.sh 0 25
# ==============================================================================
set -e

SLICE_ID=${1:-0}
TOTAL_SLICES=${2:-25}
CONCURRENCY=${3:-100}

echo "===================================================================="
echo "🚀 LAUNCHING FLINZA AWS NODE: Slice $SLICE_ID of $TOTAL_SLICES"
echo "===================================================================="

# 1. Update OS & install Python / libcurl dependencies
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv git wget curl zip unzip libcurl4-openssl-dev

# 2. Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install curl_cffi dnspython aiodns uvloop httpx pandas

# 3. Create data directories
mkdir -p data/verified_5k data/batch_zips data/raw_extracted

# 4. Download 1.9M master list
GZ_URL="https://raw.githubusercontent.com/growthenginenowoslawski/shopify-master-list/main/shopify_master_list.csv.gz"
if [ ! -f data/shopify_master_list.csv ]; then
    echo "[*] Downloading 1.9M Shopify Master List..."
    wget -q --show-progress -O data/shopify_master_list.csv.gz "$GZ_URL"
    gzip -dc data/shopify_master_list.csv.gz > data/shopify_master_list.csv
fi

# 5. Run Harvester Node
export TELEGRAM_BOT_TOKEN="8942730693:AAG9ERn1JgXInKiR_9MZJI3HPxCkjKvVtpE"
export TELEGRAM_CHAT_ID="6642913680"
export FLINZA_DATA_DIR="$(pwd)/data"

python -u colab_blitz_harvester.py \
    --slice-id "$SLICE_ID" \
    --total-slices "$TOTAL_SLICES" \
    --concurrency "$CONCURRENCY" \
    --batch-size 25000 \
    --master-csv data/shopify_master_list.csv

echo "✅ Node $SLICE_ID Complete!"
