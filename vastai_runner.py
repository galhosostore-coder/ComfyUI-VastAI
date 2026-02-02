import argparse
import time
import json
import os
import requests
import sys
import subprocess
from urllib.request import urlretrieve

# Setup Vast.ai API Key
# User must set VAST_API_KEY environment variable or pass it to this script
VAST_API_KEY = os.getenv("VAST_API_KEY")


def load_config():
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def check_vast_cli():
    try:
        subprocess.run(["vastai", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print("Error: 'vastai' CLI tool not found. Please install it with: pip install vastai")
        sys.exit(1)

def search_and_rent(gpu_query="gpu_name=RTX_3090", max_price=0.5):
    print(f"Searching for GPU with query: {gpu_query} (Max Price: ${max_price}/hr)...")
    # Use vastai CLI to search
    # vastai search offers "query" -o "price_usd" --raw
    
    cmd = [
        "vastai", "search", "offers", 
        f"{gpu_query} rented=False reliability>0.95 verified=True dlperf>10", 
        "-o", "price_usd", 
        "--raw"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error searching vastai: {result.stderr}")
        return None

    offers = json.loads(result.stdout)
    if not offers:
        print("No offers found matching criteria.")
        return None

    # Filter by price
    valid_offers = [o for o in offers if float(o['dph_total']) <= max_price]
    if not valid_offers:
        print("No offers found within price range.")
        return None

    best_offer = valid_offers[0]
    offer_id = best_offer['id']
    price = best_offer['dph_total']
    gpu = best_offer.get('gpu_name', 'Unknown GPU')
    
    print(f"Found Offer: {gpu} at ${price}/hr (ID: {offer_id})")
    print("Renting instance...")

    # Rent
    # Image: standard pytorch or a comfyui specific image. 
    # Using 'yanwk/comfyui-boot:latest' or similar is good, but let's stick to a robust one.
    # We will use a popular ComfyUI docker image that has dependencies pre-installed.
    image = "yanwk/comfyui-boot:latest" 
    
    rent_cmd = [
        "vastai", "create", "instance", str(offer_id),
        "--image", image,
        "--disk", "20",
        "--onstart-cmd", "python main.py --listen 0.0.0.0 --port 8188", # Ensure it runs
        "--raw"
    ]
    
    rent_res = subprocess.run(rent_cmd, capture_output=True, text=True)
    if rent_res.returncode != 0:
        print(f"Failed to rent: {rent_res.stderr}")
        return None
        
    rent_data = json.loads(rent_res.stdout)
    new_id = rent_data.get('new_contract')
    print(f"Instance Rented! Contract ID: {new_id}")
    return new_id

def wait_for_instance(instance_id):
    print(f"Waiting for instance {instance_id} to be ready...", end="", flush=True)
    while True:
        cmd = ["vastai", "show", "instances", "--raw"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            instances = json.loads(res.stdout)
        except:
            time.sleep(2)
            continue
            
        target = next((i for i in instances if i['id'] == instance_id), None)
        if not target:
            print("Instance not found in list...")
            pass
        else:
            status = target.get('actual_status')
            if status == 'running':
                # Check if port is mapped
                ports = target.get('ports', {})
                # We expect 8188/tcp mapping
                # vastai returns ports like { '8188/tcp': [{ 'HostIp': '...', 'HostPort': '...' }] }
                if ports:
                    # Depending on API version, structure varies. Assuming list logic.
                    print(" Running!")
                    return target
            
        print(".", end="", flush=True)
        time.sleep(5)

def get_api_url(instance):
    # Extract HostIP and Port for 8188
    # 'ports': {'8188/tcp': [{'HostIp': 'X.X.X.X', 'HostPort': 'YYYYY'}]}
    ports = instance.get('ports', {})
    if '8188/tcp' in ports:
        mapping = ports['8188/tcp'][0]
        host = mapping['HostIp']
        port = mapping['HostPort']
        return f"http://{host}:{port}"
    # Fallback usually the public ip + mapped port
    return None

def queue_prompt(comfy_url, prompt_workflow):
    p = {"prompt": prompt_workflow}
    data = json.dumps(p).encode('utf-8')
    try:
        req = requests.post(f"{comfy_url}/prompt", data=data)
        return req.json()
    except Exception as e:
        print(f"Error queueing prompt: {e}")
        return None

def get_history(comfy_url, prompt_id):
    try:
        req = requests.get(f"{comfy_url}/history/{prompt_id}")
        return req.json()
    except:
        return None

def clean_and_exit(instance_id):
    print(f"Destroying instance {instance_id}...")
    subprocess.run(["vastai", "destroy", "instance", str(instance_id)])
    print("Done.")

def main():
    parser = argparse.ArgumentParser(description="Run ComfyUI workflow on Vast.ai")
    parser.add_argument("--workflow", required=True, help="Path to workflow_api.json")
    parser.add_argument("--gpu", default="RTX_3090", help="GPU search query")
    parser.add_argument("--price", type=float, default=0.5, help="Max price per hour")
    parser.add_argument("--keep-alive", action="store_true", help="Do not destroy instance after run")
    

    # Load config file
    config = load_config()
    
    # Priority: Args > Config > Defaults/Env

    # API Key
    api_key = os.getenv("VAST_API_KEY") or config.get("api_key")
    if not api_key:
        print("Please set VAST_API_KEY environment variable or 'api_key' in config.json.")
        sys.exit(1)
    
    # Defaults handled by argparse, but we can override defaults if config exists and arg is default
    # A simpler way is to set defaults in argparse from config
    parser.set_defaults(
        gpu=config.get("gpu_query", "RTX_3090"),
        price=config.get("max_price", 0.5),
        keep_alive=config.get("keep_alive", False)
    )

    args = parser.parse_args()
    
    # Set the env var for the subprocess calls if it wasn't set
    if "VAST_API_KEY" not in os.environ:
        os.environ["VAST_API_KEY"] = api_key
        
    check_vast_cli()
    
    # Load Workflow
    with open(args.workflow, 'r') as f:
        workflow_data = json.load(f)
        
    # Rent
    instance_id = search_and_rent(args.gpu, args.price)
    if not instance_id:
        sys.exit(1)
        
    try:
        # Wait
        instance_info = wait_for_instance(instance_id)
        
        # Give ComfyUI inside Docker a moment to actually start the HTTP server
        print("Waiting for ComfyUI to initialize...")
        time.sleep(15) 
        
        api_url = get_api_url(instance_info)
        print(f"ComfyUI Remote URL: {api_url}")
        
        # Execute
        print("Sending workflow...")
        prompt_res = queue_prompt(api_url, workflow_data)
        if not prompt_res:
            print("Failed to queue prompt.")
            raise Exception("Queue failed")
            
        prompt_id = prompt_res.get('prompt_id')
        print(f"Workflow queued (ID: {prompt_id}). Waiting for completion...")
        
        # Poll for completion
        while True:
            history = get_history(api_url, prompt_id)
            if history and prompt_id in history:
                print("Job completed!")
                
                # Check outputs using simple requests (fetching generated images)
                # Ideally, we parse the outputs. 
                outputs = history[prompt_id]['outputs']
                for node_id, node_output in outputs.items():
                    if 'images' in node_output:
                        for image in node_output['images']:
                            filename = image['filename']
                            type_ = image['type']
                            subfolder = image['subfolder']
                            
                            # Construct URL
                            # /view?filename=...
                            file_url = f"{api_url}/view?filename={filename}&type={type_}&subfolder={subfolder}"
                            print(f"Downloading {filename}...")
                            
                            # Download
                            output_dir = "vast_outputs"
                            os.makedirs(output_dir, exist_ok=True)
                            urlretrieve(file_url, os.path.join(output_dir, filename))
                break
                
            print(".", end="", flush=True)
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\nAborted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if not args.keep_alive:
            clean_and_exit(instance_id)
        else:
            print(f"Instance {instance_id} kept alive. Remember to destroy it manually!")

if __name__ == "__main__":
    main()
