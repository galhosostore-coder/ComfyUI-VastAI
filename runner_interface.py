"""
runner_interface.py — v4.0 Professional Backend
================================================
Smart Vast.ai integration with REST API, template-based
instance creation, 6-step pipeline progress, and live metrics.

v4.0: Uses official ComfyUI template via template_hash_id
  - REST API (PUT /api/v0/asks/{id}/) instead of CLI for instance creation
  - Official template includes all ports, env vars, PORTAL_CONFIG, entrypoint
  - Instance Portal + Cloudflare tunnels = automatic SSL, no URL polling needed
  - Connection flow: wait for RUNNING → open Vast.ai dashboard → click Open
"""

import json
import os
import re
import ssl
import sys
import subprocess
import threading
import time
import traceback
import urllib.request
import urllib.error
import requests
from datetime import datetime
from sync_local_to_drive import sync_models as do_sync_models

# ─── Config ───────────────────────────────────────────
CONFIG_FILE = "launcher_config.json"
COMFYUI_PORT = 8188
COMFYUI_IMAGE = "vastai/comfy"

# Official ComfyUI template hash (22k+ instances created)
# Includes: ports 1111/8080/8188/8384, Instance Portal, Cloudflare tunnels
COMFYUI_TEMPLATE_HASH = "2188dfd3e0a0b83691bb468ddae0a4e5"
VASTAI_API_BASE = "https://console.vast.ai/api/v0"

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

class SmartVastStatus:
    """
    v3.0: Analyzes raw Vast.ai status and provides heuristic progress updates.
    Solves the 'is it stuck?' problem by simulating docker pull progress.
    """
    def __init__(self):
        self.raw_status = "unknown"
        self.label = "OFFLINE"
        self.detail = ""
        self.progress = 0.0  # 0-100
        self.is_stuck = False
        self.step_start_time = 0
        self.last_status = ""

    def get_status(self):
        return self.label

    def update(self, raw_data, elapsed_total):
        status = raw_data.get("actual_status")
        if status is None:
            status = "unknown"
        
        # Reset step timer if status changes
        if status != self.last_status:
            self.step_start_time = time.time()
            self.last_status = status
            self.progress = 0.0
        
        step_elapsed = time.time() - self.step_start_time
        
        if status == "loading":
            self.label = "LOADING"
            # Heuristic: Docker pulls take 30s to 300s depending on image size/speed
            # We simulate progress to keep user engaged.
            # Fast loading curve: 0-50% in 30s, 50-80% in 60s, 80-95% in 300s
            if step_elapsed < 30:
                self.progress = (step_elapsed / 30) * 50
            elif step_elapsed < 90:
                self.progress = 50 + ((step_elapsed - 30) / 60) * 30
            else:
                self.progress = 80 + ((step_elapsed - 90) / 210) * 15
            
            self.progress = min(95.0, self.progress)
            self.detail = f"Downloading Docker Image... {self.progress:.1f}%"
            
            # Stuck detection
            if step_elapsed > 600: # 10 mins
                 self.is_stuck = True
                 self.detail = "STUCK: Docker pull taking too long (>10m)."

        elif status == "creating":
            self.label = "CREATING"
            self.detail = "Allocating resources..."
            self.progress = 10.0

        elif status == "connecting":
            self.label = "CONNECTING"
            # Heuristic: SSH handshake takes 5-30s
            self.progress = min(90.0, step_elapsed * 5) # 18s to 90%
            self.detail = "Waiting for SSH/HTTP..."
            
            if step_elapsed > 120:
                self.is_stuck = True
                self.detail = "STUCK: Container running but unreachable."

        elif status == "running":
            self.label = "RUNNING"
            self.detail = "Service is active"
            self.progress = 100.0
            self.is_stuck = False

        elif status == "offline":
             self.label = "OFFLINE"
             self.detail = "Instance is offline"
             self.progress = 0.0
        
        elif status == "exited":
             self.label = "STOPPED"
             self.detail = "Instance stopped (Storage billing active)"
             self.progress = 0.0

        else:
            self.label = status.upper()
            self.detail = f"Status: {status}"
            self.progress = 0.0
            
        return self.label, self.detail, self.progress


