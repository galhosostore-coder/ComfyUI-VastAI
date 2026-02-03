#!/usr/bin/env python3
"""
Vast.ai Runner for ComfyUI - Google Drive Integration
======================================================
This script manages Vast.ai GPU instances for ComfyUI workflows.
Models are stored on Google Drive and downloaded on-demand.

Usage:
    python vastai_runner.py --workflow my_workflow.json
    python vastai_runner.py --workflow my_workflow.json --gpu RTX_4090 --price 1.0
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
from urllib.parse import urlparse, parse_qs

# ==============================================================================
# Configuration
# ==============================================================================

COMFYUI_IMAGE = "yanwk/comfyui-boot:latest"
COMFYUI_PATH = "/app"
MODELS_PATH = f"{COMFYUI_PATH}/models"

# Model type to directory mapping (ComfyUI standard structure)
MODEL_DIRS = {
    "checkpoints": "checkpoints",
    "loras": "loras", 
    "controlnet": "controlnet",
    "vae": "vae",
    "upscale_models": "upscale_models",
    "embeddings": "embeddings",
    "clip": "clip",
    "unet": "unet",
    "clip_vision": "clip_vision"
}

# Node types that load models (maps node class -> model type)
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
    "DualCLIPLoader": ("clip", "clip_name1"),  # Has clip_name1 and clip_name2
}

# ==============================================================================
# Utility Functions
# ==============================================================================

def load_config():
    """Load configuration from config.json if it exists."""
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def check_vast_cli():
    """Verify that the vastai CLI is installed."""
    try:
        subprocess.run(["vastai", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("❌ Error: 'vastai' CLI not found. Install with: pip install vastai")
        sys.exit(1)

def setup_api_key(config):
    """Setup and validate the Vast.ai API key."""
    api_key = os.getenv("VAST_API_KEY") or config.get("api_key")
    if not api_key:
        print("❌ Error: Set 'VAST_API_KEY' environment variable or 'api_key' in config.json")
        sys.exit(1)
    
    os.environ["VAST_API_KEY"] = api_key
    subprocess.run(["vastai", "set", "api-key", api_key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return api_key

def run_vastai_command(cmd):
    """Run a vastai CLI command and return parsed JSON."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout

def extract_gdrive_id(url):
    """Extract file ID from various Google Drive URL formats."""
    # Format: https://drive.google.com/file/d/FILE_ID/view
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Format: https://drive.google.com/open?id=FILE_ID
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if 'id' in query:
        return query['id'][0]
    
    return None

# ==============================================================================
# Workflow Analysis
# ==============================================================================

def analyze_workflow(workflow_path):
    """Analyze a workflow JSON to find required models."""
    print(f"📋 Analyzing workflow: {workflow_path}")
    
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)
    
    required_models = {}
    
    for node_id, node_data in workflow.items():
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs", {})
        
        if class_type in MODEL_NODES:
            model_type, input_key = MODEL_NODES[class_type]
            model_name = inputs.get(input_key)
            
            if model_name:
                if model_type not in required_models:
                    required_models[model_type] = set()
                required_models[model_type].add(model_name)
                
        # Handle DualCLIPLoader which has two clip inputs
        if class_type == "DualCLIPLoader":
            for key in ["clip_name1", "clip_name2"]:
                model_name = inputs.get(key)
                if model_name:
                    if "clip" not in required_models:
                        required_models["clip"] = set()
                    required_models["clip"].add(model_name)
    
    # Convert sets to lists for JSON serialization
    for model_type in required_models:
        required_models[model_type] = list(required_models[model_type])
    
    print("\n📦 Models required by this workflow:")
    for model_type, models in required_models.items():
        print(f"   {model_type}/")
        for m in models:
            print(f"      └── {m}")
    
    return required_models

def get_gdrive_links(config, required_models):
    """Match required models with Google Drive links from config."""
    gdrive_models = config.get("gdrive_models", {})
    download_list = []
    missing = []
    
    for model_type, models in required_models.items():
        type_links = gdrive_models.get(model_type, {})
        
        for model_name in models:
            if model_name in type_links:
                download_list.append({
                    "name": model_name,
                    "type": model_type,
                    "url": type_links[model_name],
                    "dest": f"{MODELS_PATH}/{MODEL_DIRS.get(model_type, model_type)}/{model_name}"
                })
            else:
                missing.append(f"{model_type}/{model_name}")
    
    return download_list, missing

