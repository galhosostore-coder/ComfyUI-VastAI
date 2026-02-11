import os
import sys
import subprocess
import json
import time
import argparse

# Standard ComfyUI model folder structure (matches ai-dock container paths)
MODEL_MAP = {
    "checkpoints": "models/checkpoints",
    "clip": "models/clip",
    "clip_vision": "models/clip_vision",
    "configs": "models/configs",
    "controlnet": "models/controlnet",
    "diffusers": "models/diffusers",
    "diffusion_models": "models/diffusion_models",
    "embeddings": "models/embeddings",
    "gligen": "models/gligen",
    "hypernetworks": "models/hypernetworks",
    "latent_upscale_models": "models/latent_upscale_models",
    "loras": "models/loras",
    "model_patches": "models/model_patches",
    "photomaker": "models/photomaker",
    "style_models": "models/style_models",
    "text_encoders": "models/text_encoders",
    "unet": "models/unet",
    "upscale_models": "models/upscale_models",
    "vae": "models/vae",
    "vae_approx": "models/vae_approx",
    "audio_encoders": "models/audio_encoders",
}

CACHE_FILE = "/workspace/ComfyUI/.drive_cache.json"
CACHE_TTL = 3600  # 1 hour


def install_gdown():
    try:
        import gdown
    except ImportError:
        print("🔧 Installing gdown for model syncing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown", "--quiet"])

def get_env(key):
    return os.environ.get(key)

def touch_file(path):
    """Create an empty file if it doesn't exist."""
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                pass # Create empty file
            print(f"   ➕ Created dummy: {path}")
        except Exception as e:
            print(f"   ❌ Failed to create {path}: {e}")

def list_gdrive_recursive_api(folder_id):
    """
    Actual API or gdown call to list files.
    """
    import gdown
    print("cloud scanning...")
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        files = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
        paths = []
        for f in files:
            if hasattr(f, 'path'):
                clean = f.path.replace('\\', '/').lstrip('./')
                paths.append(clean)
        return paths
    except Exception as e:
        print(f"⚠️ Error scanning Drive: {e}")
        return []

def save_cache(folder_id, files):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'folder_id': folder_id,
                'files': files
            }, f)
    except:
        pass

def load_cache(folder_id):
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        if time.time() - cache.get('timestamp', 0) < CACHE_TTL and cache.get('folder_id') == folder_id:
            return cache.get('files', [])
    except:
        pass
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Ignore cache and force sync")
    args = parser.parse_args()

    folder_id = get_env("GDRIVE_FOLDER_ID")
    if not folder_id:
        print("⚠️ GDRIVE_FOLDER_ID not set. Skipping model sync.")
        return

    install_gdown()
    
    files = []
    
    # 1. Try Cache
    if not args.force:
        cached_files = load_cache(folder_id)
        if cached_files is not None:
            print("⚡ Using cached GDrive file list.")
            files = cached_files
            
    # 2. Fetch if no cache or forced
    if not files:
        print(f"🔄 Syncing model list from Google Drive ({folder_id})...")
        files = list_gdrive_recursive_api(folder_id)
        if files:
            save_cache(folder_id, files)
    
    # 3. Process
    if not files:
        print("⚠️ No files found (or scan failed).")
        return

    count = 0
    for file_path in files:
        parts = file_path.split('/')
        if len(parts) < 2:
            continue
            
        category = parts[0].lower()
        filename = parts[-1]
        
        if category == "text_encoders": category = "clip"
        elif category == "diffusion_models": category = "unet"
        
        if category in MODEL_MAP:
            local_dir = MODEL_MAP[category]
            local_path = os.path.join("/app", local_dir, filename)
            touch_file(local_path)
            count += 1
            
    print(f"✅ Synced {count} dummy models.")

if __name__ == "__main__":
    main()
