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
    status_text = ft.Text("Offline", color="grey")
    console_output = ft.Column(scroll="always", auto_scroll=True)
    
    def log(message):
        console_output.controls.append(ft.Text(message, font_family="Consolas", size=12))
        try:
            page.update()
        except:
            pass # Handle race conditions during rapid updates

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
    
    btn_save = ft.FilledButton("Save Config", on_click=lambda e: runner.save_config(api_key_input.value, gdrive_input.value))

    settings_tab = ft.Column([
        ft.Text("Configuration", size=20, weight="bold"),
        api_key_input,
        gdrive_input,
        gpu_input,
        btn_save
    ], spacing=20)

    # Dashboard Tab
    # Use FilledButton for primary actions
    btn_start = ft.FilledButton("Start Instance", icon=ft.Icons.ROCKET_LAUNCH, on_click=start_click, bgcolor="blue", color="white")
    btn_stop = ft.FilledButton("Stop Instance", icon=ft.Icons.STOP, on_click=stop_click, bgcolor="red", color="white", disabled=True)
    
    # Use Tonal or Outlined for secondary
    btn_open = ft.FilledButton("Open ComfyUI", icon=ft.Icons.OPEN_IN_BROWSER, on_click=open_click, disabled=True)
    btn_sync = ft.OutlinedButton("Sync Models", icon=ft.Icons.SYNC, on_click=sync_click)

    # Custom Tab Header Components to avoid 'text' argument issues
    def tab_header(text, icon):
        return ft.Row([ft.Icon(icon), ft.Text(text)], spacing=5)

    dashboard_content = ft.Column([
        ft.Row([
            ft.Text("Status: ", size=20),
            status_text
        ]),
        ft.Divider(),
        ft.Row([btn_start, btn_stop], alignment="center"),
        ft.Row([btn_open, btn_sync], alignment="center"),
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
    # We use tab_content for custom headers if text='...' fails
    # But Flet 0.80 docs say 'text' should work. 
    # If the user got "unexpected keyword argument 'text'", implies Tab signature changed drastically.
    # It might be `label`? 
    # Let's try `text` again BUT verify if it's `ft.Tab(text=...)`. 
    # If `text` fails, I'll use `tab_content` (which expects a Control).
    
    tab_1 = ft.Tab(
        label="Dashboard", icon=ft.Icons.DASHBOARD,
        content=dashboard_content
    )
    
    tab_2 = ft.Tab(
         label="Settings", icon=ft.Icons.SETTINGS,
         content=settings_tab
    )

    t = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[tab_1, tab_2],
        expand=1,
    )

    page.add(t)

if __name__ == "__main__":
    # The warning said "Use run() instead".
    # ft.app(target=main) is deprecated.
    # Try ft.app(main) -> DeprecationWarning.
    # Maybe flet.app.run()? 
    # Let's try the modern standard:
    ft.app(main)
