#!/usr/bin/env python3
"""
lazy_model_loader.py
====================
Cloud-side script that runs INSIDE the Vast.ai container.

Strategy:
1. Scan GDrive folder → create 0-byte stub files for ALL models
2. Start ComfyUI (models appear in UI dropdowns)
3. Monitor model load requests → download real file on-demand from GDrive
4. Cache downloaded models for the session duration

This script is meant to be called by the onstart-cmd of the Vast.ai instance.
"""

import os
import sys
import json
import time
import threading
import subprocess
from pathlib import Path

# Paths inside the container
COMFYUI_PATH = "/app"
MODELS_PATH = f"{COMFYUI_PATH}/models"

# Marker for stub files: we use a companion .stub file
STUB_MARKER_EXT = ".stub"

# Model subdirectories
MODEL_SUBDIRS = [
    "checkpoints", "clip", "clip_vision", "configs", "controlnet",
    "diffusers", "diffusion_models", "embeddings", "gligen",
    "hypernetworks", "loras", "model_patches", "style_models",
    "text_encoders", "unet", "upscale_models", "vae", "vae_approx",
    "audio_encoders", "latent_upscale_models", "photomaker",
]


def install_gdown():
    """Ensure gdown is installed."""
    try:
        import gdown
    except ImportError:
        print("[LazyLoader] Installing gdown...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gdown"], check=True)


def scan_gdrive_for_models(folder_id):
    """
    Scan a GDrive folder recursively and return a dict:
    { "subfolder/filename.safetensors": "gdrive_file_id" }
    """
    import gdown

    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        files = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
        result = {}
        for f in files:
            if hasattr(f, 'path') and hasattr(f, 'url'):
                clean_path = f.path.replace('\\', '/').lstrip('./')
                if 'id=' in f.url:
                    f_id = f.url.split('id=')[-1]
                    result[clean_path] = f_id
        return result
    except Exception as e:
        print(f"[LazyLoader] GDrive scan failed: {e}")
        return {}


def create_stubs(gdrive_files):
    """
    Create 0-byte stub files for all models found on GDrive.
    Also create a .stub marker file containing the GDrive file ID.
    Returns: dict mapping local_path -> gdrive_file_id
    """
    stub_map = {}
    created = 0

    for rel_path, file_id in gdrive_files.items():
        # rel_path is like "checkpoints/model.safetensors"
        parts = rel_path.split("/")
        if len(parts) < 2:
            continue

        subfolder = parts[0].lower()
        filename = "/".join(parts[1:])

        # Map common folder name aliases
        folder_aliases = {
            "text_encoders": "clip",
            "diffusion_models": "unet",
        }
        subfolder = folder_aliases.get(subfolder, subfolder)

        if subfolder not in MODEL_SUBDIRS:
            continue

        local_dir = os.path.join(MODELS_PATH, subfolder)
        local_file = os.path.join(local_dir, filename)
        stub_marker = local_file + STUB_MARKER_EXT

        # Skip if real file already exists (from a previous download in this session)
        if os.path.exists(local_file) and os.path.getsize(local_file) > 0:
            if not os.path.exists(stub_marker):
                continue

        # Create directories
        os.makedirs(os.path.dirname(local_file), exist_ok=True)

        # Create 0-byte stub
        with open(local_file, 'wb') as f:
            pass  # 0 bytes

        # Create marker with the GDrive ID
        with open(stub_marker, 'w') as f:
            f.write(file_id)

        stub_map[local_file] = file_id
        created += 1

    print(f"[LazyLoader] Created {created} stub files across model directories")
    return stub_map