class InstanceInfo:
    """Live instance metadata with v3.0 cost tracking."""
    def __init__(self):
        self.id = None
        self.gpu_name = ""
        self.gpu_ram = 0
        self.dph_total = 0.0       # Running price $/hr
        self.storage_cost = 0.0    # Storage price $/hr (approx 15-20% of total usually, but fetched from offer)
        self.actual_status = ""    
        self.status = SmartVastStatus() # v3.0 Logic
        self.ssh_host = ""
        self.ssh_port = ""
        self.url = ""
        self.reliability = 0.0
        self.inet_down = 0.0
        self.disk_space = 0.0
        self.start_time = None
        self.accumulated_cost = 0.0
    
    def title(self):
        return f"ID #{self.id} • {self.gpu_name}"

    def uptime_str(self):
        if not self.start_time:
            return "00:00:00"
        elapsed = time.time() - self.start_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    def update_cost(self):
        # Simple estimation: if running, use dph_total. 
        if self.start_time and self.dph_total > 0:
            elapsed_hrs = (time.time() - self.start_time) / 3600
            self.accumulated_cost = elapsed_hrs * self.dph_total
    
    def to_dict(self):
        self.update_cost()
        return {
            "id": self.id,
            "gpu": self.gpu_name,
            "gpu_ram": f"{self.gpu_ram:.0f}GB",
            "price": f"${self.dph_total:.3f}/hr",
            "status": self.status.label,          # Smart Label
            "detail": self.status.detail,         # Smart Detail
            "progress": self.status.progress,     # Smart Progress
            "uptime": self.uptime_str(),
            "cost": f"${self.accumulated_cost:.4f}",
            "reliability": f"{self.reliability:.1%}",
            "download": f"{self.inet_down:.0f} Mb/s",
            "disk": f"{self.disk_space:.0f}GB",
            "url": self.url,
            "is_stuck": self.status.is_stuck
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
                # Fix: Use string command (not list) with shell=True on Windows
                result = subprocess.run(
                    f'vastai set api-key {api_key}',
                    shell=True, capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    self.log(f"API key configured ({api_key[:4]}...{api_key[-4:]}) ✓", "success")
                else:
                    self.log(f"API key warning: {result.stderr}", "warning")
            except Exception as e:
                self.log(f"API key setup error: {e}", "warning")

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
        
        gpu_safe = gpu.replace(" ", "_").strip()
        disk_req = int(float(self.config.get("disk_size", "40")))
        
        # Optimization: Filter by Disk Size & Internet Speed (min 200Mbps for fast startup)
        # vastai search query syntax: key>=val (no spaces around operator usually safe, but check values)
        query = f"gpu_name={gpu_safe} rentable=true reliability>0.95 num_gpus=1 dph<={max_price} disk_space>={disk_req} inet_down>=200"
        
        self.log(f"Smart Search: {gpu} ≤${max_price}/hr, Disk≥{disk_req}GB, Net≥200Mb/s, Rel>95%", "info")
        
        try:
            # Sort by price (cheapest capable instance)
            cmd_str = f"vastai search offers \"{query}\" -o dph --raw"
            
            result = subprocess.run(
                cmd_str,
                capture_output=True, text=True, shell=True, timeout=30
            )
            
            if result.returncode != 0:
                self.log(f"Search failed: {result.stderr}", "error")
                self.set_step(STEP_SEARCH, "error", "CLI error")
                return None
            
            stdout = result.stdout.strip()
            # Robust JSON extraction: Find start and end of list/dict
            try:
                if "[" in stdout:
                    start = stdout.find("[")
                    end = stdout.rfind("]") + 1
                    stdout = stdout[start:end]
                elif "{" in stdout:
                    start = stdout.find("{")
                    end = stdout.rfind("}") + 1
                    stdout = stdout[start:end]
                
                offers = json.loads(stdout)
            except json.JSONDecodeError:
                self.log(f"JSON Parse Error. Raw: {result.stdout}", "error")
                self.set_step(STEP_SEARCH, "error", "Parse error")
                return None
            
            if not offers:
                # Fallback: Try relaxing internet speed constraint
                self.log("No high-speed offers found. Relaxing filters...", "warning")
                query_relaxed = f"gpu_name={gpu_safe} rentable=true reliability>0.90 num_gpus=1 dph<={max_price} disk_space>={disk_req}"
                
                cmd_relaxed = f"vastai search offers \"{query_relaxed}\" -o dph --raw"
                
                result = subprocess.run(
                    cmd_relaxed,
                    capture_output=True, text=True, shell=True
                )
                
                # Robust extraction for fallback too
                stdout_rel = result.stdout.strip()
                try:
                    if "[" in stdout_rel:
                        stdout_rel = stdout_rel[stdout_rel.find("["):stdout_rel.rfind("]")+1]
                    offers = json.loads(stdout_rel)
                except:
                    offers = []
                
                if not offers:
                    self.log(f"No {gpu} available with {disk_req}GB disk ≤${max_price}/hr.", "error")
                    self.set_step(STEP_SEARCH, "error", "No offers")
                    return None
            
            # Pick best offer (first one is cheapest due to sorting)
            best = offers[0]
            
            # Double check machine ID to avoid blacklisted hosts? (Optional)
            
            self.log(
                f"Selected Offer #{best.get('id')}: ${best.get('dph_total', '0'):.3f}/hr | "
                f"Rel: {best.get('reliability', 0):.1%} | "
                f"Down: {best.get('inet_down', 0):.0f}Mb/s | "
                f"Disk: {best.get('disk_space', 0):.0f}GB",
                "success"
            )
            self.set_step(STEP_SEARCH, "done", f"Found ${best.get('dph_total', 0):.3f}/hr")
            
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
        """Create a Vast.ai instance using the official ComfyUI template.
        
        v4.0: Uses REST API with template_hash_id instead of CLI --image.
        The template includes all ports, env vars, PORTAL_CONFIG, and onstart.
        We only overlay our PROVISIONING_SCRIPT + GDRIVE env vars if needed.
        """
        self.set_step(STEP_CREATE, "active", "Renting GPU...")
        
        offer_id = offer.get("id")
        gdrive_id = self.config.get("gdrive_id", "")
        disk_size = int(self.config.get("disk_size", "40"))
        api_key = self.config.get("api_key", os.environ.get("VAST_API_KEY", ""))
        
        self.log(f"Creating instance from offer #{offer_id}...", "info")
        
        try:
            # ── v4.0: REST API with official ComfyUI template ──
            # Template provides: image, ports, env, onstart, PORTAL_CONFIG
            # We only need to send template_hash_id + disk + optional env overlay
            
            url = f"{VASTAI_API_BASE}/asks/{offer_id}/"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            
            body = {
                "template_hash_id": COMFYUI_TEMPLATE_HASH,
                "disk": disk_size,
            }
            
            # Overlay provisioning env vars (merged with template env)
            if gdrive_id:
                provisioning_url = (
                    "https://raw.githubusercontent.com/"
                    "galhosostore-coder/ComfyUI-VastAI/main/provision.sh"
                )
                body["env"] = {
                    "PROVISIONING_SCRIPT": provisioning_url,
                    "GDRIVE_FOLDER_ID": gdrive_id,
                }
            
            self.log(f"Using official ComfyUI template ({COMFYUI_TEMPLATE_HASH[:8]}...) ✓", "success")
            self.log(f"REST API: PUT {url}", "info")
            self.log(f"Model loader: {'provision.sh' if gdrive_id else 'none'}", "info")
            
            resp = requests.put(url, json=body, headers=headers, timeout=30)
            
            if resp.status_code not in (200, 201):
                error_text = resp.text[:300]
                self.log(f"Create failed [{resp.status_code}]: {error_text}", "error")
                self.set_step(STEP_CREATE, "error", f"API error {resp.status_code}")
                return None
            
            response = resp.json()
            instance_id = response.get("new_contract")
            
            if not instance_id:
                self.log(f"No instance ID in response: {response}", "error")
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
            
        except requests.exceptions.Timeout:
            self.log("API request timed out (30s). Try again.", "error")
            self.set_step(STEP_CREATE, "error", "API timeout")
            return None
        except Exception as e:
            self.log(f"Create error: {e}", "error")
            self.set_step(STEP_CREATE, "error", str(e))
            return None

    # ─── Steps 4-6: Poll Instance Status ────────────

    def poll_instance_until_ready(self, instance_id):
        """v4.1: Poll status, then auto-discover ComfyUI URL when running.
        
        Uses official template which provides Cloudflare tunnels + Instance Portal.
        Priority: Tunnel URL → Direct HTTP → Dashboard fallback.
        """
        self.set_step(STEP_LOADING, "active", "Initializing monitoring...")
        self.set_status("LOADING")
        self.log("Instance is loading Docker image (you are NOT charged during loading)", "info")
        
        max_wait = 1800  # 30 minutes — vastai/comfy image is 8.1GB
        start = time.time()
        
        while time.time() - start < max_wait:
            try:
                result = subprocess.run(
                    f'vastai show instance {instance_id} --raw',
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
                
                # Smart Update
                elapsed_total = time.time() - start
                label, detail, progress = self.instance.status.update(data, elapsed_total)
                self.instance.actual_status = data.get("actual_status", "")
                
                # Update cost constants if available
                if data.get("dph_total"): self.instance.dph_total = data["dph_total"]
                if data.get("gpu_name"): self.instance.gpu_name = data["gpu_name"]

                self.push_instance_info()
                
                # Detailed Status Bar Update
                stuck_suffix = " (Action Required?)" if self.instance.status.is_stuck else ""
                self.set_status(f"{label}: {detail}{stuck_suffix}")

                # ─── State Handling ─────────────────────────
                
                if label == "LOADING":
                    self.set_step(STEP_LOADING, "active", detail)
                    
                elif label == "CONNECTING":
                    self.set_step(STEP_LOADING, "done", f"Image Loaded ({int(self.instance.status.step_start_time - start)}s)")
                    self.set_step(STEP_CONNECTING, "active", detail)
                
                elif label == "RUNNING":
                    # ── v4.1: Auto-discover URL → open browser automatically ──
                    self.set_step(STEP_LOADING, "done", "✓")
                    self.set_step(STEP_CONNECTING, "done", "✓")
                    self.set_step(STEP_READY, "active", "Searching for ComfyUI URL...")
                    
                    self.log(f"🟢 Instance #{instance_id} is RUNNING!", "success")
                    self.log("Searching for ComfyUI URL (tunnel → direct → portal)...", "info")
                    
                    # Try auto-discovering a working URL
                    working_url = self._find_working_url(instance_id, data)
                    
                    import webbrowser
                    
                    if working_url:
                        self.instance.url = working_url
                        self.set_step(STEP_READY, "done", "Online ✓")
                        self.set_status("RUNNING: ComfyUI Ready")
                        self.instance.start_time = time.time()
                        self.push_instance_info()
                        self.log(f"🚀 ComfyUI READY at {working_url}", "success")
                        
                        webbrowser.open(working_url)
                        self.log("Browser opened automatically!", "success")
                    else:
                        # Fallback: open Vast.ai dashboard for manual "Open" button
                        dashboard_url = "https://cloud.vast.ai/instances/"
                        self.instance.url = dashboard_url
                        
                        self.set_step(STEP_READY, "done", "Running (use Open button)")
                        self.set_status("RUNNING: ComfyUI Ready")
                        self.instance.start_time = time.time()
                        self.push_instance_info()
                        
                        self.log("Could not auto-detect URL — opening Vast.ai dashboard.", "warning")
                        self.log("Click the 'Open' button on your instance → Instance Portal → ComfyUI", "info")
                        webbrowser.open(dashboard_url)
                    
                    self._start_metrics_polling()
                    return True
                
                elif label in ("ERROR", "STOPPED", "OFFLINE"):
                    self.log(f"Instance stopped with status: {label}", "error")
                    self.set_step(STEP_LOADING, "error", label)
                    return False
                
            except json.JSONDecodeError:
                pass
            except Exception as e:
                self.log(f"Poll error: {e}", "warning")
            
            time.sleep(3)
        
        self.log("Timeout waiting for instance (30 minutes)", "error")
        self.set_status("ERROR: Timeout")
        return False
    
    def _find_working_url(self, instance_id, instance_data, timeout=300):
        """v3.4 URL finder: Direct HTTP → Tunnel → Proxy → None.
        
        Re-fetches instance data every 30s so port mappings are always fresh.
        """
        start = time.time()
        tunnel_url = None
        last_refresh = 0
        direct_urls = self._build_direct_urls(instance_data)
        proxy_url = f"https://{instance_id}-{COMFYUI_PORT}.proxy.vast.ai/"
        
        self.log(f"Direct URLs (initial): {direct_urls}", "info")
        self.log(f"Proxy URL (fallback): {proxy_url}", "info")
        self.log("Polling for ComfyUI...", "info")
        
        attempt = 0
        while time.time() - start < timeout:
            attempt += 1
            elapsed = int(time.time() - start)
            
            # ── Refresh instance data every 30s to get fresh port mappings ──
            if elapsed - last_refresh >= 30:
                last_refresh = elapsed
                fresh_data = self._refresh_instance_data(instance_id)
                if fresh_data:
                    new_urls = self._build_direct_urls(fresh_data)
                    if new_urls != direct_urls:
                        direct_urls = new_urls
                        self.log(f"Updated direct URLs: {direct_urls}", "info")
            
            # ── Tier 1: Direct HTTP URLs (best — no SSL issues) ──
            for url in direct_urls:
                if self._check_url(url):
                    self.log(f"✓ Direct HTTP connection live: {url}", "success")
                    return url
            
            # ── Tier 2: Look for Cloudflare tunnel in logs ──
            if not tunnel_url:
                tunnel_url = self._extract_tunnel_url(instance_id)
                if tunnel_url:
                    self.log(f"🔗 Found tunnel: {tunnel_url}", "success")
            
            if tunnel_url and self._check_url(tunnel_url):
                self.log("✓ Cloudflare tunnel is live!", "success")
                return tunnel_url
            
            # Status update
            self.set_step(STEP_READY, "active", f"Waiting for ComfyUI... {elapsed}s")
            
            if elapsed > 0 and elapsed % 30 == 0:
                self.log(f"Still waiting... ({elapsed}s / {timeout}s)", "info")
            
            time.sleep(5)
        
        # Timeout — try proxy as absolute last resort
        if self._check_url(proxy_url):
            self.log("⚠ Only proxy URL works (browser will show SSL warning)", "warning")
            self.log("Click 'Advanced' → 'Proceed' in the browser", "info")
            return proxy_url
        
        self.log(f"Timeout ({timeout}s). No working URL found.", "error")
        self.log(f"Tried: Direct={direct_urls}, Tunnel={tunnel_url}, Proxy={proxy_url}", "error")
        return None
    
    def _refresh_instance_data(self, instance_id):
        """Re-fetch instance data from Vast.ai API for fresh port mappings."""
        try:
            result = subprocess.run(
                f'vastai show instance {instance_id} --raw',
                capture_output=True, text=True, shell=True, timeout=15
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            if isinstance(data, list):
                data = data[0] if data else None
            return data
        except Exception:
            return None
    
    def _extract_tunnel_url(self, instance_id):
        """v3.1: Extract tunnel/proxy URL from instance logs.
        
        Searches for:
        1. Cloudflare Quick Tunnels: https://xxx.trycloudflare.com
        2. Vast.ai proxy URLs: https://xxx.vast.ai
        3. Any HTTPS URL that looks like a ComfyUI endpoint
        """
        try:
            result = subprocess.run(
                f'vastai logs {instance_id} --raw',
                shell=True, capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0 or not result.stdout:
                return None
            
            logs = result.stdout
            
            # v3.1: Pattern 1 - Cloudflare tunnel URLs
            tunnel_matches = re.findall(
                r'(https://[\w-]+\.trycloudflare\.com)', logs
            )
            if tunnel_matches:
                return tunnel_matches[-1]
            
            # v3.1: Pattern 2 - Vast.ai proxy URLs  
            proxy_matches = re.findall(
                r'(https://[\w-]+\.proxy\.vast\.ai[/\w]*)', logs
            )
            if proxy_matches:
                return proxy_matches[-1]
            
            # v3.1: Pattern 3 - Generic vast.ai URLs with port
            vast_matches = re.findall(
                r'(https://[\w-]+-\d+\.vast\.ai[/\w]*)', logs
            )
            if vast_matches:
                return vast_matches[-1]
            
            return None
        except Exception as e:
            self.log(f"Log parse error: {e}", "warning")
            return None
    
    def _build_direct_urls(self, instance_data):
        """v3.1: Build candidate URLs from instance data.
        Includes direct IP:port and Vast.ai proxy HTTPS URLs.
        """
        urls = []
        public_ip = instance_data.get("public_ipaddr", "")
        ports = instance_data.get("ports", {})
        direct_port_start = instance_data.get("direct_port_start", 0)
        
        # From ports dict (Docker port mapping)
        if ports and isinstance(ports, dict):
            for key in ["8188/tcp", "8188"]:
                if key in ports:
                    port_info = ports[key]
                    if isinstance(port_info, list) and port_info:
                        hp = port_info[0].get("HostPort", "")
                        if hp and public_ip:
                            urls.append(f"http://{public_ip}:{hp}")
        
        # Raw fallback with known port (works with --direct)
        if public_ip:
            urls.append(f"http://{public_ip}:{COMFYUI_PORT}")
        
        # Dedupe preserving order
        seen = set()
        return [u for u in urls if u not in seen and not seen.add(u)]
    
    def _check_url(self, url, timeout_sec=5):
        """v3.1: Quick HTTP/HTTPS check — returns True if URL is alive.
        Supports HTTPS with unverified certs (Vast.ai proxies use self-signed).
        """
        try:
            # v3.1: Create SSL context that doesn't verify certs for proxies
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'ComfyUI-VastAI/3.1')
            resp = urllib.request.urlopen(req, timeout=timeout_sec, context=ctx)
            return resp.status < 400
        except urllib.error.HTTPError as he:
            # 401/403 = server is UP (auth blocking)
            return he.code in (401, 403)
        except Exception:
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
                        f'vastai show instance {self.instance.id} --raw',
                        capture_output=True, text=True, shell=True, timeout=10
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if isinstance(data, list) and data:
                            data = data[0]
                        
                        # Update status object
                        self.instance.status.update(data, 0) # Elapsed not tracked here accurately but ok for polling
                        status = data.get("actual_status", "")
                        
                        if status in ("exited", "offline", "error"):
                            self.log(f"Instance went {status}!", "error")
                            self.set_status(f"ERROR: {status}")
                            self._polling = False
                            break
                except:
                    pass
                
                time.sleep(10)
        
        self._poll_thread = threading.Thread(target=poll_loop, daemon=True)
        self._poll_thread.start()

    def get_detailed_events(self):
        """v3.0: Fetch system events for the troubleshooting tab."""
        # In a real app we might parse 'vastai logs' for system messages
        # For now we return the SmartStatus detail history if we tracked it,
        # or just the current status detail.
        return [
            f"[{time.strftime('%H:%M:%S')}] {self.instance.status.label}: {self.instance.status.detail}"
        ]

    # ─── Instance Logs ──────────────────────────────

    def get_instance_logs(self):
        """Fetch container logs from the running instance."""
        if not self.instance.id:
            return "No instance running."
        
        try:
            result = subprocess.run(
                f'vastai logs {self.instance.id} --tail 100',
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
            
            # Parallel Execution: Sync & Search
            from concurrent.futures import ThreadPoolExecutor
            
            self.log("Starting parallel sync & search...", "info")
            offer = None
            
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_sync = executor.submit(self.sync_to_drive)
                future_search = executor.submit(self.search_gpus)
                
                # Search returns offer
                try:
                    offer = future_search.result()
                    # Wait for sync
                    future_sync.result()
                except Exception as e:
                    self.log(f"Parallel execution error: {e}", "error")
                    return False

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
            # Windows: Create new console to prevent pipe deadlock
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
            
            self.process = subprocess.Popen(
                f'"{local_path}"',
                shell=True,
                cwd=working_dir,
                creationflags=flags
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

    # ─── Stop Local ─────────────────────────────────
    def stop_local(self):
        """Stop the local ComfyUI process."""
        if self.process:
            self.log("Stopping local instance...", "warning")
            try:
                # Force kill process tree (Windows)
                if os.name == 'nt':
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
                else:
                    self.process.terminate()
            except Exception as e:
                self.log(f"Error stopping process: {e}", "error")
            
            self.process = None
            self.set_status("OFFLINE")
            self.log("Local instance stopped.", "success")
            return True
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
                f'vastai destroy instance {instance_id}',
                capture_output=True, text=True, shell=True, timeout=15
            )
            
            if result.returncode == 0:
                cost = self.instance.accumulated_cost
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
                f'vastai execute {instance_id} "cat /workspace/new_models_manifest.json 2>/dev/null || echo \"[]\""',
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
                            f'vastai scp "{instance_id}:{full_path}" "{local_dest}"',
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
