#!/usr/bin/env python3
"""
Vast.ai Runner for ComfyUI - Simplified Google Drive Mode
==========================================================
Just drop models in your Google Drive folder. That's it.

v4.0: Uses official ComfyUI template via REST API (template_hash_id)
      Instance Portal + Cloudflare tunnels for reliable access.

Usage:
    python vastai_runner.py --launch
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
import functools

def retry_with_backoff(retries=3, backoff_in_seconds=5):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        print(f"❌ Failed after {retries} retries: {e}")
                        raise
                    sleep_time = (backoff_in_seconds * 2 ** x)
                    print(f"⚠️ Error: {e}. Retrying in {sleep_time}s...")
                    time.sleep(sleep_time)
                    x += 1
        return wrapper
    return decorator

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

# ComfyUI paths inside the Vast.ai container (vastai/comfy)
COMFYUI_IMAGE = "vastai/comfy"
COMFYUI_PATH = "/workspace/ComfyUI"
MODELS_PATH = f"{COMFYUI_PATH}/models"

# Official ComfyUI template hash (22k+ instances created)
COMFYUI_TEMPLATE_HASH = "2188dfd3e0a0b83691bb468ddae0a4e5"
VASTAI_API_BASE = "https://console.vast.ai/api/v0"

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
    """Setup Vast.ai API key from environment or verify existing config."""
    api_key = get_env("VAST_API_KEY", required=False)
    
    if api_key:
        # User credentials provided via Env
        print("🔑 Setting API Key from environment...")
        os.environ["VAST_API_KEY"] = api_key
        subprocess.run(["vastai", "set", "api-key", api_key], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return api_key
    
    # No Env var, check if already configured
    print("ℹ️  VAST_API_KEY not set. Checking existing CLI config...")
    check = subprocess.run(["vastai", "show", "user", "--raw"], 
                           capture_output=True, text=True)
    
    if check.returncode == 0 and "api_key" in check.stdout:
        print("✅ Using existing Vast.ai CLI configuration.")
        return "Using CLI Config"
        
    print("❌ Error: VAST_API_KEY not found and CLI is not configured.")
    print("   Please set VAST_API_KEY in Environment or run:")
    print("   vastai set api-key <your_key>")
    sys.exit(1)

@retry_with_backoff(retries=3, backoff_in_seconds=2)
def run_vastai(cmd):
    """Run vastai command and return JSON result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Check if it's a "No offers" benign error or real error
        if "No offers" in result.stdout:
            # We don't raise here, we return None to let caller handle
            return None
        raise Exception(f"VastAI CLI Error: {result.stderr} {result.stdout}")
        
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
        print(f"⚠️ Warning: GDrive scan failed: {e}")
        # Return empty but don't crash, maybe GDrive down
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

def build_download_script(required_models, gdrive_models, custom_nodes_id=None, folder_id=None):
    """
    Build startup script for the Vast.ai container.
    
    NEW (v1.4): Uses lazy loading instead of downloading all models upfront.
    - Installs gdown
    - Downloads lazy_model_loader.py from the project repo
    - Creates stub files for all models (0 bytes, instant)
    - Starts ComfyUI with model watcher (downloads on-demand)
    """
    commands = [
        "pip install -q gdown requests",
        "apt-get update && apt-get install -y git"
    ]
    
    # 1. Custom Nodes (from custom_nodes.txt) - still do this eagerly since nodes are small
    if custom_nodes_id:
        print(f"   🔧 Found custom_nodes.txt! Adding installation commands...")
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

    # 2. Download lazy_model_loader.py from our GitHub repo
    loader_url = "https://raw.githubusercontent.com/galhosostore-coder/ComfyUI-VastAI/main/lazy_model_loader.py"
    commands.append(f"cd {COMFYUI_PATH} && curl -sL '{loader_url}' -o lazy_model_loader.py")
    
    # 3. Run lazy loader (creates stubs + starts ComfyUI + watches for prompts)
    if folder_id:
        commands.append(f"cd {COMFYUI_PATH} && python lazy_model_loader.py {folder_id}")
    else:
        # Fallback: just start ComfyUI without lazy loading
        print("   ⚠️ No GDrive folder ID, falling back to direct ComfyUI start")
        commands.append(f"cd {COMFYUI_PATH} && python main.py --listen 0.0.0.0 --port 8188")
    
    return "; ".join(commands)

