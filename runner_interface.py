"""
runner_interface.py — v2.0 Professional Backend
================================================
Smart Vast.ai integration with real CLI polling, 
6-step pipeline progress, and live instance metrics.
"""

import json
import os
import sys
import subprocess
import threading
import time
import traceback
from datetime import datetime
from sync_local_to_drive import sync_models as do_sync_models

# ─── Config ───────────────────────────────────────────
CONFIG_FILE = "launcher_config.json"
COMFYUI_PORT = 8188

# ─── Pipeline Steps ──────────────────────────────────
STEPS = [
    "Sync Models",
    "Search GPU",
    "Create Instance",
    "Loading Docker",
    "Connecting",
    "Ready"
]

STEP_SYNC       = 0
STEP_SEARCH     = 1
STEP_CREATE     = 2
STEP_LOADING    = 3
STEP_CONNECTING = 4
STEP_READY      = 5


class InstanceInfo:
    """Live instance metadata."""
    def __init__(self):
        self.id = None
        self.gpu_name = ""
        self.gpu_ram = 0
        self.dph_total = 0.0       # $/hr
        self.actual_status = ""     # creating, loading, connecting, running
        self.ssh_host = ""
        self.ssh_port = ""
        self.url = ""
        self.reliability = 0.0
        self.inet_down = 0.0
        self.disk_space = 0.0
        self.start_time = None
        self.cost_so_far = 0.0
    
    def uptime_str(self):
        if not self.start_time:
            return "00:00:00"
        elapsed = time.time() - self.start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    def update_cost(self):
        if self.start_time and self.dph_total > 0:
            elapsed_hrs = (time.time() - self.start_time) / 3600
            self.cost_so_far = elapsed_hrs * self.dph_total
    
    def to_dict(self):
        self.update_cost()
        return {
            "id": self.id,
            "gpu": self.gpu_name,
            "gpu_ram": f"{self.gpu_ram:.0f}GB",
            "price": f"${self.dph_total:.3f}/hr",
            "status": self.actual_status,
            "uptime": self.uptime_str(),
            "cost": f"${self.cost_so_far:.4f}",
            "reliability": f"{self.reliability:.1%}",
            "download": f"{self.inet_down:.0f} Mb/s",
            "disk": f"{self.disk_space:.0f}GB",
            "url": self.url,
        }


