import flet as ft
import threading
import time
from runner_interface import VastRunnerInterface

def main(page: ft.Page):
    page.title = "ComfyUI-VastAI Launcher"
    page.theme_mode = "dark"
    page.window_width = 800
    page.window_height = 600
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

    # --- Actions ---
    def start_click(e):
        api_key = api_key_input.value
        gdrive_id = gdrive_input.value
        gpu = gpu_input.value
        price = price_input.value
        
        if not api_key or not gdrive_id:
            log("❌ Error: API Key and GDrive ID required in Settings tab.")
            return

        runner.set_config(api_key, gdrive_id, gpu, price)
        
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
            try:
                page.update()
            except:
                pass

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

    # --- UI Elements: Settings ---
    api_key_input = ft.TextField(label="Vast.ai API Key", password=True, can_reveal_password=True, border_color="blue")
    gdrive_input = ft.TextField(label="Google Drive Folder ID", border_color="blue")
    
    gpu_input = ft.Dropdown(
        label="GPU Model",
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
    
    btn_save = ft.FilledButton("Save Config", on_click=lambda e: runner.save_config(api_key_input.value, gdrive_input.value, gpu_input.value, price_input.value))

    settings_view = ft.Column([
        ft.Text("Configuration", size=24, weight="bold"),
        ft.Divider(),
        api_key_input,
        gdrive_input,
        ft.Row([gpu_input, price_input], spacing=20),
        ft.Container(height=20),
        btn_save
    ], spacing=10)

    # --- UI Elements: Dashboard ---
    btn_start = ft.FilledButton("Start Instance", icon=ft.Icons.ROCKET_LAUNCH, on_click=start_click, bgcolor="blue", color="white")
    btn_stop = ft.FilledButton("Stop Instance", icon=ft.Icons.STOP, on_click=stop_click, bgcolor="red", color="white", disabled=True)
    btn_open = ft.FilledButton("Open ComfyUI", icon=ft.Icons.OPEN_IN_BROWSER, on_click=open_click, disabled=True)
    btn_sync = ft.OutlinedButton("Sync Models", icon=ft.Icons.SYNC, on_click=sync_click)

    dashboard_view = ft.Column([
        ft.Row([
            ft.Text("Status: ", size=20),
            status_text
        ]),
        ft.Divider(),
        ft.Row([btn_start, btn_stop], alignment="center", spacing=20),
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
    
    # Define buttons first (references needed for switch_tab)
    # But wait, python scoping. 
    # We need to define switch_tab to use the button references?
    # Or define buttons, then define switch tab, then assign on_click?
    # Actually, inside switch_tab we can refer to tab_dash defined later if it's in local scope? No.
    # We must define references or use e.control.data.
    
    # Better: Use a class or helper, or just use `page.update()` on the whole row if we reconstruct it?
    # Efficient way:
    
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
        
        # Update styles
        if clicked == "dash":
            tab_dash.style = ft.ButtonStyle(color="white", bgcolor="#333333")
            tab_settings.style = ft.ButtonStyle(color="grey", bgcolor="transparent")
            content_area.content = dashboard_view
        else:
            tab_dash.style = ft.ButtonStyle(color="grey", bgcolor="transparent")
            tab_settings.style = ft.ButtonStyle(color="white", bgcolor="#333333")
            content_area.content = settings_view
            
        page.update()

    # Link events
    tab_dash.on_click = switch_tab
    tab_settings.on_click = switch_tab

    header = ft.Container(
        content=ft.Row([tab_dash, tab_settings], spacing=0),
        bgcolor="#111111",
        padding=5,
        border_radius=5
    )

    # Main Layout
    page.add(
        ft.Column([
            header,
            content_area
        ], expand=True)
    )

if __name__ == "__main__":
    ft.app(main)
