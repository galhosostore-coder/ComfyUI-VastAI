#!/bin/bash
set -e

echo "========================================================"
echo "      ComfyUI-VastAI Configurator for Linux/VPS"
echo "========================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    exit 1
fi

echo "[1/3] Installing Dependencies..."
pip install -r requirements.txt --quiet

echo "[2/3] Checking Vast.ai CLI..."
if ! command -v vastai &> /dev/null; then
    echo "[ERROR] Vast.ai CLI not installed."
    exit 1
fi

echo ""
echo "========================================================"
echo "[3/3] Configuration"
echo "========================================================"
echo ""

if [ -z "$VAST_API_KEY" ]; then
    read -p "Enter Vast.ai API Key: " VAST_API_KEY
    if [ ! -z "$VAST_API_KEY" ]; then
        vastai set api-key $VAST_API_KEY
        echo "[OK] API Key set."
    fi
else
    echo "VAST_API_KEY already set in environment."
fi

echo ""
echo "Setup Complete!"
echo "To run a workflow:"
echo "python3 vastai_runner.py --workflow your_workflow.json"
echo ""
