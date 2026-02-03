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

def list_gdrive_folder(folder_id):
    """
    List files in a public Google Drive folder using gdown.
    Returns dict: {filename: file_id}
    """
    try:
        import gdown
    except ImportError:
        return {}
    
    # gdown can list folder contents
    # Format: https://drive.google.com/drive/folders/FOLDER_ID
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    
    try:
        # This returns list of (id, name, is_folder)
        files = gdown.download_folder(url, skip_download=True, quiet=True)
        if files:
            return {f[1]: f[0] for f in files if not f[2]}  # name: id, skip folders
    except:
        pass
    
    return {}

def scan_gdrive_models(folder_id):
    """
    Scan the GDrive folder structure for models.
    Expected structure:
        /checkpoints/model.safetensors
        /loras/lora.safetensors
        etc.
    
    Returns: {model_type: {filename: gdrive_id}}
    """
    models = {}
    
    # First, list the main folder to find subfolders
    # We'll use the folder IDs from environment if provided
    for model_type in MODEL_DIRS.keys():
        subfolder_id = get_env(f"GDRIVE_{model_type.upper()}_FOLDER_ID")
        if subfolder_id:
            files = list_gdrive_folder(subfolder_id)
            if files:
                models[model_type] = files
    
    # If no subfolder IDs, try to scan the main folder
    if not models and folder_id:
        # User might have put files directly or in subfolders
        # For simplicity, we'll just use the main folder
        files = list_gdrive_folder(folder_id)
        if files:
            # Try to categorize by extension/name
            for filename, file_id in files.items():
                model_type = detect_model_type(filename)
                if model_type not in models:
                    models[model_type] = {}
                models[model_type][filename] = file_id
    
    return models

def detect_model_type(filename):
    """Detect model type from filename."""
    fn = filename.lower()
    
    if "lora" in fn:
        return "loras"
    elif "controlnet" in fn or "control_" in fn:
        return "controlnet"
    elif "vae" in fn:
        return "vae"
    elif "upscale" in fn or "esrgan" in fn:
        return "upscale_models"
    elif "embed" in fn:
        return "embeddings"
    elif "clip" in fn:
        return "clip"
    elif "unet" in fn:
        return "unet"
    else:
        return "checkpoints"  # Default

# ==============================================================================
# Workflow Analysis
# ==============================================================================

def analyze_workflow(workflow_path):
    """Find all models required by a workflow."""
    print(f"📋 Analyzing: {workflow_path}")
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    required = {}
    
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        
        if class_type in MODEL_NODES:
            model_type, key = MODEL_NODES[class_type]
            name = inputs.get(key)
            if name:
                if model_type not in required:
                    required[model_type] = set()
                required[model_type].add(name)
        
        # DualCLIPLoader has two inputs
        if class_type == "DualCLIPLoader":
            for k in ["clip_name1", "clip_name2"]:
                name = inputs.get(k)
                if name:
                    if "clip" not in required:
                        required["clip"] = set()
                    required["clip"].add(name)
    
    # Convert sets to lists
    for t in required:
        required[t] = list(required[t])
    
    print("\n📦 Required models:")
    for t, models in required.items():
        for m in models:
            print(f"   {t}/{m}")
    
    return required

# ==============================================================================
# Instance Management
# ==============================================================================

def search_gpu(gpu_name, max_price):
    """Search for available GPU."""
    print(f"🔍 Searching: {gpu_name} (max ${max_price}/hr)")
    
    cmd = [
        "vastai", "search", "offers",
        f"gpu_name={gpu_name} rented=False reliability>0.95 verified=True",
        "-o", "price_usd", "--raw"
    ]
    
    offers = run_vastai(cmd)
    if not offers:
        return None
    
    valid = [o for o in offers if float(o['dph_total']) <= max_price]
    if not valid:
        print(f"❌ No {gpu_name} found under ${max_price}/hr")
        return None
    
    return valid[0]

