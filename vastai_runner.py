#!/usr/bin/env python3
"""
Vast.ai Runner for ComfyUI - With Persistent Model Storage
===========================================================
This script manages the lifecycle of Vast.ai GPU instances for ComfyUI workflows.
It supports persistent storage for models and provides model management commands.

Usage:
    python vastai_runner.py --setup-storage          # First time setup - create persistent volume
    python vastai_runner.py --list-models            # List all models in your storage
    python vastai_runner.py --add-model <URL>        # Download a model to storage
    python vastai_runner.py --remove-model <name>    # Remove a model from storage
    python vastai_runner.py --workflow <file.json>   # Run a workflow
"""

import argparse
import time
import json
import os
import requests
import sys
import subprocess
from urllib.request import urlretrieve
from urllib.parse import urlparse
import re

# ==============================================================================
# Configuration
# ==============================================================================

VAST_API_KEY = os.getenv("VAST_API_KEY")
COMFYUI_IMAGE = "yanwk/comfyui-boot:latest"
WORKSPACE_PATH = "/workspace"  # Vast.ai persistent storage mount point
MODELS_PATH = f"{WORKSPACE_PATH}/models"

# Model type to directory mapping (ComfyUI standard structure)
MODEL_DIRS = {
    "checkpoint": "checkpoints",
    "lora": "loras",
    "controlnet": "controlnet",
    "vae": "vae",
    "upscaler": "upscale_models",
    "embedding": "embeddings",
    "clip": "clip",
    "unet": "unet"
}

# ==============================================================================
# Utility Functions
# ==============================================================================

