#!/usr/bin/env python3
"""
Vast.ai Runner for ComfyUI - Simplified Google Drive Mode
==========================================================
Just drop models in your Google Drive folder. That's it.

Environment Variables (set in Coolify):
    VAST_API_KEY      - Your Vast.ai API key
    GDRIVE_FOLDER_ID  - Your Google Drive folder ID
    VAST_GPU          - GPU to search for (default: RTX_3090)
    VAST_PRICE        - Max price per hour (default: 0.5)

Usage:
    python vastai_runner.py --workflow workflow.json
    python vastai_runner.py --stop
"""

import argparse
import time
import json
import os
import re
import requests
import sys
import subprocess
from urllib.request import urlretrieve

# ==============================================================================
# Configuration from Environment Variables
# ==============================================================================

def get_env(name, default=None, required=False):
    """Get environment variable with optional default."""
    value = os.getenv(name, default)
    if required and not value:
        print(f"❌ Error: {name} environment variable is required")
        print(f"   Set it in Coolify Environment Variables tab")
        sys.exit(1)
    return value

# ComfyUI paths inside the Vast.ai container
COMFYUI_IMAGE = "yanwk/comfyui-boot:latest"
COMFYUI_PATH = "/app"
MODELS_PATH = f"{COMFYUI_PATH}/models"

# Model directories (ComfyUI standard structure)
MODEL_DIRS = {
    "checkpoints": "checkpoints",
    "loras": "loras",
    "controlnet": "controlnet",
    "vae": "vae",
    "upscale_models": "upscale_models",
    "embeddings": "embeddings",
    "clip": "clip",
    "unet": "unet",
}

# Nodes that load models (class_type -> (model_type, input_key))
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

# ==============================================================================
# Vast.ai CLI Helpers
# ==============================================================================

