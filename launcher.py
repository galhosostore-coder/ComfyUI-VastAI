import flet as ft
import threading
import time
import os
from runner_interface import VastRunnerInterface

def main(page: ft.Page):
    page.title = "ComfyUI-VastAI Launcher (Hybrid Edition)"
    page.theme_mode = "dark"
    page.window_width = 800
    page.window_height = 650
    page.padding = 20
    
    runner = VastRunnerInterface()
    
    # --- State Variables ---
    status_text = ft.Text("Offline", color="grey", size=16, weight="bold")
    console_output = ft.Column(scroll="always", auto_scroll=True)
    
    def log(message):
        console_output.controls.append(ft.Text(message, font_family="Consolas", size=12))
        try:
            page.update()
        except:
            pass

    def update_buttons(mode="offline"):
        # Modes: "offline", "cloud_running", "local_running"
        
        # Reset all by default
        btn_start_cloud.disabled = False
        btn_start_cloud.style = ft.ButtonStyle(bgcolor="blue", color="white")
        
        btn_stop_cloud.disabled = True
        btn_stop_cloud.style = ft.ButtonStyle(bgcolor="grey", color="#aaaaaa")
        
        btn_start_local.disabled = False
        btn_start_local.style = ft.ButtonStyle(bgcolor="teal", color="white")
        
        btn_open.disabled = True
        btn_open.style = ft.ButtonStyle(bgcolor="grey", color="#aaaaaa")
        
        if mode == "cloud_running":
            status_text.value = "Cloud Running"
            status_text.color = "green"
            
            btn_start_cloud.disabled = True
            btn_start_cloud.style = ft.ButtonStyle(bgcolor="grey", color="white")
            
            btn_stop_cloud.disabled = False
            btn_stop_cloud.style = ft.ButtonStyle(bgcolor="red", color="white")
            
            btn_start_local.disabled = True # Prevent running both? Or allow? Let's prevent to avoid port conflicts if 8188 default.
            btn_start_local.style = ft.ButtonStyle(bgcolor="grey", color="#aaaaaa")
            
            btn_open.disabled = False
            btn_open.style = ft.ButtonStyle(bgcolor="green", color="white")
            
        elif mode == "local_running":
            status_text.value = "Local Running"
            status_text.color = "lightgreen"
            
            btn_start_local.disabled = True
            btn_start_local.style = ft.ButtonStyle(bgcolor="grey", color="white")
            
            # Can we stop local? We didn't implement stop_local yet in runner (subprocess object exists).
            # For now, just disable start buttons. User stops local by closing window manually usually, 
            # but we should probably add stop local eventually.
            
            btn_open.disabled = False
            btn_open.style = ft.ButtonStyle(bgcolor="green", color="white")

        elif mode == "offline":
            status_text.value = "Offline"
            status_text.color = "grey"
            
        page.update()

    # --- Actions ---
    def start_cloud_click(e):
        api_key = api_key_input.value
        gdrive_id = gdrive_input.value
        gpu = gpu_input.value
        price = price_input.value
        local_path = local_path_input.value
        
        if not api_key or not gdrive_id:
            log("❌ Error: API Key and GDrive ID required for Cloud.")
            return

        runner.set_config(api_key, gdrive_id, gpu, price, local_path, drive_models_input.value)
        
        status_text.value = "Cloud Starting..."
        status_text.color = "orange"
        btn_start_cloud.disabled = True
        btn_start_cloud.style = ft.ButtonStyle(bgcolor="grey")
        page.update()
        
        def run_thread():
            log("🚀 Cloud Launch Sequence initiated...")
            success = runner.start_instance(log_callback=log)
            if success:
                update_buttons("cloud_running")
            else:
                update_buttons("offline")
                status_text.value = "Cloud Failed"
                status_text.color = "red"
                page.update()

        threading.Thread(target=run_thread, daemon=True).start()

    def start_local_click(e):
        local_path = local_path_input.value
        if not local_path:
             log("❌ Error: Please set 'Local ComfyUI Path' in Settings.")
             return
             
        # Save config
        runner.save_config(api_key_input.value, gdrive_input.value, gpu_input.value, price_input.value, local_path, drive_models_input.value)

        status_text.value = "Local Starting..."
        status_text.color = "orange"
        btn_start_local.disabled = True
        btn_start_local.style = ft.ButtonStyle(bgcolor="grey")
        page.update()
        
        def run_thread():
            log(f"🏠 Launching Local ComfyUI from: {local_path}")
            success = runner.start_local(local_path, log_callback=log)
            if success:
                update_buttons("local_running")
                # Wait a bit then open
                time.sleep(3)
                log("🌐 Opening Localhost...")
                page.launch_url("http://127.0.0.1:8188") 
            else:
                update_buttons("offline")
                status_text.value = "Local Failed"
                status_text.color = "red"
                page.update()

        threading.Thread(target=run_thread, daemon=True).start()

    def stop_cloud_click(e):
        log("🛑 Stopping Cloud instance...")
        runner.stop_all(log_callback=log)
        update_buttons("offline")

    def open_click(e):
        # Determine URL based on status
        if "Local" in status_text.value:
            url = "http://127.0.0.1:8188"
        else:
            url = runner.get_current_url()
        log(f"🌐 Opening: {url}")
        page.launch_url(url)

    def sync_click(e):
        log("\ud83d\udd04 Syncing local models to Drive...")
        def sync_thread():
            runner.sync_to_drive(log_callback=log)
        threading.Thread(target=sync_thread, daemon=True).start()

    # --- UI Elements: Settings ---
    api_key_input = ft.TextField(label="Vast.ai API Key", password=True, can_reveal_password=True, border_color="blue")
    gdrive_input = ft.TextField(label="Google Drive Folder ID", border_color="blue")
    local_path_input = ft.TextField(label="Local ComfyUI Path (e.g. run_nvidia_gpu.bat)", border_color="teal", hint_text="A:\\ComfyUI_windows_portable\\run_nvidia_gpu.bat")
    drive_models_input = ft.TextField(label="Drive Models Path (synced folder)", border_color="orange", hint_text="G:\\Meu Drive\\Programas\\ConfyUI-VastIA\\VastAI_Models")
    
    gpu_input = ft.Dropdown(
        label="Cloud GPU Model",
        options=[
            ft.dropdown.Option("RTX_3090"),
            ft.dropdown.Option("RTX_4090"),
            ft.dropdown.Option("RTX_3060"),
            ft.dropdown.Option("A100"),
            ft.dropdown.Option("A100_80GB"),
            ft.dropdown.Option("A6000"),
            ft.dropdown.Option("A40"),
            ft.dropdown.Option("T4"),
        ],
        value="RTX_3090",
        border_color="blue",
        expand=True
    )
    
    price_input = ft.TextField(
        label="Max Price ($/hr)", 
        value="0.5", 
        border_color="blue", 
        expand=True,
        keyboard_type="number"
    )
    
    cfg = runner.load_config()
    api_key_input.value = cfg.get("api_key", "")
    gdrive_input.value = cfg.get("gdrive_id", "")
    price_input.value = str(cfg.get("price", "0.5"))
    gpu_input.value = cfg.get("gpu", "RTX_3090")
    local_path_input.value = cfg.get("local_path", "")
    drive_models_input.value = cfg.get("drive_models_path", "")
    
    btn_save = ft.FilledButton("Save Config", on_click=lambda e: runner.save_config(api_key_input.value, gdrive_input.value, gpu_input.value, price_input.value, local_path_input.value, drive_models_input.value))

    settings_view = ft.Column([
        ft.Text("Configuration", size=24, weight="bold"),
        ft.Divider(),
        ft.Text("Cloud Settings (Vast.ai)", color="blue", weight="bold"),
        api_key_input,
        gdrive_input,
        ft.Row([gpu_input, price_input], spacing=20),
        ft.Divider(),
        ft.Text("Local Settings (PC)", color="teal", weight="bold"),
        local_path_input,
        ft.Divider(),
        ft.Text("Sync Settings (Local \u2192 Drive \u2192 Cloud)", color="orange", weight="bold"),
        drive_models_input,
        ft.Container(height=20),
        btn_save
    ], spacing=10, scroll="auto")

    # --- UI Elements: Dashboard ---
    btn_start_cloud = ft.FilledButton("Start Cloud GPU", icon=ft.Icons.CLOUD, on_click=start_cloud_click, style=ft.ButtonStyle(bgcolor="blue", color="white"))
    btn_stop_cloud = ft.FilledButton("Stop Cloud", icon=ft.Icons.STOP, on_click=stop_cloud_click, style=ft.ButtonStyle(bgcolor="grey", color="#aaaaaa"), disabled=True)
    
    btn_start_local = ft.FilledButton("Start Local PC", icon=ft.Icons.COMPUTER, on_click=start_local_click, style=ft.ButtonStyle(bgcolor="teal", color="white"))
    
    btn_open = ft.FilledButton("Open ComfyUI", icon=ft.Icons.OPEN_IN_BROWSER, on_click=open_click, style=ft.ButtonStyle(bgcolor="grey", color="#aaaaaa"), disabled=True)
    btn_sync = ft.OutlinedButton("Sync Models", icon=ft.Icons.SYNC, on_click=sync_click)

    dashboard_view = ft.Column([
        ft.Row([
            ft.Text("Status: ", size=20),
            status_text
        ]),
        ft.Divider(),
        ft.Text("Cloud Operations", color="blue"),
        ft.Row([btn_start_cloud, btn_stop_cloud], alignment="start", spacing=20),
        ft.Container(height=10),
        ft.Text("Local Operations", color="teal"),
        ft.Row([btn_start_local], alignment="start", spacing=20),
        ft.Container(height=10),
        ft.Divider(),
        ft.Row([btn_open, btn_sync], alignment="center", spacing=20),
        ft.Divider(),
        ft.Text("Console Output:", size=14, color="grey"),
        ft.Container(
            content=console_output,
            bgcolor="#1a1a1a",
            border=ft.border.all(1, "#333333"),
            border_radius=10,
            padding=10,
            expand=True
        )
    ], expand=True)

    # --- Manual Tab System ---
    content_area = ft.Container(content=dashboard_view, expand=True, padding=10)
    
    tab_dash = ft.TextButton(
        "Dashboard", 
        icon=ft.Icons.DASHBOARD, 
        data="dash",
        style=ft.ButtonStyle(color="white", bgcolor="#333333")
    )
    
    tab_settings = ft.TextButton(
        "Settings", 
        icon=ft.Icons.SETTINGS, 
        data="settings",
        style=ft.ButtonStyle(color="grey", bgcolor="transparent")
    )

    def switch_tab(e):
        clicked = e.control.data
        if clicked == "dash":
            tab_dash.style = ft.ButtonStyle(color="white", bgcolor="#333333")
            tab_settings.style = ft.ButtonStyle(color="grey", bgcolor="transparent")
            content_area.content = dashboard_view
        else:
            tab_dash.style = ft.ButtonStyle(color="grey", bgcolor="transparent")
            tab_settings.style = ft.ButtonStyle(color="white", bgcolor="#333333")
            content_area.content = settings_view
        page.update()

    tab_dash.on_click = switch_tab
    tab_settings.on_click = switch_tab

    header = ft.Container(
        content=ft.Row([tab_dash, tab_settings], spacing=0),
        bgcolor="#111111",
        padding=5,
        border_radius=5
    )

    page.add(
        ft.Column([
            header,
            content_area
        ], expand=True)
    )

if __name__ == "__main__":
    ft.app(main)