# ==============================================================================
# Instance Management
# ==============================================================================

def search_offers(gpu_query="RTX_3090", max_price=0.5):
    """Search for available GPU offers."""
    print(f"🔍 Searching for {gpu_query} (Max: ${max_price}/hr)...")
    
    cmd = [
        "vastai", "search", "offers",
        f"gpu_name={gpu_query} rented=False reliability>0.95 verified=True dlperf>10",
        "-o", "price_usd",
        "--raw"
    ]
    
    offers = run_vastai_command(cmd)
    if not offers:
        return None
    
    valid = [o for o in offers if float(o['dph_total']) <= max_price]
    if not valid:
        print(f"❌ No offers found within ${max_price}/hr")
        return None
    
    return valid[0]

def build_onstart_script(download_list):
    """Build the startup script that downloads models and starts ComfyUI."""
    
    # Install gdown for Google Drive downloads
    script_parts = [
        "pip install -q gdown",
    ]
    
    # Add download commands for each model
    for item in download_list:
        gdrive_id = extract_gdrive_id(item["url"])
        if gdrive_id:
            dest = item["dest"]
            # Create directory and download
            script_parts.append(f"mkdir -p $(dirname {dest})")
            script_parts.append(f"gdown -q --id {gdrive_id} -O {dest}")
            print(f"   📥 Will download: {item['name']} -> {dest}")
    
    # Start ComfyUI
    script_parts.append(f"cd {COMFYUI_PATH} && python main.py --listen 0.0.0.0 --port 8188")
    
    return " && ".join(script_parts)

def rent_instance(offer_id, onstart_script, disk_size=20):
    """Rent a Vast.ai instance."""
    print(f"💰 Renting instance...")
    
    cmd = [
        "vastai", "create", "instance", str(offer_id),
        "--image", COMFYUI_IMAGE,
        "--disk", str(disk_size),
        "--onstart-cmd", onstart_script,
        "--raw"
    ]
    
    result = run_vastai_command(cmd)
    if not result:
        return None
    
    instance_id = result.get('new_contract')
    print(f"✅ Instance rented! ID: {instance_id}")
    return instance_id

def wait_for_instance(instance_id, timeout=600):
    """Wait for instance to be ready."""
    print(f"⏳ Waiting for instance (downloading models)...", end="", flush=True)
    start = time.time()
    
    while time.time() - start < timeout:
        instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
        if instances:
            target = next((i for i in instances if i['id'] == instance_id), None)
            if target and target.get('actual_status') == 'running':
                if target.get('ports'):
                    print(" ✅ Ready!")
                    return target
        
        print(".", end="", flush=True)
        time.sleep(10)
    
    print(" ❌ Timeout!")
    return None

def get_instance_url(instance):
    """Get ComfyUI URL from instance."""
    ports = instance.get('ports', {})
    if '8188/tcp' in ports:
        m = ports['8188/tcp'][0]
        return f"http://{m['HostIp']}:{m['HostPort']}"
    return None

def destroy_instance(instance_id):
    """Destroy instance."""
    print(f"🗑️ Destroying instance {instance_id}...")
    subprocess.run(["vastai", "destroy", "instance", str(instance_id)])
    print("✅ Billing stopped.")

def stop_all():
    """Stop all running instances."""
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    if not instances:
        print("No instances found.")
        return
    
    running = [i for i in instances if i.get('actual_status') == 'running']
    if not running:
        print("No running instances.")
        return
    
    print(f"Found {len(running)} running instance(s):")
    for i in running:
        print(f"   ID: {i['id']} | {i.get('gpu_name', 'N/A')} | ${i.get('dph_total', 0)}/hr")
    
    resp = input("Destroy all? [y/N]: ").strip().lower()
    if resp == 'y':
        for i in running:
            destroy_instance(i['id'])

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
        r = requests.get(f"{url}/history/{prompt_id}", timeout=10)
        return r.json()
    except:
        return None

