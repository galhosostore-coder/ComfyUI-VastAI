# Tuned Dockerfile for Coolify (CPU Mode)
# Based on standard python:3.10-slim for stability and low footprint

FROM python:3.10-slim

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for ComfyUI and common nodes
# Tuned: Added ffmpeg, libgl1, libglib2.0 for image/video processing nodes
RUN apt-get update && apt-get install -y \
    git \
    wget \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the official ComfyUI repository
# Tuned: Fetches the latest master branch
RUN git clone https://github.com/Comfy-Org/ComfyUI.git .

# Install PyTorch for CPU (Lightweight)
# Tuned: Explicitly install the CPU version to save space and avoid CUDA errors on Contabo
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install ComfyUI dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install extra dependencies for our Vast.ai runner script
# Tuned: Allows running the vastai automation directly from this container if needed
COPY requirements.txt /tmp/custom_requirements.txt
RUN pip install --no-cache-dir -r /tmp/custom_requirements.txt && \
    pip install --no-cache-dir gdown

# Copy our custom scripts
COPY vastai_runner.py /app/vastai_runner.py
COPY sync_models.py /app/sync_models.py

# Copy internal Custom Node for Sync
COPY custom_nodes/ComfyUI-GDrive-Sync /app/custom_nodes/ComfyUI-GDrive-Sync

# Install ComfyUI-Manager (Standard Manager)
RUN git clone https://github.com/Comfy-Org/ComfyUI-Manager.git /app/custom_nodes/ComfyUI-Manager

# Create storage directories
# Tuned: Setup volumes for Coolify persistence
VOLUME /app/input
VOLUME /app/output
VOLUME /app/user
VOLUME /app/custom_nodes
VOLUME /app/models

# Expose port
EXPOSE 8188

# Start Sync + ComfyUI
# Tuned: Runs sync_models.py (if gdrive configured) before starting ComfyUI
CMD sh -c "python sync_models.py; python main.py --listen 0.0.0.0 --port 8188 --cpu"
