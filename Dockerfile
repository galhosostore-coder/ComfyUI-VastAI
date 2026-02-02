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
RUN pip install --no-cache-dir -r /tmp/custom_requirements.txt

# Create storage directories
# Tuned: Setup volumes for Coolify persistence
VOLUME /app/input
VOLUME /app/output
VOLUME /app/user
VOLUME /app/custom_nodes
VOLUME /app/models

# Expose port
EXPOSE 8188

# Start ComfyUI in CPU mode and listen on all interfaces
# Tuned: "--cpu" flag forces CPU mode even if standard torch is present (safety)
CMD ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu"]

