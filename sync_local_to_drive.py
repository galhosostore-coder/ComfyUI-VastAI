"""
sync_local_to_drive.py
Incremental sync: Local ComfyUI Models → Google Drive folder.
Only copies files that are new or have a different size.
"""

import os
import shutil
import time

# Model subfolders to sync
MODEL_FOLDERS = [
    "checkpoints",
    "clip",
    "clip_vision",
    "configs",
    "controlnet",
    "diffusers",
    "diffusion_models",
    "embeddings",
    "gligen",
    "hypernetworks",
    "latent_upscale_models",
    "loras",
    "model_patches",
    "photomaker",
    "style_models",
    "text_encoders",
    "unet",
    "upscale_models",
    "vae",
    "vae_approx",
    "audio_encoders",
]


def get_file_list(base_path):
    """Walk directory and return dict of {relative_path: file_size}."""
    files = {}
    if not os.path.exists(base_path):
        return files
    for root, dirs, filenames in os.walk(base_path):
        for fname in filenames:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, base_path)
            try:
                files[rel] = os.path.getsize(full)
            except OSError:
                pass
    return files


def sync_models(local_models_path, drive_models_path, log_callback=None, folders=None):
    """
    Sync models from local to drive.
    Returns (copied_count, skipped_count, total_size_bytes).
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not os.path.exists(local_models_path):
        log(f"Error: Local path not found: {local_models_path}")
        return 0, 0, 0

    # Create drive root if needed
    os.makedirs(drive_models_path, exist_ok=True)

    target_folders = folders or MODEL_FOLDERS
    
    copied = 0
    skipped = 0
    total_bytes = 0
    
    log(f"Scanning local models: {local_models_path}")
    
    for folder in target_folders:
        local_folder = os.path.join(local_models_path, folder)
        drive_folder = os.path.join(drive_models_path, folder)
        
        if not os.path.exists(local_folder):
            continue
        
        # Get local files
        local_files = get_file_list(local_folder)
        
        if not local_files:
            continue
            
        # Get drive files
        drive_files = get_file_list(drive_folder)
        
        log(f"[{folder}] {len(local_files)} files locally, {len(drive_files)} on Drive")
        
        for rel_path, local_size in local_files.items():
            drive_size = drive_files.get(rel_path)
            
            if drive_size == local_size:
                skipped += 1
                continue
            
            # File is new or different size -> copy
            src = os.path.join(local_folder, rel_path)
            dst = os.path.join(drive_folder, rel_path)
            
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            
            size_mb = local_size / (1024 * 1024)
            action = "NEW" if drive_size is None else "UPDATE"
            log(f"  [{action}] {rel_path} ({size_mb:.1f} MB)")
            
            try:
                shutil.copy2(src, dst)
                copied += 1
                total_bytes += local_size
            except Exception as e:
                log(f"  ERROR copying {rel_path}: {e}")
    
    # Check for files on Drive that are NOT on local (orphans)
    # We don't delete them automatically to be safe, just warn.
    for folder in target_folders:
        local_folder = os.path.join(local_models_path, folder)
        drive_folder = os.path.join(drive_models_path, folder)
        
        if not os.path.exists(drive_folder):
            continue
            
        local_files = get_file_list(local_folder)
        drive_files = get_file_list(drive_folder)
        
        for rel_path in drive_files:
            if rel_path not in local_files:
                log(f"  [ORPHAN] {folder}/{rel_path} exists on Drive but not locally")

    total_mb = total_bytes / (1024 * 1024)
    log(f"Sync complete: {copied} copied, {skipped} skipped, {total_mb:.1f} MB transferred")
    
    return copied, skipped, total_bytes


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python sync_local_to_drive.py <local_models_path> <drive_models_path>")
        print("Example: python sync_local_to_drive.py A:\\ComfyUI\\models G:\\Meu Drive\\ComfyUI\\models")
        sys.exit(1)
    
    local = sys.argv[1]
    drive = sys.argv[2]
    
    print(f"Syncing: {local} -> {drive}")
    start = time.time()
    c, s, b = sync_models(local, drive)
    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")
