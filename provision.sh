#!/bin/bash
# provision.sh — Provisioning script for vastai/comfy template
# ============================================================
# This runs automatically inside the container via PROVISIONING_SCRIPT env var.
# It installs gdown and launches our lazy model loader for on-demand GDrive models.
#
# Usage (set as env var in Vast.ai):
#   PROVISIONING_SCRIPT=https://raw.githubusercontent.com/galhosostore-coder/ComfyUI-VastAI/main/provision.sh

set -e

COMFY_DIR="/workspace/ComfyUI"
LOADER_URL="https://raw.githubusercontent.com/galhosostore-coder/ComfyUI-VastAI/main/lazy_model_loader.py"
GDRIVE_FOLDER_ID="${GDRIVE_FOLDER_ID:-}"

echo "=============================================="
echo "[Provision] ComfyUI-VastAI Provisioning Script"
echo "=============================================="

# Wait for ComfyUI directory to exist (vastai/comfy creates it)
for i in $(seq 1 30); do
    if [ -d "$COMFY_DIR" ]; then
        break
    fi
    echo "[Provision] Waiting for $COMFY_DIR... ($i/30)"
    sleep 2
done

if [ ! -d "$COMFY_DIR" ]; then
    echo "[Provision] ERROR: $COMFY_DIR not found after 60s"
    exit 1
fi

echo "[Provision] ComfyUI found at $COMFY_DIR"

# Install dependencies
pip install -q gdown requests 2>/dev/null || true

# Download our lazy model loader
echo "[Provision] Downloading lazy_model_loader.py..."
curl -sL "$LOADER_URL" -o "$COMFY_DIR/lazy_model_loader.py"

if [ -z "$GDRIVE_FOLDER_ID" ]; then
    echo "[Provision] No GDRIVE_FOLDER_ID set. Skipping model loader."
    echo "[Provision] ComfyUI will start with default models only."
    exit 0
fi

echo "[Provision] Starting lazy model loader with folder: $GDRIVE_FOLDER_ID"
cd "$COMFY_DIR"
python3 lazy_model_loader.py "$GDRIVE_FOLDER_ID" &

echo "[Provision] Done! Model loader running in background."
