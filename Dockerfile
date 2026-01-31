# ComfyUI CPU-only Dockerfile
# Baseado em Python oficial para máxima compatibilidade

FROM python:3.11-slim-bookworm

LABEL maintainer="ComfyUI-VastAI"
LABEL description="ComfyUI CPU-only for workflow design"

# Evitar prompts interativos
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Criar usuário não-root
RUN useradd -m -u 1000 comfy
WORKDIR /app

# Clonar ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app \
    && chown -R comfy:comfy /app

# Instalar dependências Python (CPU-only - sem CUDA)
RUN pip install --upgrade pip && \
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# Criar diretórios para dados
RUN mkdir -p /app/output /app/input /app/user /app/custom_nodes \
    && chown -R comfy:comfy /app

# Mudar para usuário não-root
USER comfy

# Porta padrão do ComfyUI
EXPOSE 8188

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8188/ || exit 1

# Comando padrão
CMD ["python", "main.py", "--cpu", "--listen", "0.0.0.0", "--preview-method", "auto"]