def download_model(local_path, file_id):
    """
    Download a real model file from GDrive, replacing the stub.
    """
    import gdown

    stub_marker = local_path + STUB_MARKER_EXT
    filename = os.path.basename(local_path)
    size_before = os.path.getsize(local_path) if os.path.exists(local_path) else 0

    # Skip if already downloaded (not a stub)
    if size_before > 0 and not os.path.exists(stub_marker):
        print(f"[LazyLoader] {filename} already downloaded, skipping")
        return True

    print(f"[LazyLoader] ⬇️  Downloading: {filename} (ID: {file_id})")
    start = time.time()

    try:
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, local_path, quiet=False)

        elapsed = time.time() - start
        size_mb = os.path.getsize(local_path) / (1024 * 1024)
        speed = size_mb / elapsed if elapsed > 0 else 0

        print(f"[LazyLoader] ✅ {filename}: {size_mb:.0f}MB in {elapsed:.1f}s ({speed:.1f} MB/s)")

        # Remove stub marker
        if os.path.exists(stub_marker):
            os.remove(stub_marker)

        return True
    except Exception as e:
        print(f"[LazyLoader] ❌ Failed to download {filename}: {e}")
        return False


def is_stub(filepath):
    """Check if a model file is a stub (has companion .stub marker)."""
    return os.path.exists(filepath + STUB_MARKER_EXT)


def resolve_stubs_for_workflow(workflow_path, stub_map):
    """
    Parse a ComfyUI workflow JSON and download only the models it needs.
    """
    # Node types that reference models
    MODEL_NODES = {
        "CheckpointLoaderSimple": ("checkpoints", "ckpt_name"),
        "CheckpointLoader": ("checkpoints", "ckpt_name"),
        "LoraLoader": ("loras", "lora_name"),
        "LoraLoaderModelOnly": ("loras", "lora_name"),
        "VAELoader": ("vae", "vae_name"),
        "ControlNetLoader": ("controlnet", "control_net_name"),
        "UpscaleModelLoader": ("upscale_models", "model_name"),
        "CLIPLoader": ("clip", "clip_name"),
        "UNETLoader": ("unet", "unet_name"),
        "DualCLIPLoader": ("clip", "clip_name1"),
    }

    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
    except Exception as e:
        print(f"[LazyLoader] Cannot parse workflow: {e}")
        return

    needed_models = set()

    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if class_type in MODEL_NODES:
            model_type, key = MODEL_NODES[class_type]
            name = inputs.get(key)
            if name and isinstance(name, str):
                local_path = os.path.join(MODELS_PATH, model_type, name)
                needed_models.add(local_path)

        # DualCLIPLoader has two clip inputs
        if class_type == "DualCLIPLoader":
            for k in ["clip_name1", "clip_name2"]:
                name = inputs.get(k)
                if name:
                    local_path = os.path.join(MODELS_PATH, "clip", name)
                    needed_models.add(local_path)

    print(f"[LazyLoader] Workflow needs {len(needed_models)} model(s)")

    for model_path in needed_models:
        if is_stub(model_path):
            stub_marker = model_path + STUB_MARKER_EXT
            with open(stub_marker, 'r') as f:
                file_id = f.read().strip()
            download_model(model_path, file_id)
        elif os.path.exists(model_path):
            print(f"[LazyLoader] ✅ {os.path.basename(model_path)} already available")
        else:
            print(f"[LazyLoader] ⚠️  {os.path.basename(model_path)} not found on Drive")


