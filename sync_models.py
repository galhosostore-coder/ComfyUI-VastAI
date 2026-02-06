import os
import sys
import subprocess

# Standard ComfyUI model folder structure
MODEL_MAP = {
    "checkpoints": "models/checkpoints",
    "loras": "models/loras",
    "vae": "models/vae",
    "controlnet": "models/controlnet",
    "upscale_models": "models/upscale_models",
    "embeddings": "models/embeddings",
    "clip": "models/clip",
    "unet": "models/unet",
    "clip_vision": "models/clip_vision"
}

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

def list_gdrive_recursive(folder_id):
    import gdown
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        # gdown returns list of objects with .path and .url
        files = gdown.download_folder(url, skip_download=True, quiet=True, use_cookies=False)
        paths = []
        for f in files:
            if hasattr(f, 'path'):
                # Clean path: remove leading ./ or / and backslashes
                clean = f.path.replace('\\', '/').lstrip('./')
                paths.append(clean)
        return paths
    except Exception as e:
        print(f"⚠️ Error scanning Drive: {e}")
        return []

def main():
    folder_id = get_env("GDRIVE_FOLDER_ID")
    if not folder_id:
        print("⚠️ GDRIVE_FOLDER_ID not set. Skipping model sync.")
        return

    install_gdown()
    
    print(f"🔄 Syncing model list from Google Drive ({folder_id})...")
    files = list_gdrive_recursive(folder_id)
    
    count = 0
    for file_path in files:
        # file_path example: "checkpoints/sd_xl.safetensors"
        parts = file_path.split('/')
        if len(parts) < 2:
            continue
            
        category = parts[0].lower()
        filename = parts[-1]
        
        # Remap categories that don't match exactly
        if category == "text_encoders": category = "clip"
        elif category == "diffusion_models": category = "unet"
        
        if category in MODEL_MAP:
            local_dir = MODEL_MAP[category]
            local_path = os.path.join("/app", local_dir, filename)
            touch_file(local_path)
            count += 1
            
    print(f"✅ Synced {count} dummy models. They will appear in ComfyUI menus.")

if __name__ == "__main__":
    main()
