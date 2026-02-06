#!/bin/bash
set -e

# Detect OS
OS="$(uname -s)"
echo "========================================================"
echo "      ComfyUI-VastAI Configurator for $OS"
echo "========================================================"
echo ""

# 1. Python Check
# MacOS often has 'python3' command
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] python3 could not be found. Please install Python."
    if [ "$OS" = "Darwin" ]; then
        echo "Tip: brew install python"
    fi
    exit 1
fi

echo "[1/4] Setting up Virtual Environment (.venv)..."
if [ ! -d ".venv" ]; then
    $PYTHON_CMD -m venv .venv
    echo "      .venv created."
else
    echo "      .venv exists."
fi

# Activate venv
source .venv/bin/activate

echo "[2/4] Installing Dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "[3/4] Checking Vast.ai CLI..."
if ! command -v vastai &> /dev/null; then
    echo "[ERROR] Vast.ai CLI installation failed."
    exit 1
fi

echo ""
echo "========================================================"
echo "[4/4] Configuration"
echo "========================================================"
echo ""

if [ -z "$VAST_API_KEY" ]; then
    # Try to read from existing config if possible or just ask
    echo "Please enter your Vast.ai API Key (Press Enter to skip if already done):"
    read -p "API Key: " USER_KEY
    if [ ! -z "$USER_KEY" ]; then
        vastai set api-key $USER_KEY
        echo "[OK] API Key set."
    fi
else
    echo "VAST_API_KEY detected in environment."
fi

# Create a helper runner script
echo "#!/bin/bash" > run.sh
echo "source .venv/bin/activate" >> run.sh
echo "$PYTHON_CMD vastai_runner.py \"\$@\"" >> run.sh
chmod +x run.sh

echo ""
echo "✅ Setup Complete!"
echo ""
echo "To run a workflow:"
echo "  ./run.sh --workflow examples/simple_txt2img.json"
echo ""