def start_model_watcher(stub_map):
    """
    Background thread that watches for model file access.
    When ComfyUI tries to load a stub, this intercepts and downloads the real file.
    
    Strategy: poll model directories for .stub files. If a .stub exists but someone 
    is trying to read the main file (detected via inotify or polling), download it.
    
    Simpler approach: We hook into ComfyUI's execution by monitoring the API.
    When a prompt is queued, we parse it and pre-download needed models BEFORE execution.
    """
    print("[LazyLoader] 🔍 Starting model watcher (API monitor)...")

    comfyui_url = "http://127.0.0.1:8188"
    last_queue_remaining = 0

    while True:
        try:
            # Poll the ComfyUI API for queued prompts
            resp = requests.get(f"{comfyui_url}/queue", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                pending = data.get("queue_pending", [])

                if pending and len(pending) > last_queue_remaining:
                    # New prompt queued! Parse it and download needed models
                    for item in pending:
                        if len(item) >= 3:
                            prompt_data = item[2]  # The actual prompt/workflow
                            if isinstance(prompt_data, dict):
                                # Download needed models before ComfyUI tries to load them
                                resolve_stubs_for_prompt(prompt_data, stub_map)

                last_queue_remaining = len(pending)

        except Exception:
            pass  # ComfyUI not ready yet or request failed

        time.sleep(2)  # Poll every 2 seconds


def resolve_stubs_for_prompt(prompt_data, stub_map):
    """Resolve stubs needed by a queued prompt (already parsed JSON)."""
    MODEL_NODES = {
        "CheckpointLoaderSimple": ("checkpoints", "ckpt_name"),
        "CheckpointLoader": ("checkpoints", "ckpt_name"),
        "LoraLoader": ("loras", "lora_name"),
        "LoraLoaderModelOnly": ("loras", "lora_name"),
        "VAELoader": ("vae", "vae_name"),
        "ControlNetLoader": ("controlnet", "control_net_name"),
        "UpscaleModelLoader": ("upscale_models", "model_name"),
        "CLIPLoader": ("clip", "clip_name"),
        "UNETLoader": ("unet", "unet_name"),
        "DualCLIPLoader": ("clip", "clip_name1"),
    }

    for node_id, node in prompt_data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})

        keys_to_check = []
        if class_type in MODEL_NODES:
            model_type, key = MODEL_NODES[class_type]
            keys_to_check.append((model_type, key))

        if class_type == "DualCLIPLoader":
            keys_to_check.append(("clip", "clip_name2"))

        for model_type, key in keys_to_check:
            name = inputs.get(key)
            if name and isinstance(name, str):
                local_path = os.path.join(MODELS_PATH, model_type, name)
                if is_stub(local_path):
                    stub_marker = local_path + STUB_MARKER_EXT
                    try:
                        with open(stub_marker, 'r') as f:
                            file_id = f.read().strip()
                        download_model(local_path, file_id)
                    except Exception as e:
                        print(f"[LazyLoader] Error resolving {name}: {e}")


def main():
    """
    Main entry point. Called as part of the container's onstart-cmd.
    
    Usage: python lazy_model_loader.py <gdrive_folder_id>
    """
    import requests as req
    global requests
    requests = req

    if len(sys.argv) < 2:
        print("[LazyLoader] Usage: python lazy_model_loader.py <gdrive_folder_id>")
        sys.exit(1)

    folder_id = sys.argv[1]

    print("=" * 60)
    print("[LazyLoader] 🚀 Initializing Smart Model Loading")
    print("=" * 60)

    # Step 1: Install dependencies
    install_gdown()

    # Step 2: Scan GDrive
    print(f"\n[LazyLoader] 📂 Scanning GDrive folder: {folder_id}")
    gdrive_files = scan_gdrive_for_models(folder_id)
    print(f"[LazyLoader] Found {len(gdrive_files)} files on Drive")

    # Step 3: Create stubs
    print(f"\n[LazyLoader] 📋 Creating stub files...")
    stub_map = create_stubs(gdrive_files)

    # Step 4: Start ComfyUI in background
    print(f"\n[LazyLoader] 🖥️  Starting ComfyUI...")
    comfyui_proc = subprocess.Popen(
        [sys.executable, "main.py", "--listen", "0.0.0.0", "--port", "8188"],
        cwd=COMFYUI_PATH
    )

    # Step 5: Start watcher (monitors API for queued prompts)
    print(f"\n[LazyLoader] 👁️  Starting model watcher...")
    watcher = threading.Thread(target=start_model_watcher, args=(stub_map,), daemon=True)
    watcher.start()

    # Step 6: Wait for ComfyUI process
    print(f"\n[LazyLoader] ✅ System ready! Models will download on-demand.")
    print("=" * 60)

    try:
        comfyui_proc.wait()
    except KeyboardInterrupt:
        print("\n[LazyLoader] Shutting down...")
        comfyui_proc.terminate()


if __name__ == "__main__":
    main()