class VastRunnerInterface:
    """
    Professional backend for ComfyUI-VastAI Launcher.
    Provides real-time pipeline progress and instance monitoring.
    """
    
    def __init__(self):
        self.config = self.load_config()
        self.instance = InstanceInfo()
        self._polling = False
        self._poll_thread = None
        
        # Callbacks (set by the UI)
        self.on_log = None            # (message, severity) → severity: info/success/warning/error/progress
        self.on_step = None           # (step_index, status, detail) → status: active/done/error/pending
        self.on_instance_update = None  # (instance_info_dict)
        self.on_status_change = None  # (status_string) e.g. "OFFLINE", "RUNNING"

    # ─── Config ─────────────────────────────────────

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_config(self, cfg_dict):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg_dict, f, indent=2)
        self.config = cfg_dict
        self.log("Config saved.", "success")

    def apply_env(self):
        """Push config to env vars and Vast CLI."""
        api_key = self.config.get("api_key", "")
        if api_key:
            os.environ["VAST_API_KEY"] = api_key
            os.environ["GDRIVE_FOLDER_ID"] = self.config.get("gdrive_id", "")
            os.environ["VAST_GPU"] = self.config.get("gpu", "RTX_3090")
            os.environ["VAST_PRICE"] = str(self.config.get("price", "0.5"))
            
            try:
                subprocess.run(
                    ["vastai", "set", "api-key", api_key],
                    shell=True, capture_output=True, timeout=10
                )
            except:
                pass

    # ─── Logging ────────────────────────────────────

    def log(self, message, severity="info"):
        """Send a log entry to the UI. severity: info/success/warning/error/progress"""
        if self.on_log:
            self.on_log(message, severity)
        else:
            print(f"[{severity.upper()}] {message}")

    def set_step(self, step_index, status, detail=""):
        """Update pipeline step. status: active/done/error/pending"""
        if self.on_step:
            self.on_step(step_index, status, detail)

    def set_status(self, status):
        """Set global status: OFFLINE, SYNCING, SEARCHING, LOADING, CONNECTING, RUNNING, ERROR"""
        if self.on_status_change:
            self.on_status_change(status)

    def push_instance_info(self):
        """Push live instance metrics to UI."""
        if self.on_instance_update:
            self.on_instance_update(self.instance.to_dict())

    # ─── Step 1: Sync Models ────────────────────────

    def sync_to_drive(self):
        """Sync local models to Google Drive."""
        self.set_step(STEP_SYNC, "active", "Checking paths...")
        self.set_status("SYNCING")
        
        local_models = self.config.get("local_path", "")
        drive_models = self.config.get("drive_models_path", "")
        
        if not local_models or not drive_models:
            self.log("Sync skipped: paths not configured", "warning")
            self.set_step(STEP_SYNC, "done", "Skipped (no paths)")
            return True
        
        # Derive models folder from bat path
        comfy_dir = os.path.dirname(local_models)
        possible_models = os.path.join(comfy_dir, "ComfyUI", "models")
        if not os.path.exists(possible_models):
            possible_models = os.path.join(comfy_dir, "models")
        if not os.path.exists(possible_models):
            self.log(f"Models folder not found near: {local_models}", "warning")
            self.set_step(STEP_SYNC, "done", "Skipped (folder not found)")
            return True  # Don't block cloud launch
        
        self.log(f"Syncing: {possible_models} → {drive_models}", "info")
        self.set_step(STEP_SYNC, "active", "Copying files...")
        
        try:
            copied, skipped, total_bytes = do_sync_models(
                possible_models, drive_models, 
                log_callback=lambda msg: self.log(msg, "info")
            )
            size_mb = total_bytes / (1024 * 1024) if total_bytes else 0
            if copied == 0:
                self.set_step(STEP_SYNC, "done", "Already up to date ✓")
                self.log("Drive is already up to date!", "success")
            else:
                self.set_step(STEP_SYNC, "done", f"{copied} files ({size_mb:.0f}MB)")
                self.log(f"Synced {copied} files ({size_mb:.0f}MB)", "success")
            return True
        except Exception as e:
            self.log(f"Sync error: {e}", "error")
            self.set_step(STEP_SYNC, "error", str(e))
            return True  # Continue anyway

    # ─── Step 2: Search GPU ─────────────────────────

    def search_gpus(self):
        """Search Vast.ai for available GPUs matching criteria."""
        self.set_step(STEP_SEARCH, "active", "Querying marketplace...")
        self.set_status("SEARCHING")
        
        gpu = self.config.get("gpu", "RTX_3090")
        max_price = float(self.config.get("price", "0.5"))
        
        query = f"gpu_name={gpu} rentable=true reliability>0.90 num_gpus=1 dph<={max_price}"
        
        self.log(f"Searching: {gpu} ≤${max_price}/hr, reliability>90%", "info")
        
        try:
            result = subprocess.run(
                ["vastai", "search", "offers", query, "-o", "dph", "--raw"],
                capture_output=True, text=True, shell=True, timeout=30
            )
            
            if result.returncode != 0:
                self.log(f"Search failed: {result.stderr}", "error")
                self.set_step(STEP_SEARCH, "error", "CLI error")
                return None
            
            offers = json.loads(result.stdout)
            
            if not offers:
                self.log(f"No {gpu} available ≤${max_price}/hr. Try higher price or different GPU.", "error")
                self.set_step(STEP_SEARCH, "error", "No offers found")
                return None
            
            best = offers[0]
            self.log(
                f"Found {len(offers)} offer(s). Best: ${best.get('dph_total', 0):.3f}/hr, "
                f"reliability {best.get('reliability', 0):.1%}, "
                f"↓{best.get('inet_down', 0):.0f}Mb/s, "
                f"{best.get('disk_space', 0):.0f}GB disk",
                "success"
            )
            self.set_step(STEP_SEARCH, "done", f"{len(offers)} offers, best ${best.get('dph_total', 0):.3f}/hr")
            
            return best
            
        except json.JSONDecodeError:
            self.log("Could not parse GPU search results", "error")
            self.set_step(STEP_SEARCH, "error", "Parse error")
            return None
        except Exception as e:
            self.log(f"Search error: {e}", "error")
            self.set_step(STEP_SEARCH, "error", str(e))
            return None

    # ─── Step 3: Create Instance ────────────────────

    def create_instance(self, offer):
        """Create a Vast.ai instance from the selected offer."""
        self.set_step(STEP_CREATE, "active", "Renting GPU...")
        
        offer_id = offer.get("id")
        gdrive_id = self.config.get("gdrive_id", "")
        
        # Build the onstart command
        onstart_parts = [
            "pip install -q gdown requests",
            "apt-get update -qq && apt-get install -y -qq git > /dev/null 2>&1",
        ]
        
        # Lazy model loader
        loader_url = "https://raw.githubusercontent.com/galhosostore-coder/ComfyUI-VastAI/main/lazy_model_loader.py"
        onstart_parts.append(f"cd /app && curl -sL '{loader_url}' -o lazy_model_loader.py")
        
        if gdrive_id:
            onstart_parts.append(f"cd /app && python lazy_model_loader.py {gdrive_id}")
        else:
            onstart_parts.append("cd /app && python main.py --listen 0.0.0.0 --port 8188")
        
        onstart_cmd = " && ".join(onstart_parts)
        
        self.log(f"Creating instance from offer #{offer_id}...", "info")
        
        try:
            cmd = [
                "vastai", "create", "instance", str(offer_id),
                "--image", "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
                "--disk", "40",
                "--onstart-cmd", onstart_cmd,
                "--direct",
                "--env", f"-e GDRIVE_FOLDER_ID={gdrive_id} -p 8188:8188",
                "--raw"
            ]
            
            result = subprocess.run(
                cmd, capture_output=True, text=True, shell=True, timeout=30
            )
            
            if result.returncode != 0:
                self.log(f"Create failed: {result.stderr}", "error")
                self.set_step(STEP_CREATE, "error", "Creation failed")
                return None
            
            response = json.loads(result.stdout)
            instance_id = response.get("new_contract")
            
            if not instance_id:
                self.log(f"Unexpected response: {result.stdout}", "error")
                self.set_step(STEP_CREATE, "error", "No instance ID returned")
                return None
            
            self.instance.id = instance_id
            self.instance.gpu_name = offer.get("gpu_name", "Unknown")
            self.instance.gpu_ram = offer.get("gpu_ram", 0)
            self.instance.dph_total = offer.get("dph_total", 0)
            self.instance.reliability = offer.get("reliability", 0)
            self.instance.inet_down = offer.get("inet_down", 0)
            self.instance.disk_space = offer.get("disk_space", 0)
            self.instance.start_time = time.time()
            self.instance.actual_status = "creating"
            
            self.log(f"Instance #{instance_id} created! GPU: {self.instance.gpu_name}", "success")
            self.set_step(STEP_CREATE, "done", f"ID #{instance_id}")
            self.push_instance_info()
            
            return instance_id
            
        except Exception as e:
            self.log(f"Create error: {e}", "error")
            self.set_step(STEP_CREATE, "error", str(e))
            return None

    # ─── Steps 4-6: Poll Instance Status ────────────

    def poll_instance_until_ready(self, instance_id):
        """Poll `vastai show instance <id> --raw` until RUNNING or ERROR."""
        self.set_step(STEP_LOADING, "active", "Waiting for Docker image...")
        self.set_status("LOADING")
        self.log("Instance is loading Docker image (you are NOT charged during loading)", "info")
        
        max_wait = 600  # 10 minutes max
        start = time.time()
        last_status = ""
        
        while time.time() - start < max_wait:
            try:
                result = subprocess.run(
                    ["vastai", "show", "instance", str(instance_id), "--raw"],
                    capture_output=True, text=True, shell=True, timeout=15
                )
                
                if result.returncode != 0:
                    time.sleep(5)
                    continue
                
                data = json.loads(result.stdout)
                
                # Handle both dict and list responses
                if isinstance(data, list):
                    if not data:
                        time.sleep(5)
                        continue
                    data = data[0]
                
                status = data.get("actual_status", "unknown")
                self.instance.actual_status = status
                
                # Update instance info from poll data
                if data.get("gpu_name"):
                    self.instance.gpu_name = data["gpu_name"]
                if data.get("dph_total"):
                    self.instance.dph_total = data["dph_total"]
                
                self.push_instance_info()
                
                if status != last_status:
                    elapsed = int(time.time() - start)
                    self.log(f"Status: {status} ({elapsed}s elapsed)", "progress")
                    last_status = status
                
                if status == "loading":
                    pct = min(90, int((time.time() - start) / max_wait * 100))
                    self.set_step(STEP_LOADING, "active", f"Pulling Docker image... {elapsed}s")
                    self.set_status("LOADING")
                    
                elif status == "connecting":
                    self.set_step(STEP_LOADING, "done", f"Image pulled ({elapsed}s)")
                    self.set_step(STEP_CONNECTING, "active", "Establishing connection...")
                    self.set_status("CONNECTING")
                
                elif status == "running":
                    # Extract URL from ports
                    ports = data.get("ports", {})
                    public_ip = data.get("public_ipaddr", "")
                    
                    if "8188/tcp" in ports:
                        port_info = ports["8188/tcp"]
                        if isinstance(port_info, list) and port_info:
                            host_port = port_info[0].get("HostPort", COMFYUI_PORT)
                            self.instance.url = f"http://{public_ip}:{host_port}"
                        else:
                            self.instance.url = f"http://{public_ip}:{COMFYUI_PORT}"
                    elif public_ip:
                        self.instance.url = f"http://{public_ip}:{COMFYUI_PORT}"
                    
                    self.set_step(STEP_LOADING, "done", "✓")
                    self.set_step(STEP_CONNECTING, "done", "✓")
                    self.set_step(STEP_READY, "active", "Waiting for ComfyUI startup...")
                    self.set_status("CONNECTING")
                    
                    # Wait for ComfyUI to actually respond
                    if self._wait_for_comfyui():
                        self.set_step(STEP_READY, "done", self.instance.url)
                        self.set_status("RUNNING")
                        self.instance.actual_status = "running"
                        self.instance.start_time = time.time()  # Reset for cost from "running"
                        self.push_instance_info()
                        self.log(f"ComfyUI is READY at {self.instance.url}", "success")
                        
                        # Start background metrics poller
                        self._start_metrics_polling()
                        return True
                    else:
                        self.log("ComfyUI didn't respond in time, but instance is running", "warning")
                        self.set_step(STEP_READY, "done", f"Running (port may need time)")
                        self.set_status("RUNNING")
                        self.push_instance_info()
                        self._start_metrics_polling()
                        return True
                
                elif status in ("exited", "error", "offline"):
                    self.log(f"Instance failed with status: {status}", "error")
                    self.set_step(STEP_LOADING, "error", status)
                    self.set_status("ERROR")
                    return False
                
            except json.JSONDecodeError:
                pass
            except Exception as e:
                self.log(f"Poll error: {e}", "warning")
            
            time.sleep(5)
        
        self.log("Timeout waiting for instance (10 minutes)", "error")
        self.set_status("ERROR")
        return False
    
    def _wait_for_comfyui(self, timeout=120):
        """Wait for ComfyUI HTTP endpoint to respond."""
        import urllib.request
        
        if not self.instance.url:
            return False
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                req = urllib.request.urlopen(self.instance.url, timeout=5)
                if req.status == 200:
                    return True
            except:
                pass
            
            elapsed = int(time.time() - start)
            self.set_step(STEP_READY, "active", f"ComfyUI starting... {elapsed}s")
            time.sleep(5)
        
        return False

    # ─── Metrics Polling ────────────────────────────

    def _start_metrics_polling(self):
        """Background thread to update instance metrics every 5s."""
        self._polling = True
        
        def poll_loop():
            while self._polling and self.instance.id:
                try:
                    self.instance.update_cost()
                    self.push_instance_info()
                    
                    # Also check if instance is still running
                    result = subprocess.run(
                        ["vastai", "show", "instance", str(self.instance.id), "--raw"],
                        capture_output=True, text=True, shell=True, timeout=10
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if isinstance(data, list) and data:
                            data = data[0]
                        status = data.get("actual_status", "")
                        if status in ("exited", "offline", "error"):
                            self.log(f"Instance went {status}!", "error")
                            self.set_status("ERROR")
                            self._polling = False
                            break
                except:
                    pass
                
                time.sleep(10)
        
        self._poll_thread = threading.Thread(target=poll_loop, daemon=True)
        self._poll_thread.start()

    # ─── Instance Logs ──────────────────────────────

    def get_instance_logs(self):
        """Fetch container logs from the running instance."""
        if not self.instance.id:
            return "No instance running."
        
        try:
            result = subprocess.run(
                ["vastai", "logs", str(self.instance.id), "--tail", "100"],
                capture_output=True, text=True, shell=True, timeout=15
            )
            return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
        except Exception as e:
            return f"Error fetching logs: {e}"

    # ─── Full Cloud Launch Pipeline ─────────────────

    def launch_cloud(self):
        """Execute the full 6-step cloud launch pipeline."""
        try:
            self.apply_env()
            
            # Reset all steps to pending
            for i in range(len(STEPS)):
                self.set_step(i, "pending")
            
            # Step 1: Sync
            self.sync_to_drive()
            
            # Step 2: Search
            offer = self.search_gpus()
            if not offer:
                self.set_status("ERROR")
                return False
            
            # Step 3: Create
            instance_id = self.create_instance(offer)
            if not instance_id:
                self.set_status("ERROR")
                return False
            
            # Steps 4-6: Poll until ready
            success = self.poll_instance_until_ready(instance_id)
            return success
            
        except Exception as e:
            self.log(f"Pipeline error: {traceback.format_exc()}", "error")
            self.set_status("ERROR")
            return False

    # ─── Local Launch ───────────────────────────────

    def start_local(self, local_path):
        """Launch local ComfyUI."""
        if not os.path.exists(local_path):
            self.log(f"Local path not found: {local_path}", "error")
            return False
        
        self.log(f"Starting local ComfyUI: {local_path}", "info")
        self.set_status("LOCAL")
        
        try:
            working_dir = os.path.dirname(local_path)
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
                self.log(f"Process exited with code {self.process.returncode}", "error")
                return False
            
            self.instance.url = "http://127.0.0.1:8188"
            self.log("Local ComfyUI started!", "success")
            return True
            
        except Exception as e:
            self.log(f"Launch error: {e}", "error")
            return False

    # ─── Destroy ────────────────────────────────────

    def destroy_instance(self):
        """Destroy current cloud instance. Retrieves new models first."""
        if not self.instance.id:
            self.log("No instance to destroy.", "warning")
            return
        
        self._polling = False
        instance_id = self.instance.id
        
        # Step 1: Retrieve new models
        self.log("Checking for new models before destroying...", "info")
        self._retrieve_new_models(instance_id)
        
        # Step 2: Destroy
        self.log(f"Destroying instance #{instance_id}...", "info")
        try:
            result = subprocess.run(
                ["vastai", "destroy", "instance", str(instance_id)],
                capture_output=True, text=True, shell=True, timeout=15
            )
            
            if result.returncode == 0:
                cost = self.instance.cost_so_far
                self.log(f"Instance #{instance_id} destroyed. Total cost: ${cost:.4f}", "success")
            else:
                self.log(f"Destroy error: {result.stderr}", "error")
        except Exception as e:
            self.log(f"Destroy failed: {e}", "error")
        
        # Reset
        self.instance = InstanceInfo()
        self.set_status("OFFLINE")
        for i in range(len(STEPS)):
            self.set_step(i, "pending")

    def _retrieve_new_models(self, instance_id):
        """Download new models from cloud before destroying."""
        drive_models = self.config.get("drive_models_path", "")
        if not drive_models:
            return
        
        try:
            result = subprocess.run(
                ["vastai", "execute", str(instance_id),
                 "cat /app/new_models_manifest.json 2>/dev/null || echo '[]'"],
                capture_output=True, text=True, shell=True, timeout=15
            )
            
            if result.returncode == 0:
                try:
                    manifest = json.loads(result.stdout.strip())
                except:
                    manifest = []
                
                if manifest:
                    self.log(f"Found {len(manifest)} new model(s)!", "success")
                    for model in manifest:
                        rel_path = model.get("relative_path", "")
                        full_path = model.get("full_path", "")
                        size_mb = model.get("size_mb", 0)
                        
                        if not rel_path or not full_path:
                            continue
                        
                        local_dest = os.path.join(drive_models, rel_path)
                        os.makedirs(os.path.dirname(local_dest), exist_ok=True)
                        
                        self.log(f"Downloading {rel_path} ({size_mb}MB)...", "progress")
                        scp_result = subprocess.run(
                            ["vastai", "scp", f"{instance_id}:{full_path}", local_dest],
                            capture_output=True, text=True, shell=True, timeout=300
                        )
                        
                        if scp_result.returncode == 0:
                            self.log(f"Saved: {rel_path}", "success")
                        else:
                            self.log(f"Failed: {scp_result.stderr}", "error")
                else:
                    self.log("No new models to retrieve.", "info")
        except Exception as e:
            self.log(f"Model retrieval error: {e}", "warning")

    # ─── Utility ────────────────────────────────────

    def get_url(self):
        """Get the current ComfyUI URL."""
        if self.instance.url:
            return self.instance.url
        return "http://localhost:8188"