def load_config():
    """Load configuration from config.json if it exists."""
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def check_vast_cli():
    """Verify that the vastai CLI is installed."""
    try:
        subprocess.run(["vastai", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("Error: 'vastai' CLI tool not found. Please install it with: pip install vastai")
        sys.exit(1)

def setup_api_key(config):
    """Setup and validate the Vast.ai API key."""
    api_key = os.getenv("VAST_API_KEY") or config.get("api_key")
    if not api_key:
        print("Error: Please set 'VAST_API_KEY' environment variable or 'api_key' in config.json")
        sys.exit(1)
    
    os.environ["VAST_API_KEY"] = api_key
    subprocess.run(["vastai", "set", "api-key", api_key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return api_key

def run_vastai_command(cmd, parse_json=True):
    """Run a vastai CLI command and return the result."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    if parse_json:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout
    return result.stdout

def get_storage_template_id():
    """Get or create a persistent storage template ID from config."""
    config_path = "config.json"
    config = load_config()
    return config.get("storage_template_id")

def save_storage_template_id(template_id):
    """Save the storage template ID to config."""
    config = load_config()
    config["storage_template_id"] = template_id
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)

# ==============================================================================
# Instance Management
# ==============================================================================

def search_offers(gpu_query="RTX_3090", max_price=0.5):
    """Search for available GPU offers on Vast.ai."""
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
    
    # Filter by price
    valid_offers = [o for o in offers if float(o['dph_total']) <= max_price]
    if not valid_offers:
        print(f"❌ No offers found within ${max_price}/hr price range.")
        return None
    
    return valid_offers[0]

def rent_instance(offer_id, disk_size=50, use_persistent=True):
    """Rent a Vast.ai instance with optional persistent storage."""
    print(f"💰 Renting instance (Offer ID: {offer_id})...")
    
    # Build the onstart command to:
    # 1. Link models from persistent storage to ComfyUI
    # 2. Start ComfyUI
    onstart_script = f"""
    mkdir -p {MODELS_PATH}/checkpoints {MODELS_PATH}/loras {MODELS_PATH}/controlnet {MODELS_PATH}/vae {MODELS_PATH}/upscale_models {MODELS_PATH}/embeddings {MODELS_PATH}/clip {MODELS_PATH}/unet
    ln -sf {MODELS_PATH}/* /app/models/ 2>/dev/null || true
    cd /app && python main.py --listen 0.0.0.0 --port 8188
    """
    
    cmd = [
        "vastai", "create", "instance", str(offer_id),
        "--image", COMFYUI_IMAGE,
        "--disk", str(disk_size),
        "--onstart-cmd", onstart_script.strip().replace('\n', ' && '),
        "--raw"
    ]
    
    result = run_vastai_command(cmd)
    if not result:
        return None
    
    instance_id = result.get('new_contract')
    print(f"✅ Instance rented! Contract ID: {instance_id}")
    return instance_id

def wait_for_instance(instance_id, timeout=300):
    """Wait for an instance to be ready."""
    print(f"⏳ Waiting for instance {instance_id} to start...", end="", flush=True)
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
        if not instances:
            time.sleep(5)
            continue
        
        target = next((i for i in instances if i['id'] == instance_id), None)
        if target and target.get('actual_status') == 'running':
            ports = target.get('ports', {})
            if ports:
                print(" ✅ Running!")
                return target
        
        print(".", end="", flush=True)
        time.sleep(5)
    
    print(" ❌ Timeout!")
    return None

def get_instance_url(instance):
    """Extract the ComfyUI URL from instance info."""
    ports = instance.get('ports', {})
    if '8188/tcp' in ports:
        mapping = ports['8188/tcp'][0]
        return f"http://{mapping['HostIp']}:{mapping['HostPort']}"
    return None

def destroy_instance(instance_id):
    """Destroy a Vast.ai instance."""
    print(f"🗑️ Destroying instance {instance_id}...")
    subprocess.run(["vastai", "destroy", "instance", str(instance_id)])
    print("✅ Instance destroyed. Billing stopped.")

def ssh_to_instance(instance_id):
    """Get SSH command for an instance."""
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    if not instances:
        return None
    
    target = next((i for i in instances if i['id'] == instance_id), None)
    if target:
        ssh_host = target.get('ssh_host')
        ssh_port = target.get('ssh_port')
        if ssh_host and ssh_port:
            return f"ssh -p {ssh_port} root@{ssh_host}"
    return None

def run_ssh_command(instance_id, command):
    """Run a command on the instance via SSH."""
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    if not instances:
        return None
    
    target = next((i for i in instances if i['id'] == instance_id), None)
    if not target:
        return None
    
    ssh_host = target.get('ssh_host')
    ssh_port = target.get('ssh_port')
    
    if not ssh_host or not ssh_port:
        print("❌ SSH not available for this instance.")
        return None
    
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(ssh_port), f"root@{ssh_host}", command]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

# ==============================================================================
# Model Management
# ==============================================================================

def detect_model_type(url, filename):
    """Try to detect model type from URL or filename."""
    url_lower = url.lower()
    filename_lower = filename.lower()
    
    if "lora" in url_lower or "lora" in filename_lower:
        return "lora"
    elif "controlnet" in url_lower or "control" in filename_lower:
        return "controlnet"
    elif "vae" in url_lower or "vae" in filename_lower:
        return "vae"
    elif "upscale" in url_lower or "esrgan" in filename_lower:
        return "upscaler"
    elif "embedding" in url_lower or "embed" in filename_lower:
        return "embedding"
    else:
        return "checkpoint"  # Default to checkpoint

def setup_storage(gpu_query, max_price, disk_size=50):
    """Setup persistent storage on Vast.ai."""
    print("=" * 60)
    print("🚀 SETTING UP PERSISTENT STORAGE")
    print("=" * 60)
    
    # Find an offer
    offer = search_offers(gpu_query, max_price)
    if not offer:
        print("❌ No suitable GPU offers found.")
        return False
    
    offer_id = offer['id']
    gpu_name = offer.get('gpu_name', 'Unknown')
    price = offer['dph_total']
    
    print(f"📦 Selected: {gpu_name} at ${price}/hr")
    
    # Rent instance
    instance_id = rent_instance(offer_id, disk_size)
    if not instance_id:
        return False
    
    # Save instance ID for future reference
    save_storage_template_id(instance_id)
    
    # Wait for it to start
    instance = wait_for_instance(instance_id)
    if not instance:
        destroy_instance(instance_id)
        return False
    
    # Create model directories
    print("📁 Creating model directories...")
    time.sleep(10)  # Give the instance time to fully initialize
    
    mkdir_cmd = f"mkdir -p {MODELS_PATH}/checkpoints {MODELS_PATH}/loras {MODELS_PATH}/controlnet {MODELS_PATH}/vae {MODELS_PATH}/upscale_models {MODELS_PATH}/embeddings"
    run_ssh_command(instance_id, mkdir_cmd)
    
    print("")
    print("=" * 60)
    print("✅ STORAGE SETUP COMPLETE!")
    print("=" * 60)
    print(f"Instance ID: {instance_id}")
    print(f"Disk Size: {disk_size}GB")
    print("")
    print("Your models will be stored in /workspace/models/")
    print("")
    print("IMPORTANT: The instance is still running and billing!")
    print("Use one of these commands:")
    print(f"  - Add models: python vastai_runner.py --add-model <URL>")
    print(f"  - Stop billing: python vastai_runner.py --stop")
    print("")
    
    return True

def list_models(gpu_query, max_price):
    """List all models in persistent storage."""
    print("📋 Listing models in persistent storage...")
    
    # We need a running instance to check storage
    # First check if we have an existing instance
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    running_instance = None
    
    if instances:
        running_instance = next((i for i in instances if i.get('actual_status') == 'running'), None)
    
    if not running_instance:
        print("⚠️ No running instance. Starting a temporary instance to check storage...")
        offer = search_offers(gpu_query, max_price)
        if not offer:
            return
        
        instance_id = rent_instance(offer['id'])
        instance = wait_for_instance(instance_id)
        if not instance:
            destroy_instance(instance_id)
            return
        
        time.sleep(10)
        running_instance = {'id': instance_id}
    
    instance_id = running_instance['id']
    
    # List files in each model directory
    print("\n" + "=" * 60)
    print("📦 MODELS IN PERSISTENT STORAGE")
    print("=" * 60)
    
    for model_type, dir_name in MODEL_DIRS.items():
        path = f"{MODELS_PATH}/{dir_name}"
        result = run_ssh_command(instance_id, f"ls -lh {path} 2>/dev/null")
        
        if result and result.strip():
            print(f"\n📁 {model_type.upper()} ({dir_name}/)")
            print("-" * 40)
            for line in result.strip().split('\n'):
                if line and not line.startswith('total'):
                    print(f"  {line}")
        else:
            print(f"\n📁 {model_type.upper()} ({dir_name}/) - Empty")
    
    print("\n" + "=" * 60)

def add_model(url, model_type, gpu_query, max_price):
    """Download a model to persistent storage."""
    print(f"📥 Adding model from: {url}")
    
    # Extract filename from URL
    parsed = urlparse(url)
    filename = os.path.basename(parsed.path)
    if not filename or '.' not in filename:
        filename = "downloaded_model.safetensors"
    
    # Auto-detect model type if not specified
    if not model_type:
        model_type = detect_model_type(url, filename)
        print(f"🔍 Auto-detected model type: {model_type}")
    
    dir_name = MODEL_DIRS.get(model_type, "checkpoints")
    dest_path = f"{MODELS_PATH}/{dir_name}/{filename}"
    
    # Get or start instance
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    running_instance = None
    
    if instances:
        running_instance = next((i for i in instances if i.get('actual_status') == 'running'), None)
    
    temp_instance = False
    if not running_instance:
        print("⚠️ No running instance. Starting temporary instance...")
        offer = search_offers(gpu_query, max_price)
        if not offer:
            return False
        
        instance_id = rent_instance(offer['id'])
        instance = wait_for_instance(instance_id)
        if not instance:
            destroy_instance(instance_id)
            return False
        
        time.sleep(10)
        running_instance = {'id': instance_id}
        temp_instance = True
    
    instance_id = running_instance['id']
    
    # Download the model
    print(f"⬇️ Downloading to {dest_path}...")
    download_cmd = f"wget -q --show-progress -O '{dest_path}' '{url}'"
    
    # For large files, we need to handle this differently
    # Use subprocess directly to show progress
    ssh_host = None
    ssh_port = None
    
    if instances:
        target = next((i for i in instances if i['id'] == instance_id), None)
        if target:
            ssh_host = target.get('ssh_host')
            ssh_port = target.get('ssh_port')
    
    if ssh_host and ssh_port:
        cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(ssh_port), f"root@{ssh_host}", download_cmd]
        subprocess.run(cmd)
        print(f"✅ Model saved to {dest_path}")
    
    if temp_instance:
        print("\n⚠️ Temporary instance is still running.")
        response = input("Destroy instance to stop billing? [Y/n]: ").strip().lower()
        if response != 'n':
            destroy_instance(instance_id)
    
    return True

def remove_model(model_name, gpu_query, max_price):
    """Remove a model from persistent storage."""
    print(f"🗑️ Removing model: {model_name}")
    
    # Get running instance
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    running_instance = None
    
    if instances:
        running_instance = next((i for i in instances if i.get('actual_status') == 'running'), None)
    
    if not running_instance:
        print("⚠️ No running instance. Starting temporary instance...")
        offer = search_offers(gpu_query, max_price)
        if not offer:
            return False
        
        instance_id = rent_instance(offer['id'])
        instance = wait_for_instance(instance_id)
        if not instance:
            destroy_instance(instance_id)
            return False
        
        time.sleep(10)
        instance_id = instance_id
    else:
        instance_id = running_instance['id']
    
    # Find and remove the model
    find_cmd = f"find {MODELS_PATH} -name '*{model_name}*' -type f"
    result = run_ssh_command(instance_id, find_cmd)
    
    if result and result.strip():
        files = result.strip().split('\n')
        print(f"Found {len(files)} matching file(s):")
        for f in files:
            print(f"  - {f}")
        
        response = input("Delete these files? [y/N]: ").strip().lower()
        if response == 'y':
            for f in files:
                run_ssh_command(instance_id, f"rm '{f}'")
            print("✅ Files deleted.")
    else:
        print(f"❌ No files found matching '{model_name}'")
    
    return True

def stop_instances():
    """Stop all running instances to stop billing."""
    instances = run_vastai_command(["vastai", "show", "instances", "--raw"])
    
    if not instances:
        print("No instances found.")
        return
    
    running = [i for i in instances if i.get('actual_status') == 'running']
    
    if not running:
        print("No running instances found.")
        return
    
    print(f"Found {len(running)} running instance(s):")
    for inst in running:
        print(f"  - ID: {inst['id']} | GPU: {inst.get('gpu_name', 'N/A')} | ${inst.get('dph_total', 0)}/hr")
    
    response = input("Destroy all running instances? [y/N]: ").strip().lower()
    if response == 'y':
        for inst in running:
            destroy_instance(inst['id'])
        print("✅ All instances destroyed. Billing stopped.")

# ==============================================================================
# ComfyUI Workflow Execution
# ==============================================================================

def queue_prompt(comfy_url, prompt_workflow):
    """Send a workflow to ComfyUI for execution."""
    try:
        response = requests.post(
            f"{comfy_url}/prompt",
            json={"prompt": prompt_workflow},
            timeout=30
        )
        return response.json()
    except Exception as e:
        print(f"Error queueing prompt: {e}")
        return None

def get_history(comfy_url, prompt_id):
    """Get the execution history for a prompt."""
    try:
        response = requests.get(f"{comfy_url}/history/{prompt_id}", timeout=10)
        return response.json()
    except:
        return None

def run_workflow(workflow_path, gpu_query, max_price, keep_alive):
    """Run a ComfyUI workflow on Vast.ai."""
    print("=" * 60)
    print("🎨 RUNNING COMFYUI WORKFLOW")
    print("=" * 60)
    
    # Load workflow
    with open(workflow_path, 'r') as f:
        workflow_data = json.load(f)
    
    # Find and rent GPU
    offer = search_offers(gpu_query, max_price)
    if not offer:
        return False
    
    instance_id = rent_instance(offer['id'])
    if not instance_id:
        return False
    
    try:
        # Wait for instance
        instance = wait_for_instance(instance_id)
        if not instance:
            raise Exception("Instance failed to start")
        
        # Wait for ComfyUI to initialize
        print("⏳ Waiting for ComfyUI to initialize...")
        time.sleep(20)
        
        api_url = get_instance_url(instance)
        if not api_url:
            raise Exception("Could not get instance URL")
        
        print(f"🌐 ComfyUI URL: {api_url}")
        
        # Queue the workflow
        print("📤 Sending workflow...")
        result = queue_prompt(api_url, workflow_data)
        if not result:
            raise Exception("Failed to queue workflow")
        
        prompt_id = result.get('prompt_id')
        print(f"⏳ Workflow queued (ID: {prompt_id}). Processing...", end="", flush=True)
        
        # Wait for completion
        while True:
            history = get_history(api_url, prompt_id)
            if history and prompt_id in history:
                print(" ✅ Complete!")
                
                # Download outputs
                outputs = history[prompt_id].get('outputs', {})
                output_dir = "vast_outputs"
                os.makedirs(output_dir, exist_ok=True)
                
                for node_id, node_output in outputs.items():
                    if 'images' in node_output:
                        for image in node_output['images']:
                            filename = image['filename']
                            img_type = image.get('type', 'output')
                            subfolder = image.get('subfolder', '')
                            
                            file_url = f"{api_url}/view?filename={filename}&type={img_type}&subfolder={subfolder}"
                            local_path = os.path.join(output_dir, filename)
                            
                            print(f"📥 Downloading {filename}...")
                            urlretrieve(file_url, local_path)
                            print(f"   Saved to: {local_path}")
                
                break
            
            print(".", end="", flush=True)
            time.sleep(3)
        
        print("\n✅ Workflow completed successfully!")
        print(f"📁 Outputs saved to: {output_dir}/")
        
    except KeyboardInterrupt:
        print("\n⚠️ Aborted by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        if not keep_alive:
            destroy_instance(instance_id)
        else:
            print(f"\n⚠️ Instance {instance_id} kept alive. Remember to stop it!")
            print(f"   Stop with: python vastai_runner.py --stop")
    
    return True

# ==============================================================================
# Main Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Vast.ai Runner for ComfyUI with Persistent Model Storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Setup storage:     python vastai_runner.py --setup-storage
  Add a model:       python vastai_runner.py --add-model https://civitai.com/.../model.safetensors
  List models:       python vastai_runner.py --list-models
  Run workflow:      python vastai_runner.py --workflow my_workflow.json
  Stop billing:      python vastai_runner.py --stop
        """
    )
    
    # Commands
    parser.add_argument("--setup-storage", action="store_true", help="Setup persistent storage on Vast.ai")
    parser.add_argument("--list-models", action="store_true", help="List all models in persistent storage")
    parser.add_argument("--add-model", type=str, help="Download a model from URL to persistent storage")
    parser.add_argument("--model-type", type=str, choices=list(MODEL_DIRS.keys()), help="Model type (auto-detected if not specified)")
    parser.add_argument("--remove-model", type=str, help="Remove a model from storage")
    parser.add_argument("--workflow", type=str, help="Path to workflow_api.json to execute")
    parser.add_argument("--stop", action="store_true", help="Stop all running instances")
    
    # Options
    parser.add_argument("--gpu", type=str, default="RTX_3090", help="GPU to search for (default: RTX_3090)")
    parser.add_argument("--price", type=float, default=0.5, help="Max price per hour (default: 0.5)")
    parser.add_argument("--disk", type=int, default=50, help="Disk size in GB (default: 50)")
    parser.add_argument("--keep-alive", action="store_true", help="Don't destroy instance after workflow")
    
    # Load config and set defaults
    config = load_config()
    default_gpu = os.getenv("VAST_GPU") or config.get("gpu_query", "RTX_3090")
    env_price = os.getenv("VAST_PRICE")
    default_price = float(env_price) if env_price else config.get("max_price", 0.5)
    
    parser.set_defaults(gpu=default_gpu, price=default_price)
    args = parser.parse_args()
    
    # Setup API key
    setup_api_key(config)
    check_vast_cli()
    
    # Execute command
    if args.setup_storage:
        setup_storage(args.gpu, args.price, args.disk)
    elif args.list_models:
        list_models(args.gpu, args.price)
    elif args.add_model:
        add_model(args.add_model, args.model_type, args.gpu, args.price)
    elif args.remove_model:
        remove_model(args.remove_model, args.gpu, args.price)
    elif args.stop:
        stop_instances()
    elif args.workflow:
        run_workflow(args.workflow, args.gpu, args.price, args.keep_alive)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