# ==============================================================================
# Model Detection & Workflow Analysis
# ==============================================================================

def detect_model_type(filename):
    """Detect model type from filename extension or keywords users might use."""
    fn = filename.lower()
    if "lora" in fn: return "loras"
    if "control" in fn: return "controlnet"
    if "vae" in fn: return "vae"
    if "upscale" in fn or "esrgan" in fn: return "upscale_models"
    if "clip" in fn or "t5" in fn: return "clip"
    if "unet" in fn: return "unet"
    return "checkpoints"

def analyze_workflow(workflow_path):
    """Find all models required by a workflow JSON."""
    print(f"📋 Analyzing: {workflow_path}")
    try:
        with open(workflow_path, 'r', encoding='utf-8') as f:
            workflow = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load workflow: {e}")
        return {}
    
    required = {}
    
    for node_id, node in workflow.items():
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        
        # Check standard model loaders
        if class_type in MODEL_NODES:
            model_type, key = MODEL_NODES[class_type]
            name = inputs.get(key)
            if name and isinstance(name, str):
                if model_type not in required: required[model_type] = set()
                required[model_type].add(name)
        
        # Special cases
        if class_type == "DualCLIPLoader":
            for k in ["clip_name1", "clip_name2"]:
                name = inputs.get(k)
                if name:
                    if "clip" not in required: required["clip"] = set()
                    required["clip"].add(name)
    
    # Convert sets to sorted lists
    for t in required:
        required[t] = sorted(list(required[t]))
        
    print("\n📦 Required models found:")
    for t, models in required.items():
        for m in models:
            print(f"   - {t}: {m}")
            
    return required

# ==============================================================================
# Vast Internal Logic
# ==============================================================================

def search_gpu(gpu_name, max_price):
    """Search for the best available GPU offer."""
    print(f"\n🔍 Searching for {gpu_name} (max ${max_price}/hr)...")
    
    # Verify verified=True, rented=False
    query = f"gpu_name={gpu_name} rented=False verified=True reliability>0.95"
    cmd = [
        "vastai", "search", "offers", 
        query, 
        "-o", "price_usd",  # Order by price ascending
        "--raw"
    ]
    
    offers = run_vastai(cmd)
    if not offers:
        print("❌ No offers returned from Vast.ai API.")
        return None
        
    # Filter by price manually to be safe
    valid_offers = []
    for offer in offers:
        try:
            price = float(offer.get('dph_total', 999))
            if price <= max_price:
                valid_offers.append(offer)
        except:
            continue
            
    if not valid_offers:
        print(f"❌ No {gpu_name} instances found under ${max_price}/hr.")
        return None
        
    best = valid_offers[0]
    print(f"✅ Found: ID {best['id']} | {best['gpu_name']} | ${best['dph_total']}/hr | {best['dlperf']} DLPerf")
    return best

def rent_gpu(offer_id, startup_script):
    """Rent the specific GPU offer. v4.0: REST API + official ComfyUI template."""
    print(f"\n💰 Renting instance {offer_id} with official ComfyUI template...")
    
    api_key = os.getenv("VAST_API_KEY", "")
    if not api_key:
        print("❌ VAST_API_KEY not set!")
        return None
    
    url = f"{VASTAI_API_BASE}/asks/{offer_id}/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    body = {
        "template_hash_id": COMFYUI_TEMPLATE_HASH,
        "disk": 40,
    }
    
    # Overlay provisioning env vars if GDrive is configured
    folder_id = os.getenv("GDRIVE_FOLDER_ID", "")
    if folder_id:
        provisioning_url = (
            "https://raw.githubusercontent.com/"
            "galhosostore-coder/ComfyUI-VastAI/main/provision.sh"
        )
        body["env"] = (
            f"-e PROVISIONING_SCRIPT={provisioning_url}"
            f" -e GDRIVE_FOLDER_ID={folder_id}"
        )
    
    try:
        resp = requests.put(url, json=body, headers=headers, timeout=30)
        
        if resp.status_code not in (200, 201):
            print(f"❌ API error [{resp.status_code}]: {resp.text[:300]}")
            return None
        
        result = resp.json()
    except Exception as e:
        print(f"❌ Request error: {e}")
        return None
    
    if not result or 'new_contract' not in result:
        print(f"❌ Failed to rent instance: {result}")
        return None
        
    instance_id = result['new_contract']
    print(f"✅ Contract signed! Instance ID: {instance_id}")
    return instance_id