def build_download_script(required_models, gdrive_models):
    """Build script to download required models from GDrive."""
    commands = ["pip install -q gdown"]
    
    for model_type, filenames in required_models.items():
        gdrive_files = gdrive_models.get(model_type, {})
        dest_dir = f"{MODELS_PATH}/{MODEL_DIRS.get(model_type, model_type)}"
        
        for filename in filenames:
            if filename in gdrive_files:
                file_id = gdrive_files[filename]
                commands.append(f"mkdir -p {dest_dir}")
                commands.append(f"gdown -q --id {file_id} -O {dest_dir}/{filename}")
                print(f"   📥 {model_type}/{filename}")
    
    # Start ComfyUI
    commands.append(f"cd {COMFYUI_PATH} && python main.py --listen 0.0.0.0 --port 8188")
    
    return " && ".join(commands)

def rent_gpu(offer_id, startup_script):
    """Rent a GPU instance."""
    print("💰 Renting GPU...")
    
    cmd = [
        "vastai", "create", "instance", str(offer_id),
        "--image", COMFYUI_IMAGE,
        "--disk", "20",
        "--onstart-cmd", startup_script,
        "--raw"
    ]
    
    result = run_vastai(cmd)
    if not result:
        return None
    
    instance_id = result.get('new_contract')
    print(f"✅ Rented! ID: {instance_id}")
    return instance_id

def wait_for_ready(instance_id, timeout=900):
    """Wait for instance to be ready."""
    print("⏳ Starting (downloading models)...", end="", flush=True)
    start = time.time()
    
    while time.time() - start < timeout:
        instances = run_vastai(["vastai", "show", "instances", "--raw"])
        if instances:
            inst = next((i for i in instances if i['id'] == instance_id), None)
            if inst and inst.get('actual_status') == 'running' and inst.get('ports'):
                print(" ✅ Ready!")
                return inst
        
        print(".", end="", flush=True)
        time.sleep(10)
    
    print(" ❌ Timeout")
    return None

def get_url(instance):
    """Get ComfyUI URL from instance."""
    ports = instance.get('ports', {})
    if '8188/tcp' in ports:
        p = ports['8188/tcp'][0]
        return f"http://{p['HostIp']}:{p['HostPort']}"
    return None

def destroy(instance_id):
    """Destroy instance."""
    print(f"🗑️ Destroying {instance_id}...")
    subprocess.run(["vastai", "destroy", "instance", str(instance_id)])
    print("✅ Stopped billing.")

def stop_all():
    """Stop all running instances."""
    instances = run_vastai(["vastai", "show", "instances", "--raw"])
    if not instances:
        print("No instances.")
        return
    
    running = [i for i in instances if i.get('actual_status') == 'running']
    if not running:
        print("No running instances.")
        return
    
    for i in running:
        print(f"   {i['id']}: {i.get('gpu_name')} ${i.get('dph_total')}/hr")
    
    if input("Destroy all? [y/N]: ").lower() == 'y':
        for i in running:
            destroy(i['id'])

# ==============================================================================
# Workflow Execution
# ==============================================================================

def queue_prompt(url, workflow):
    """Send workflow to ComfyUI."""
    try:
        r = requests.post(f"{url}/prompt", json={"prompt": workflow}, timeout=30)
        return r.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_history(url, prompt_id):
    """Get execution history."""
    try:
        return requests.get(f"{url}/history/{prompt_id}", timeout=10).json()
    except:
        return None

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
    if folder_id:
        print("\n📁 Scanning Google Drive...")
        gdrive_models = scan_gdrive_models(folder_id)
    
    # Build download script
    print("\n📥 Models to download:")
    startup_script = build_download_script(required, gdrive_models)
    
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
        # Wait
        instance = wait_for_ready(instance_id)
        if not instance:
            raise Exception("Failed to start")
        
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
                os.makedirs("vast_outputs", exist_ok=True)
                outputs = history[prompt_id].get('outputs', {})
                
                for node_id, out in outputs.items():
                    if 'images' in out:
                        for img in out['images']:
                            fn = img['filename']
                            img_url = f"{url}/view?filename={fn}&type={img.get('type','output')}&subfolder={img.get('subfolder','')}"
                            print(f"📥 {fn}")
                            urlretrieve(img_url, f"vast_outputs/{fn}")
                
                break
            
            print(".", end="", flush=True)
            time.sleep(3)
        
        print(f"\n✅ Done! → vast_outputs/")
        
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
