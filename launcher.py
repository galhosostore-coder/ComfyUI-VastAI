import flet as ft
import threading
import time
import os
import sys
import subprocess
from runner_interface import VastRunnerInterface

def main(page: ft.Page):
    page.title = "ComfyUI-VastAI Launcher"
    page.theme_mode = "dark"
    page.window_width = 800
    page.window_height = 600
    page.padding = 20
    
    runner = VastRunnerInterface()
    
    # --- State Variables ---
    status_text = ft.Text("Offline", color="grey")
    console_output = ft.Column(scroll="always", auto_scroll=True)
    
    def log(message):
        console_output.controls.append(ft.Text(message, font_family="Consolas", size=12))
        page.update()

    # --- Actions ---
    def start_click(e):
        api_key = api_key_input.value
        gdrive_id = gdrive_input.value
        gpu = gpu_input.value
        
        if not api_key or not gdrive_id:
            log("❌ Error: API Key and GDrive ID required in Settings tab.")
            return

        runner.set_config(api_key, gdrive_id, gpu)
        
        status_text.value = "Starting..."
        status_text.color = "orange"
        btn_start.disabled = True
        page.update()
        
        def run_thread():
            log("🚀 Launching sequence initiated...")
            success = runner.start_instance(log_callback=log)
            if success:
                status_text.value = "Running"
                status_text.color = "green"
                btn_open.disabled = False
                btn_stop.disabled = False
            else:
                status_text.value = "Failed"
                status_text.color = "red"
                btn_start.disabled = False
            page.update()

        threading.Thread(target=run_thread, daemon=True).start()

    def stop_click(e):
        log("🛑 Stopping instance...")
        runner.stop_all(log_callback=log)
        status_text.value = "Offline"
        status_text.color = "grey"
        btn_start.disabled = False
        btn_stop.disabled = True
        btn_open.disabled = True
        page.update()

    def open_click(e):
        url = runner.get_current_url()
        log(f"🌐 Opening: {url}")
        page.launch_url(url)

    def sync_click(e):
        log("🔄 Syncing models...")
        runner.sync_models(log_callback=log)

    # --- UI Elements ---
    
    # Settings Tab
    api_key_input = ft.TextField(label="Vast.ai API Key", password=True, can_reveal_password=True)
    gdrive_input = ft.TextField(label="Google Drive Folder ID")
    gpu_input = ft.Dropdown(
        label="GPU Preference",
        options=[
            ft.dropdown.Option("RTX_3090"),
            ft.dropdown.Option("RTX_4090"),
            ft.dropdown.Option("A6000"),
        ],
        value="RTX_3090"
    )
    
    # Load saved config
    cfg = runner.load_config()
    api_key_input.value = cfg.get("api_key", "")
    gdrive_input.value = cfg.get("gdrive_id", "")
    
    btn_save = ft.Button("Save Config", on_click=lambda e: runner.save_config(api_key_input.value, gdrive_input.value))

    settings_tab = ft.Column([
        ft.Text("Configuration", size=20, weight=ft.FontWeight.BOLD),
        api_key_input,
        gdrive_input,
        gpu_input,
        btn_save
    ], spacing=20)

    # Dashboard Tab
    btn_start = ft.ElevatedButton("Start Instance", icon=ft.Icons.ROCKET_LAUNCH, on_click=start_click, bgcolor="blue", color="white")
    btn_stop = ft.ElevatedButton("Stop Instance", icon=ft.Icons.STOP, on_click=stop_click, bgcolor="red", color="white", disabled=True)
    btn_open = ft.ElevatedButton("Open ComfyUI", icon=ft.Icons.OPEN_IN_BROWSER, on_click=open_click, disabled=True)
    btn_sync = ft.ElevatedButton("Sync Models", icon=ft.Icons.SYNC, on_click=sync_click)

    dashboard_tab = ft.Column([
        ft.Row([
            ft.Text("Status: ", size=20),
            status_text
        ]),
        ft.Divider(),
        ft.Row([btn_start, btn_stop], alignment=ft.MainAxisAlignment.CENTER),
        ft.Row([btn_open, btn_sync], alignment=ft.MainAxisAlignment.CENTER),
        ft.Divider(),
        ft.Container(
            content=console_output,
            bgcolor=ft.Colors.BLACK54, 
            border_radius=10,
            padding=10,
            expand=True
        )
    ], expand=True)

    # Tabs
    t = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="Dashboard", icon=ft.Icons.DASHBOARD, content=dashboard_tab),
            ft.Tab(text="Settings", icon=ft.Icons.SETTINGS, content=settings_tab),
        ],
        expand=1,
    )

    page.add(t)

if __name__ == "__main__":
    ft.app(main)
