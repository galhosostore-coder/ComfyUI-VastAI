FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    wget \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone ComfyUI
RUN git clone https://github.com/Comfy-Org/ComfyUI.git .

# Install Python dependencies (CPU version)
# We copy requirements from the host so we can manage them
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install standard ComfyUI requirements just in case (but we overrode torch above)
RUN pip install --no-cache-dir -r requirements.txt

# Create a volume for output and input to persist data
VOLUME /app/output
VOLUME /app/input
VOLUME /app/user
VOLUME /app/custom_nodes

# Expose the default port
EXPOSE 8188

# Command to run ComfyUI listening on all interfaces (needed for Docker)
CMD ["python", "main.py", "--listen", "0.0.0.0", "--cpu"]