def wait_for_ready(instance_id, timeout=600):
    """Wait for the instance to boot and ComfyUI to respond."""
    print(f"\n⏳ Waiting for instance {instance_id} to become ready (Timeout: {timeout}s)...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check instance status
        instances = run_vastai(["vastai", "show", "instances", "--raw"])
        if not instances:
            print(".", end="", flush=True)
            time.sleep(5)
            continue
            
        # Find our instance
        current = next((i for i in instances if str(i['id']) == str(instance_id)), None)
        
        if not current:
            print("?", end="", flush=True) # Instance not found yet?
            time.sleep(5)
            continue
            
        status = current.get('actual_status')
        
        if status == 'running':
            # Check if ports are mapped
            url = get_url(current)
            if url:
                 print(f"\n🚀 Instance is RUNNING at {url}")
                 return current
        
        print(f"[{status}]", end="", flush=True)
        time.sleep(10)
        
    print(f"\n❌ Timeout waiting for instance {instance_id}.")
    destroy(instance_id) # Cleanup
    return None

def get_url(instance):
    """Get the Vast.ai dashboard URL for accessing the instance.
    
    v4.0: Instance Portal (via official template) handles all connections
    with Cloudflare tunnels and valid SSL. No need to construct direct URLs.
    """
    instance_id = instance.get('id')
    if instance_id:
        return f"https://cloud.vast.ai/instances/"
    return None

def destroy(instance_id):
    """Destroy the instance to stop billing."""
    print(f"\n🗑️  Destroying instance {instance_id}...")
    run_vastai(["vastai", "destroy", "instance", str(instance_id)])
    print("✅ Instance destroyed. Billing stopped.")

def stop_all():
    """Stop all instances owned by user."""
    print("\n🛑 Stopping ALL instances...")
    instances = run_vastai(["vastai", "show", "instances", "--raw"])
    if not instances:
        print("No active instances found.")
        return
        
    for i in instances:
        print(f"   - Destorying {i['id']} ({i['gpu_name']})")
        destroy(i['id'])

# ==============================================================================
# ComfyUI API Usage
# ==============================================================================

def queue_prompt(url, workflow):
    """Submit workflow to ComfyUI API."""
    try:
        p = {"prompt": workflow}
        r = requests.post(f"{url}/prompt", json=p, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"❌ Error queuing prompt: {e}")
        return None

def get_history(url, prompt_id):
    """Get history for a specific prompt_id."""
    try:
        r = requests.get(f"{url}/history/{prompt_id}", timeout=10)
        r.raise_for_status()
        return r.json()
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
    custom_nodes_id = None
    
    if folder_id:
        print("\n📁 Scanning Google Drive...")
        gdrive_models = scan_gdrive_models(folder_id)
        custom_nodes_id = scan_gdrive_custom_nodes(folder_id)
    
    # Build startup script (v1.4: lazy loading - stubs + on-demand download)
    print("\n📥 Preparing lazy-load startup script...")
    startup_script = build_download_script(required, gdrive_models, custom_nodes_id, folder_id=folder_id)
    
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
        # Wait for ready (returns the instance dict or None)
        instance = wait_for_ready(instance_id, timeout=600)
        if not instance:
            print("❌ Instance failed to start.")
            destroy(instance_id)
            return False
        
        # Extra wait for ComfyUI to initialize
        print("⏳ ComfyUI initializing...")
        time.sleep(30)
        
        url = get_url(instance)
        if not url:
            print("❌ Could not determine ComfyUI URL.")
            print(f"Try manually: https://console.vast.ai/instances/")
            if not keep_alive:
                destroy(instance_id)
            return False
        
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