def check_vast_cli():
    """Check if vastai CLI is installed."""
    try:
        subprocess.run(["vastai", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("❌ 'vastai' CLI not found. Install: pip install vastai")
        sys.exit(1)

def setup_api_key():
    """Setup Vast.ai API key from environment."""
    api_key = get_env("VAST_API_KEY", required=True)
    os.environ["VAST_API_KEY"] = api_key
    subprocess.run(["vastai", "set", "api-key", api_key], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return api_key

def run_vastai(cmd):
    """Run vastai command and return JSON result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except:
        return result.stdout

# ==============================================================================
# Google Drive Integration
# ==============================================================================

def get_gdrive_folder_id():
    """Get Google Drive folder ID from environment."""
    folder_id = get_env("GDRIVE_FOLDER_ID")
    if not folder_id:
        print("⚠️ GDRIVE_FOLDER_ID not set. Models won't be downloaded from GDrive.")
        return None
    return folder_id

def list_gdrive_recursive(folder_id):
    """
    List ALL files in a GDrive folder recursively.
    Returns: { "path/to/file.ext": "file_id" }
    """
    try:
        import gdown
    except ImportError:
        print("⚠️ gdown module not found")
        return {}

    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        # gdown.download_folder with skip_download=True returns a list of file objects
        # We handle the structure assuming recent gdown versions
        files = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
        result = {}
        
        for f in files:
            # f might be an object with .path (relative) and .url (with ID)
            if hasattr(f, 'path') and hasattr(f, 'url'):
                 # Clean path: remove leading ./ or / and backslashes
                 clean_path = f.path.replace('\\', '/').lstrip('./')
                 
                 # Extract ID
                 if 'id=' in f.url:
                     f_id = f.url.split('id=')[-1]
                     result[clean_path] = f_id
            
        return result
    except Exception as e:
        # Fallback/Silent error
        return {}

def list_gdrive_folder(folder_id):
    """Legacy wrapper for compatibility if needed, or simple flat listing."""
    # We redirect to recursive for now as it's more robust
    flat = {}
    recursive = list_gdrive_recursive(folder_id)
    for path, fid in recursive.items():
        filename = path.split('/')[-1]
        flat[filename] = fid
    return flat

def scan_gdrive_models(folder_id):
    """
    Scan GDrive folder and map files to model types based on folder structure.
    """
    models = {}
    
    # 1. Get all files recursively
    print("   ...fetching file list from Google Drive (this may take a moment)...")
    all_files = list_gdrive_recursive(folder_id)
    
    for path, file_id in all_files.items():
        parts = path.split('/')
        filename = parts[-1]
        
        # Determine type
        model_type = None
        
        # A. Check if path starts with a known folder (e.g. "checkpoints/...")
        if len(parts) > 1:
            folder_name = parts[0].lower()
            
            # Map "text_encoders" -> "clip"
            if folder_name == "text_encoders": folder_name = "clip"
            elif folder_name == "diffusion_models": folder_name = "unet"
            
            if folder_name in MODEL_DIRS:
                model_type = MODEL_DIRS[folder_name] # e.g. "checkpoints"
        
        # B. Fallback: Detect by filename
        if not model_type:
            model_type = detect_model_type(filename)
            
        if model_type:
            if model_type not in models:
                models[model_type] = {}
            # We store just the filename mapping because that's what the workflow uses
            # logic: if multiple files have same name, last one wins (warning?)
            models[model_type][filename] = file_id
            
    return models

def scan_gdrive_custom_nodes(folder_id):
    """
    Check if 'custom_nodes.txt' exists in GDrive.
    Returns: file_id or None
    """
    files = list_gdrive_folder(folder_id)
    if not files:
        return None
    
    for filename, file_id in files.items():
        if filename.lower() == "custom_nodes.txt":
            return file_id
    return None

def build_download_script(required_models, gdrive_models, custom_nodes_id=None):
    """Build script to download models and install nodes."""
    commands = [
        "pip install -q gdown",
        "apt-get update && apt-get install -y git" # Ensure git is there
    ]
    
    # 1. Models
    for model_type, filenames in required_models.items():
        gdrive_files = gdrive_models.get(model_type, {})
        dest_dir = f"{MODELS_PATH}/{MODEL_DIRS.get(model_type, model_type)}"
        
        for filename in filenames:
            if filename in gdrive_files:
                file_id = gdrive_files[filename]
                commands.append(f"mkdir -p {dest_dir}")
                # Use -O with explicit filename to handle messy GDrive names
                commands.append(f"gdown -q --id {file_id} -O '{dest_dir}/{filename}'")
                print(f"   📥 Model: {model_type}/{filename}")

    # 2. Custom Nodes (from custom_nodes.txt)
    if custom_nodes_id:
        print(f"   🔧 Found custom_nodes.txt! Adding installation commands...")
        # Download the file to a temp location, read it, then append git clones
        # Note: We can't easily read it locally if we only have the ID and are avoiding auth.
        # Strategy: We tell the remote machine to download it, then iterate through it.
        # But bash scripting that is complex in a one-liner.
        # Better: We download it LOCALLY now (machine running the runner), parse it, 
        # and generate the explicit git clone commands for the remote.
        
        try:
            import gdown
            url = f"https://drive.google.com/uc?id={custom_nodes_id}"
            output = "temp_custom_nodes.txt"
            gdown.download(url, output, quiet=True)
            
            with open(output, 'r', encoding='utf-8') as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            os.remove(output)
            
            nodes_dir = f"{COMFYUI_PATH}/custom_nodes"
            for repo_url in repos:
                repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
                commands.append(f"git clone {repo_url} {nodes_dir}/{repo_name} 2>/dev/null || (cd {nodes_dir}/{repo_name} && git pull)")
                print(f"   🔧 Node: {repo_name}")
                
        except Exception as e:
            print(f"⚠️ Failed to process custom_nodes.txt locally: {e}")

    # 3. Start ComfyUI (Background)
    # We use nohup or just run it. Since this is --onstart-cmd, 
    # it runs effectively in the background of the 'startup' phase but needs to block?
    # VastAI onstart usually runs in a screen or background. 
    # We just run python directly.
    commands.append(f"cd {COMFYUI_PATH} && python main.py --listen 0.0.0.0 --port 8188")
    
    return " && ".join(commands)

def run_workflow(workflow_path, gpu_name, max_price, keep_alive):
    """Main workflow execution."""
    print("=" * 50)
    print("🎨 COMFYUI + GOOGLE DRIVE + VAST.AI")
    print("=" * 50)
    
    # Analyze workflow
    required = analyze_workflow(workflow_path)
    if not required:
        print("No models needed (or could not parse workflow)")
    
    # Get GDrive models
    folder_id = get_gdrive_folder_id()
    gdrive_models = {}
    custom_nodes_id = None
    
    if folder_id:
        print("\n📁 Scanning Google Drive...")
        gdrive_models = scan_gdrive_models(folder_id)
        custom_nodes_id = scan_gdrive_custom_nodes(folder_id)
    
    # Build download script
    print("\n📥 Preparing startup script...")
    startup_script = build_download_script(required, gdrive_models, custom_nodes_id)
    
    # Load workflow
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow_data = json.load(f)
    
    # Find GPU
    offer = search_gpu(gpu_name, max_price)
    if not offer:
        return False
    
    print(f"📦 {offer.get('gpu_name')} @ ${offer['dph_total']}/hr")
    
    # Rent
    instance_id = rent_gpu(offer['id'], startup_script)
    if not instance_id:
        return False
    
    try:
        # Wait (Increase timeout for potential node installs)
        # ... (Rest of function remains same)
        
        # Extra wait for ComfyUI
        print("⏳ ComfyUI initializing...")
        time.sleep(30)
        
        url = get_url(instance)
        print(f"🌐 {url}")
        
        # Queue
        print("📤 Sending workflow...")
        result = queue_prompt(url, workflow_data)
        if not result:
            raise Exception("Queue failed")
        
        prompt_id = result.get('prompt_id')
        print("⏳ Processing...", end="", flush=True)
        
        # Wait for completion
        while True:
            history = get_history(url, prompt_id)
            if history and prompt_id in history:
                print(" ✅")
                
                # Download outputs
                # Save to standard 'output' folder so it persists (if mounted) or is easy to find
                output_dir = "output"
                os.makedirs(output_dir, exist_ok=True)
                outputs = history[prompt_id].get('outputs', {})
                
                for node_id, out in outputs.items():
                    if 'images' in out:
                        for img in out['images']:
                            fn = img['filename']
                            img_url = f"{url}/view?filename={fn}&type={img.get('type','output')}&subfolder={img.get('subfolder','')}"
                            print(f"📥 {fn}")
                            urlretrieve(img_url, f"{output_dir}/{fn}")
                
                break
            
            print(".", end="", flush=True)
            time.sleep(3)
        
        print(f"\n✅ Done! → {output_dir}/")
        
    except KeyboardInterrupt:
        print("\n⚠️ Cancelled")
    except Exception as e:
        print(f"\n❌ {e}")
    finally:
        if not keep_alive:
            destroy(instance_id)
        else:
            print(f"\n⚠️ Instance kept alive: {instance_id}")
    
    return True

# ==============================================================================
# Main
# ==============================================================================

def print_env_help():
    """Print environment variables help."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║         ENVIRONMENT VARIABLES (Set in Coolify)               ║
╠══════════════════════════════════════════════════════════════╣
║  REQUIRED:                                                   ║
║    VAST_API_KEY        Your Vast.ai API key                  ║
║                                                              ║
║  RECOMMENDED:                                                ║
║    GDRIVE_FOLDER_ID    Main Google Drive folder ID           ║
║                        (from the sharing link)               ║
║                                                              ║
║  OPTIONAL:                                                   ║
║    VAST_GPU            GPU to use (default: RTX_3090)        ║
║    VAST_PRICE          Max $/hour (default: 0.5)             ║
╚══════════════════════════════════════════════════════════════╝

Your GDrive Folder ID: 1MoYmMMAf5gpYOEuYNrem4bQjXLqj6VY9

Create these subfolders in your Drive:
  📁 checkpoints/    (SD, SDXL, Flux models)
  📁 loras/          (LoRA files)
  📁 controlnet/     (ControlNet models)
  📁 vae/            (VAE files)
  📁 upscale_models/ (Upscalers)
  📁 embeddings/     (Textual Inversion)

Just drop your models in the right folders. That's it!
""")

def main():
    parser = argparse.ArgumentParser(description="ComfyUI on Vast.ai with Google Drive")
    parser.add_argument("--workflow", help="Workflow JSON file")
    parser.add_argument("--stop", action="store_true", help="Stop all instances")
    parser.add_argument("--env-help", action="store_true", help="Show environment variables help")
    parser.add_argument("--gpu", default=None, help="GPU to use")
    parser.add_argument("--price", type=float, default=None, help="Max price")
    parser.add_argument("--keep-alive", action="store_true", help="Keep instance after run")
    
    args = parser.parse_args()
    
    if args.env_help:
        print_env_help()
        return
    
    # Get config from environment
    gpu = args.gpu or get_env("VAST_GPU", "RTX_3090")
    price = args.price or float(get_env("VAST_PRICE", "0.5"))
    
    setup_api_key()
    check_vast_cli()
    
    if args.stop:
        stop_all()
    elif args.workflow:
        run_workflow(args.workflow, gpu, price, args.keep_alive)
    else:
        parser.print_help()
        print("\n" + "=" * 50)
        print_env_help()

if __name__ == "__main__":
    main()