def run_workflow(workflow_path, gpu_query, max_price, keep_alive):
    """Main workflow execution."""
    print("=" * 60)
    print("🎨 COMFYUI WORKFLOW RUNNER (Google Drive Mode)")
    print("=" * 60)
    
    config = load_config()
    
    # Analyze workflow
    required_models = analyze_workflow(workflow_path)
    
    # Get download links
    download_list, missing = get_gdrive_links(config, required_models)
    
    if missing:
        print(f"\n⚠️ Missing Google Drive links for:")
        for m in missing:
            print(f"   - {m}")
        print(f"\nAdd these to 'gdrive_models' in config.json")
        
        resp = input("\nContinue anyway? (model might be in Docker image) [y/N]: ").strip().lower()
        if resp != 'y':
            return False
    
    if download_list:
        print(f"\n📥 Will download {len(download_list)} model(s) from Google Drive")
    
    # Build startup script
    onstart_script = build_onstart_script(download_list)
    
    # Load workflow
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow_data = json.load(f)
    
    # Find and rent GPU
    offer = search_offers(gpu_query, max_price)
    if not offer:
        return False
    
    gpu_name = offer.get('gpu_name', 'Unknown')
    price = offer['dph_total']
    print(f"📦 Selected: {gpu_name} at ${price}/hr")
    
    instance_id = rent_instance(offer['id'], onstart_script)
    if not instance_id:
        return False
    
    try:
        # Wait (longer timeout for model downloads)
        instance = wait_for_instance(instance_id, timeout=900)
        if not instance:
            raise Exception("Instance failed to start")
        
        # Extra wait for ComfyUI init after model downloads
        print("⏳ Waiting for ComfyUI to initialize...")
        time.sleep(30)
        
        api_url = get_instance_url(instance)
        if not api_url:
            raise Exception("Could not get URL")
        
        print(f"🌐 ComfyUI: {api_url}")
        
        # Queue workflow
        print("📤 Sending workflow...")
        result = queue_prompt(api_url, workflow_data)
        if not result:
            raise Exception("Failed to queue")
        
        prompt_id = result.get('prompt_id')
        print(f"⏳ Processing...", end="", flush=True)
        
        # Wait for completion
        while True:
            history = get_history(api_url, prompt_id)
            if history and prompt_id in history:
                print(" ✅ Done!")
                
                # Download outputs
                outputs = history[prompt_id].get('outputs', {})
                os.makedirs("vast_outputs", exist_ok=True)
                
                for node_id, out in outputs.items():
                    if 'images' in out:
                        for img in out['images']:
                            fn = img['filename']
                            t = img.get('type', 'output')
                            sf = img.get('subfolder', '')
                            
                            img_url = f"{api_url}/view?filename={fn}&type={t}&subfolder={sf}"
                            local = os.path.join("vast_outputs", fn)
                            
                            print(f"📥 Downloading {fn}...")
                            urlretrieve(img_url, local)
                
                break
            
            print(".", end="", flush=True)
            time.sleep(3)
        
        print(f"\n✅ Complete! Outputs in: vast_outputs/")
        
    except KeyboardInterrupt:
        print("\n⚠️ Aborted.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        if not keep_alive:
            destroy_instance(instance_id)
        else:
            print(f"\n⚠️ Instance {instance_id} kept alive!")
            print(f"   Stop with: python vastai_runner.py --stop")
    
    return True

# ==============================================================================
# Main
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="ComfyUI on Vast.ai with Google Drive models")
    parser.add_argument("--workflow", type=str, help="Workflow JSON file to run")
    parser.add_argument("--stop", action="store_true", help="Stop all running instances")
    parser.add_argument("--gpu", type=str, default="RTX_3090", help="GPU to search for")
    parser.add_argument("--price", type=float, default=0.5, help="Max price per hour")
    parser.add_argument("--keep-alive", action="store_true", help="Don't destroy after run")
    
    # Load defaults from config/env
    config = load_config()
    default_gpu = os.getenv("VAST_GPU") or config.get("gpu_query", "RTX_3090")
    env_price = os.getenv("VAST_PRICE")
    default_price = float(env_price) if env_price else config.get("max_price", 0.5)
    
    parser.set_defaults(gpu=default_gpu, price=default_price)
    args = parser.parse_args()
    
    setup_api_key(config)
    check_vast_cli()
    
    if args.stop:
        stop_all()
    elif args.workflow:
        run_workflow(args.workflow, args.gpu, args.price, args.keep_alive)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
