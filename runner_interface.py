import json
import os
import sys
import subprocess
import threading
import time
import requests
from sync_local_to_drive import sync_models as do_sync_models

# CONFIG FILE
CONFIG_FILE = "launcher_config.json"

class VastRunnerInterface:
    def __init__(self):
        self.config = self.load_config()
        self.current_instance_id = None
        self.current_ip = None
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_config(self, api_key, gdrive_id, gpu="RTX_3090", price="0.5", local_path="", drive_models_path=""):
        cfg = {
            "api_key": api_key,
            "gdrive_id": gdrive_id,
            "gpu": gpu,
            "price": price,
            "local_path": local_path,
            "drive_models_path": drive_models_path
        }
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f)
        self.config = cfg
        print("Config saved.")

    def set_config(self, api_key, gdrive_id, gpu, price, local_path, drive_models_path):
        self.save_config(api_key, gdrive_id, gpu, price, local_path, drive_models_path)
        # Set Env vars for subprocesses
        os.environ["VAST_API_KEY"] = api_key
        os.environ["GDRIVE_FOLDER_ID"] = gdrive_id
        os.environ["VAST_GPU"] = gpu
        os.environ["VAST_PRICE"] = str(price)
        
        # Configure Vast CLI
        if api_key:
            subprocess.run(["vastai", "set", "api-key", api_key], shell=True)

    def sync_to_drive(self, log_callback=None):
        """Sync local models to Google Drive before cloud start."""
        local_models = self.config.get("local_path", "")
        drive_models = self.config.get("drive_models_path", "")
        
        if not local_models or not drive_models:
            self.log("Skipping sync: Local or Drive path not configured.", log_callback)
            return False
        
        # Derive local models path from the ComfyUI bat file path
        # e.g. A:\ComfyUI_windows_portable\run_nvidia_gpu.bat -> A:\ComfyUI_windows_portable\ComfyUI\models
        comfy_dir = os.path.dirname(local_models)
        possible_models = os.path.join(comfy_dir, "ComfyUI", "models")
        if not os.path.exists(possible_models):
            # Maybe the path IS the models folder directly, or try parent
            possible_models = os.path.join(comfy_dir, "models")
        if not os.path.exists(possible_models):
            self.log(f"Could not find models folder near: {local_models}", log_callback)
            return False
        
        self.log(f"Syncing: {possible_models} -> {drive_models}", log_callback)
        
        try:
            copied, skipped, total_bytes = do_sync_models(possible_models, drive_models, log_callback=log_callback)
            if copied == 0:
                self.log("Drive is already up to date!", log_callback)
            return True
        except Exception as e:
            self.log(f"Sync error: {e}", log_callback)
            return False

    def log(self, msg, callback):
        if callback:
            callback(msg)
        else:
            print(msg)

    def start_local(self, local_path, log_callback=None):
        if not os.path.exists(local_path):
            self.log(f"❌ Error: Local path not found: {local_path}", log_callback)
            return False
            
        self.log(f"🏠 Starting Local ComfyUI: {local_path}", log_callback)
        
        try:
            working_dir = os.path.dirname(local_path)
            
            # Use Shell=True to run batch files properly
            self.process = subprocess.Popen(
                f'"{local_path}"', 
                shell=True,
                cwd=working_dir,
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                universal_newlines=True
            )
            
            time.sleep(2)
            if self.process.poll() is not None:
                    self.log(f"❌ Error: Process exited with code {self.process.returncode}", log_callback)
                    return False
                    
            self.log("✅ Local ComfyUI started!", log_callback)
            return True
            
        except Exception as e:
            self.log(f"❌ Exception: {e}", log_callback)
            return False

    def start_instance(self, log_callback=None):
        """Runs the run_workflow logic via subprocess to capture output."""
        # Step 1: Sync models to Drive first
        self.log("📦 Step 1/2: Syncing models to Drive...", log_callback)
        self.sync_to_drive(log_callback=log_callback)
        
        # Step 2: Start cloud instance
        self.log("🚀 Step 2/2: Initializing cloud runner...", log_callback)
        
        # We run the runner with a dummy workflow or just to start
        # Since the runner expects a workflow file, we might need a 'start only' mode or dummy.
        # Let's create a temporary dummy workflow if none exists.
        dummy_wf = "temp_launcher_workflow.json"
        if not os.path.exists(dummy_wf):
            with open(dummy_wf, 'w') as f:
                json.dump({"3": {"class_type": "KSampler"}}, f) # Minimal valid-ish JSON
        
        cmd = [
            "python", "vastai_runner.py", 
            "--workflow", "examples/simple_txt2img.json",
            "--keep-alive" # Crucial so it doesn't destroy immediately
        ]
        
        self.log(f"📝 Command: {' '.join(cmd)}", log_callback)
        
        # Prepare environment with UTF-8 enforcement
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            bufsize=1,
            universal_newlines=True,
            env=env
        )
        
        instance_id = None
        url = None
        
        # Stream output
        for line in process.stdout:
            line = line.strip()
            if line:
                self.log(line, log_callback)
                
                # Setup URL detection
                if "Instance is RUNNING at" in line:
                    url = line.split("at")[-1].strip()
                    self.current_ip = url
                
                # Setup ID detection if possible (runner needs to print it clearly)
                if "Instance ID:" in line:
                    parts = line.split("Instance ID:")
                    if len(parts) > 1:
                        instance_id = parts[1].strip()
                        self.current_instance_id = instance_id

        process.wait()
        
        if process.returncode == 0:
            self.log("✅ Sequence completed successfully.", log_callback)
            return True
        else:
            stderr = process.stderr.read()
            self.log(f"❌ Error: {stderr}", log_callback)
            return False

    def stop_all(self, log_callback=None):
        self.log("🛑 Sending stop command...", log_callback)
        cmd = ["python", "vastai_runner.py", "--stop"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.log(result.stdout, log_callback)
        if result.stderr:
             self.log(f"Errors: {result.stderr}", log_callback)

    def get_current_url(self):
        # Fallback: query vastai if we don't have it in memory
        if self.current_ip: 
            return self.current_ip
        
        # Try to find via CLI
        try:
            res = subprocess.run(["vastai", "show", "instances", "--raw"], capture_output=True, text=True)
            data = json.loads(res.stdout)
            if data:
                # Get first running
                 for i in data:
                     if i['actual_status'] == 'running':
                        # Parse ports
                        ports = i.get('ports', {})
                        if '8188/tcp' in ports:
                             mapping = ports['8188/tcp'][0]
                             return f"http://{mapping['HostIp']}:{mapping['HostPort']}"
        except:
            pass
        return "http://localhost:8188" # Fallback

    def sync_models(self, log_callback=None):
        self.log("🔄 Triggering manual model sync...", log_callback)
        # This one is tricky if we are on local Windows and want to sync GDrive? 
        # Actually vastai_runner only runs sync inside the container. 
        # The user presumably wants to sync the REMOTE instance.
        # But we can't easily run a command inside the remote instance from here unless we use ssh.
        # OR we just rely on "Sync Now" button in the ComfyUI browser.
        
        self.log("ℹ️  To sync models, please use the 'Sync Now' button inside ComfyUI.", log_callback)
        self.log("    (The runner syncs automatically on start).", log_callback)
