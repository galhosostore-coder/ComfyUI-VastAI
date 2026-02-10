"""
launcher.py — v2.0 Professional ComfyUI Cloud Manager
=====================================================
Premium dark UI with pipeline stepper, rich console, 
live instance metrics, and sidebar navigation.
"""

import flet as ft
import threading
import time
import os
from datetime import datetime
from runner_interface import VastRunnerInterface, STEPS

# ─── Design System ────────────────────────────────────
BG_PRIMARY   = "#0d1117"
BG_CARD      = "#161b22"
BG_CARD_ALT  = "#1c2333"
BG_CONSOLE   = "#0b0e14"
BORDER_COLOR = "#30363d"
BORDER_LIGHT = "#484f58"

ACCENT_BLUE   = "#58a6ff"
ACCENT_GREEN  = "#3fb950"
ACCENT_RED    = "#f85149"
ACCENT_YELLOW = "#d29922"
ACCENT_ORANGE = "#f0883e"
ACCENT_PURPLE = "#bc8cff"

TEXT_PRIMARY   = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED     = "#484f58"

STATUS_COLORS = {
    "OFFLINE":     TEXT_MUTED,
    "SYNCING":     ACCENT_YELLOW,
    "SEARCHING":   ACCENT_BLUE,
    "LOADING":     ACCENT_ORANGE,
    "CONNECTING":  ACCENT_PURPLE,
    "RUNNING":     ACCENT_GREEN,
    "LOCAL":       ACCENT_GREEN,
    "ERROR":       ACCENT_RED,
}

SEVERITY_ICONS = {
    "info":     ("ℹ️", TEXT_SECONDARY),
    "success":  ("✅", ACCENT_GREEN),
    "warning":  ("⚠️", ACCENT_YELLOW),
    "error":    ("❌", ACCENT_RED),
    "progress": ("⏳", ACCENT_BLUE),
}

STEP_ICONS = {
    "pending": ("○", TEXT_MUTED),
    "active":  ("◉", ACCENT_BLUE),
    "done":    ("●", ACCENT_GREEN),
    "error":   ("✕", ACCENT_RED),
}


def main(page: ft.Page):
    # ─── Window Config ─────────────────────────────
    page.title = "ComfyUI Cloud Manager"
    page.theme_mode = "dark"
    page.bgcolor = BG_PRIMARY
    page.window.width = 980
    page.window.height = 720
    page.padding = 0
    page.spacing = 0
    page.fonts = {"Mono": "Consolas"}

    runner = VastRunnerInterface()

    # ═══════════════════════════════════════════════
    # COMPONENTS
    # ═══════════════════════════════════════════════

    # ─── Status Badge ──────────────────────────────
    status_badge = ft.Container(
        content=ft.Text("OFFLINE", size=11, weight="bold", color=TEXT_MUTED, font_family="Mono"),
        bgcolor="#21262d",
        border=ft.Border.all(1, TEXT_MUTED),
        border_radius=20,
        padding=ft.Padding.symmetric(horizontal=14, vertical=4),
    )

    def update_status(status):
        color = STATUS_COLORS.get(status, TEXT_MUTED)
        status_badge.content.value = status
        status_badge.content.color = color
        status_badge.border = ft.Border.all(1, color)
        try:
            page.update()
        except:
            pass

    runner.on_status_change = update_status

    # ─── Instance Info Card ────────────────────────
    info_gpu     = ft.Text("—", size=14, weight="bold", color=TEXT_PRIMARY, font_family="Mono")
    info_price   = ft.Text("—", size=12, color=TEXT_SECONDARY, font_family="Mono")
    info_uptime  = ft.Text("00:00:00", size=12, color=TEXT_SECONDARY, font_family="Mono")
    info_cost    = ft.Text("$0.0000", size=14, weight="bold", color=ACCENT_GREEN, font_family="Mono")
    info_speed   = ft.Text("—", size=11, color=TEXT_MUTED, font_family="Mono")
    info_id_text = ft.Text("—", size=11, color=TEXT_MUTED, font_family="Mono")

    instance_card = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.MEMORY, color=ACCENT_BLUE, size=18),
                ft.Text("I N S T A N C E", size=11, color=TEXT_SECONDARY, weight="bold"),
            ], spacing=8),
            ft.Divider(height=1, color=BORDER_COLOR),
            ft.Row([
                ft.Column([
                    ft.Text("GPU", size=9, color=TEXT_MUTED),
                    info_gpu,
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text("PRICE", size=9, color=TEXT_MUTED),
                    info_price,
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text("UPTIME", size=9, color=TEXT_MUTED),
                    info_uptime,
                ], spacing=2, expand=True),
                ft.Column([
                    ft.Text("COST", size=9, color=TEXT_MUTED),
                    info_cost,
                ], spacing=2, expand=True),
            ]),
            ft.Row([
                info_speed,
                ft.Text("│", color=BORDER_COLOR),
                info_id_text,
            ], spacing=8),
        ], spacing=8),
        bgcolor=BG_CARD,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=16,
        visible=False,
    )

    def update_instance_info(info):
        instance_card.visible = True
        info_gpu.value = info.get("gpu", "—")
        info_price.value = info.get("price", "—")
        info_uptime.value = info.get("uptime", "00:00:00")
        info_cost.value = info.get("cost", "$0.0000")
        info_speed.value = f"↓{info.get('download', '—')}"
        info_id_text.value = f"ID #{info.get('id', '—')}"
        try:
            page.update()
        except:
            pass

    runner.on_instance_update = update_instance_info

    # ─── Pipeline Stepper ──────────────────────────
    step_controls = []
    step_details = []

    for i, name in enumerate(STEPS):
        icon_text = ft.Text("○", size=16, color=TEXT_MUTED, font_family="Mono", text_align="center")
        label = ft.Text(name, size=10, color=TEXT_MUTED, weight="bold", text_align="center")
        detail = ft.Text("", size=9, color=TEXT_SECONDARY, text_align="center", max_lines=1, overflow="ellipsis")

        step_col = ft.Column([
            icon_text,
            label,
            detail,
        ], horizontal_alignment="center", spacing=2, expand=True)

        step_controls.append((icon_text, label, step_col))
        step_details.append(detail)

    def build_stepper_row():
        items = []
        for i, (icon_t, label_t, col) in enumerate(step_controls):
            items.append(col)
            if i < len(STEPS) - 1:
                items.append(
                    ft.Container(
                        content=ft.Text("─", color=BORDER_COLOR, size=12, text_align="center"),
                        width=20,
                    )
                )
        return items

    pipeline_stepper = ft.Container(
        content=ft.Row(build_stepper_row(), alignment="center"),
        bgcolor=BG_CARD,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    )

    def update_step(step_index, status, detail=""):
        if step_index < 0 or step_index >= len(STEPS):
            return
        
        icon_char, color = STEP_ICONS.get(status, ("○", TEXT_MUTED))
        icon_t, label_t, _ = step_controls[step_index]
        
        icon_t.value = icon_char
        icon_t.color = color
        label_t.color = color if status != "pending" else TEXT_MUTED
        step_details[step_index].value = detail

        # Update connector colors
        try:
            page.update()
        except:
            pass

    runner.on_step = update_step

    # ─── Rich Console ──────────────────────────────
    console_list = ft.ListView(
        auto_scroll=True,
        spacing=1,
        padding=ft.Padding.all(8),
        expand=True,
    )

    def add_log(message, severity="info"):
        now = datetime.now().strftime("%H:%M:%S")
        icon, color = SEVERITY_ICONS.get(severity, ("ℹ️", TEXT_SECONDARY))
        
        entry = ft.Container(
            content=ft.Row([
                ft.Text(now, size=10, color=TEXT_MUTED, font_family="Mono", width=65),
                ft.Text(icon, size=11, width=22),
                ft.Text(
                    str(message), size=11, color=color, 
                    font_family="Mono", expand=True,
                    max_lines=3, overflow="ellipsis",
                    selectable=True,
                ),
            ], spacing=4, vertical_alignment="start"),
            padding=ft.Padding.symmetric(horizontal=4, vertical=2),
            border_radius=4,
            bgcolor="#0f131a" if len(console_list.controls) % 2 == 0 else "transparent",
        )
        
        console_list.controls.append(entry)
        
        # Keep last 200 entries
        if len(console_list.controls) > 200:
            console_list.controls.pop(0)
        
        try:
            page.update()
        except:
            pass

    runner.on_log = add_log

    rich_console = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.TERMINAL, color=TEXT_MUTED, size=14),
                    ft.Text("C O N S O L E", size=10, color=TEXT_MUTED, weight="bold"),
                    ft.Container(expand=True),
                    ft.TextButton(
                        "Clear",
                        style=ft.ButtonStyle(color=TEXT_MUTED),
                        on_click=lambda e: (console_list.controls.clear(), page.update()),
                    ),
                ], spacing=8),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                bgcolor="#0f131a",
                border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
            ),
            console_list,
        ], spacing=0, expand=True),
        bgcolor=BG_CONSOLE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=8,
        expand=True,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )

    # ─── Action Buttons ───────────────────────────
    btn_open = ft.FilledButton(
        "Open ComfyUI",
        icon=ft.Icons.OPEN_IN_BROWSER,
        disabled=True,
        style=ft.ButtonStyle(
            bgcolor={"": "#21262d"},
            color={"": TEXT_MUTED},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
        ),
    )

    btn_destroy = ft.OutlinedButton(
        "Destroy Instance",
        icon=ft.Icons.DELETE_FOREVER,
        disabled=True,
        style=ft.ButtonStyle(
            color={"": TEXT_MUTED},
            side={"": ft.BorderSide(1, TEXT_MUTED)},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        ),
    )

    btn_start_cloud = ft.FilledButton(
        "Start Cloud GPU",
        icon=ft.Icons.CLOUD,
        style=ft.ButtonStyle(
            bgcolor={"": ACCENT_BLUE},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        ),
    )

    btn_start_local = ft.FilledButton(
        "Start Local PC",
        icon=ft.Icons.COMPUTER,
        style=ft.ButtonStyle(
            bgcolor={"": "#1f6f50"},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        ),
    )

    btn_sync = ft.OutlinedButton(
        "Sync Models",
        icon=ft.Icons.SYNC,
        style=ft.ButtonStyle(
            color={"": ACCENT_YELLOW},
            side={"": ft.BorderSide(1, ACCENT_YELLOW)},
            shape=ft.RoundedRectangleBorder(radius=8),
        ),
    )

    def enable_running_buttons():
        btn_open.disabled = False
        btn_open.style = ft.ButtonStyle(
            bgcolor={"": ACCENT_GREEN},
            color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
        )
        btn_destroy.disabled = False
        btn_destroy.style = ft.ButtonStyle(
            color={"": ACCENT_RED},
            side={"": ft.BorderSide(1, ACCENT_RED)},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )
        btn_start_cloud.disabled = True
        btn_start_cloud.style = ft.ButtonStyle(
            bgcolor={"": "#21262d"},
            color={"": TEXT_MUTED},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        )
        try:
            page.update()
        except:
            pass

    def disable_all_buttons():
        btn_open.disabled = True
        btn_open.style = ft.ButtonStyle(
            bgcolor={"": "#21262d"}, color={"": TEXT_MUTED},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=12),
        )
        btn_destroy.disabled = True
        btn_destroy.style = ft.ButtonStyle(
            color={"": TEXT_MUTED}, side={"": ft.BorderSide(1, TEXT_MUTED)},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        )
        btn_start_cloud.disabled = False
        btn_start_cloud.style = ft.ButtonStyle(
            bgcolor={"": ACCENT_BLUE}, color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        )
        btn_start_local.disabled = False
        btn_start_local.style = ft.ButtonStyle(
            bgcolor={"": "#1f6f50"}, color={"": "#ffffff"},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=24, vertical=14),
        )
        instance_card.visible = False
        try:
            page.update()
        except:
            pass

    # ─── Actions ───────────────────────────────────
    def start_cloud_click(e):
        cfg = runner.config
        if not cfg.get("api_key") or not cfg.get("gdrive_id"):
            add_log("API Key and GDrive Folder ID required. Go to Settings.", "error")
            return
        
        btn_start_cloud.disabled = True
        btn_start_local.disabled = True
        page.update()
        
        def run():
            add_log("Cloud launch pipeline starting...", "info")
            success = runner.launch_cloud()
            if success:
                enable_running_buttons()
                add_log("Pipeline complete! ComfyUI is ready.", "success")
            else:
                disable_all_buttons()
                add_log("Pipeline failed. Check logs above.", "error")
        
        threading.Thread(target=run, daemon=True).start()

    def start_local_click(e):
        local_path = runner.config.get("local_path", "")
        if not local_path:
            add_log("Set 'Local ComfyUI Path' in Settings first.", "error")
            return
        
        btn_start_local.disabled = True
        btn_start_cloud.disabled = True
        page.update()
        
        def run():
            success = runner.start_local(local_path)
            if success:
                enable_running_buttons()
                time.sleep(3)
                add_log("Opening local ComfyUI...", "info")
                page.launch_url("http://127.0.0.1:8188")
            else:
                disable_all_buttons()
        
        threading.Thread(target=run, daemon=True).start()

    def open_click(e):
        url = runner.get_url()
        add_log(f"Opening: {url}", "info")
        page.launch_url(url)

    def destroy_click(e):
        btn_destroy.disabled = True
        page.update()
        
        def run():
            runner.destroy_instance()
            disable_all_buttons()
        
        threading.Thread(target=run, daemon=True).start()

    def sync_click(e):
        def run():
            runner.apply_env()
            runner.sync_to_drive()
        threading.Thread(target=run, daemon=True).start()

    btn_start_cloud.on_click = start_cloud_click
    btn_start_local.on_click = start_local_click
    btn_open.on_click = open_click
    btn_destroy.on_click = destroy_click
    btn_sync.on_click = sync_click

    # ═══════════════════════════════════════════════
    # PAGES
    # ═══════════════════════════════════════════════

    # ─── Dashboard Page ────────────────────────────
    dashboard_page = ft.Column([
        instance_card,
        pipeline_stepper,
        ft.Container(height=4),
        ft.Row([
            btn_start_cloud,
            btn_start_local,
            ft.Container(expand=True),
            btn_sync,
        ], spacing=12),
        ft.Container(height=4),
        rich_console,
        ft.Container(height=4),
        ft.Row([
            btn_open,
            ft.Container(expand=True),
            btn_destroy,
        ], spacing=12),
    ], spacing=8, expand=True)

    # ─── Settings Page ─────────────────────────────
    cfg = runner.load_config()

    api_key_input = ft.TextField(
        label="Vast.ai API Key",
        password=True, can_reveal_password=True,
        value=cfg.get("api_key", ""),
        border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(font_family="Mono"),
        cursor_color=ACCENT_BLUE,
    )
    gdrive_input = ft.TextField(
        label="Google Drive Folder ID",
        value=cfg.get("gdrive_id", ""),
        border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(font_family="Mono"),
        cursor_color=ACCENT_BLUE,
    )
    local_path_input = ft.TextField(
        label="Local ComfyUI Path",
        value=cfg.get("local_path", ""),
        hint_text="A:\\ComfyUI_windows_portable\\run_nvidia_gpu.bat",
        border_color=BORDER_COLOR, focused_border_color=ACCENT_GREEN,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(font_family="Mono"),
        hint_style=ft.TextStyle(color=TEXT_MUTED),
        cursor_color=ACCENT_GREEN,
    )
    drive_models_input = ft.TextField(
        label="Drive Models Path (VastAI_Models folder)",
        value=cfg.get("drive_models_path", ""),
        hint_text="G:\\Meu Drive\\Programas\\ConfyUI-VastIA\\VastAI_Models",
        border_color=BORDER_COLOR, focused_border_color=ACCENT_YELLOW,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(font_family="Mono"),
        hint_style=ft.TextStyle(color=TEXT_MUTED),
        cursor_color=ACCENT_YELLOW,
    )
    gpu_input = ft.Dropdown(
        label="Cloud GPU",
        options=[
            ft.dropdown.Option("RTX_3090", "RTX 3090 (24GB)"),
            ft.dropdown.Option("RTX_4090", "RTX 4090 (24GB)"),
            ft.dropdown.Option("RTX_3060", "RTX 3060 (12GB)"),
            ft.dropdown.Option("RTX_4070", "RTX 4070 (12GB)"),
            ft.dropdown.Option("RTX_4080", "RTX 4080 (16GB)"),
            ft.dropdown.Option("A100_80GB", "A100 80GB"),
            ft.dropdown.Option("A6000", "A6000 (48GB)"),
            ft.dropdown.Option("A40", "A40 (48GB)"),
            ft.dropdown.Option("L40", "L40 (48GB)"),
            ft.dropdown.Option("T4", "T4 (16GB)"),
        ],
        value=cfg.get("gpu", "RTX_3090"),
        border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(color=TEXT_PRIMARY),
        expand=True,
    )
    price_input = ft.TextField(
        label="Max Price ($/hr)",
        value=str(cfg.get("price", "0.5")),
        border_color=BORDER_COLOR, focused_border_color=ACCENT_BLUE,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
        text_style=ft.TextStyle(font_family="Mono"),
        cursor_color=ACCENT_BLUE,
        keyboard_type="number",
        expand=True,
    )

    save_toast = ft.Text("", color=ACCENT_GREEN, size=12)

    def save_click(e):
        new_cfg = {
            "api_key": api_key_input.value,
            "gdrive_id": gdrive_input.value,
            "gpu": gpu_input.value,
            "price": price_input.value,
            "local_path": local_path_input.value,
            "drive_models_path": drive_models_input.value,
        }
        runner.save_config(new_cfg)
        save_toast.value = "✓ Saved!"
        page.update()
        time.sleep(2)
        save_toast.value = ""
        try:
            page.update()
        except:
            pass

    def make_settings_card(title, icon, color, children):
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(icon, color=color, size=16),
                    ft.Text(title, size=12, color=color, weight="bold"),
                ], spacing=8),
                ft.Divider(height=1, color=BORDER_COLOR),
                *children,
            ], spacing=10),
            bgcolor=BG_CARD,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            padding=20,
        )

    settings_page = ft.Column([
        make_settings_card("CLOUD — VAST.AI", ft.Icons.CLOUD, ACCENT_BLUE, [
            api_key_input,
            gdrive_input,
            ft.Row([gpu_input, price_input], spacing=12),
        ]),
        make_settings_card("LOCAL — PC", ft.Icons.COMPUTER, ACCENT_GREEN, [
            local_path_input,
        ]),
        make_settings_card("SYNC — MODELS", ft.Icons.SYNC, ACCENT_YELLOW, [
            drive_models_input,
        ]),
        ft.Container(height=8),
        ft.Row([
            ft.FilledButton(
                "Save Configuration",
                icon=ft.Icons.SAVE,
                on_click=save_click,
                style=ft.ButtonStyle(
                    bgcolor={"": ACCENT_BLUE},
                    color={"": "#ffffff"},
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding.symmetric(horizontal=24, vertical=12),
                ),
            ),
            save_toast,
        ], spacing=12),
    ], spacing=12, scroll="auto", expand=True)

    # ─── Logs Page ─────────────────────────────────
    logs_output = ft.TextField(
        multiline=True, read_only=True,
        min_lines=25, max_lines=40,
        text_style=ft.TextStyle(font_family="Mono", size=11, color=TEXT_SECONDARY),
        border_color=BORDER_COLOR,
        bgcolor=BG_CONSOLE,
        expand=True,
    )

    def refresh_logs(e):
        logs_output.value = "Fetching instance logs..."
        page.update()
        
        def fetch():
            text = runner.get_instance_logs()
            logs_output.value = text
            try:
                page.update()
            except:
                pass
        
        threading.Thread(target=fetch, daemon=True).start()

    logs_page = ft.Column([
        ft.Row([
            ft.Icon(ft.Icons.ARTICLE, color=TEXT_MUTED, size=16),
            ft.Text("I N S T A N C E   L O G S", size=11, color=TEXT_MUTED, weight="bold"),
            ft.Container(expand=True),
            ft.FilledButton(
                "Refresh",
                icon=ft.Icons.REFRESH,
                on_click=refresh_logs,
                style=ft.ButtonStyle(
                    bgcolor={"": "#21262d"},
                    color={"": TEXT_SECONDARY},
                    shape=ft.RoundedRectangleBorder(radius=8),
                ),
            ),
        ], spacing=8),
        logs_output,
    ], spacing=8, expand=True)

    # ═══════════════════════════════════════════════
    # NAVIGATION
    # ═══════════════════════════════════════════════

    content_area = ft.Container(
        content=dashboard_page,
        expand=True,
        padding=20,
        bgcolor=BG_PRIMARY,
    )

    current_nav = {"index": 0}

    def switch_page(index):
        pages = [dashboard_page, settings_page, logs_page]
        content_area.content = pages[index]
        current_nav["index"] = index
        
        # Update nav button styles
        for i, btn in enumerate(nav_buttons):
            if i == index:
                btn.style = ft.ButtonStyle(
                    bgcolor={"": "#21262d"},
                    color={"": ACCENT_BLUE},
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                )
            else:
                btn.style = ft.ButtonStyle(
                    bgcolor={"": "transparent"},
                    color={"": TEXT_SECONDARY},
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=ft.Padding.symmetric(horizontal=16, vertical=10),
                )
        page.update()

    nav_home = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.DASHBOARD, size=18),
            ft.Text("Home", size=12),
        ], spacing=10),
        on_click=lambda e: switch_page(0),
        style=ft.ButtonStyle(
            bgcolor={"": "#21262d"},
            color={"": ACCENT_BLUE},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        ),
    )

    nav_settings = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.SETTINGS, size=18),
            ft.Text("Config", size=12),
        ], spacing=10),
        on_click=lambda e: switch_page(1),
        style=ft.ButtonStyle(
            bgcolor={"": "transparent"},
            color={"": TEXT_SECONDARY},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        ),
    )

    nav_logs = ft.TextButton(
        content=ft.Row([
            ft.Icon(ft.Icons.ARTICLE, size=18),
            ft.Text("Logs", size=12),
        ], spacing=10),
        on_click=lambda e: switch_page(2),
        style=ft.ButtonStyle(
            bgcolor={"": "transparent"},
            color={"": TEXT_SECONDARY},
            shape=ft.RoundedRectangleBorder(radius=8),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        ),
    )

    nav_buttons = [nav_home, nav_settings, nav_logs]

    # ─── Sidebar ───────────────────────────────────
    sidebar = ft.Container(
        content=ft.Column([
            # Logo
            ft.Container(
                content=ft.Column([
                    ft.Text("ComfyUI", size=16, weight="bold", color=TEXT_PRIMARY),
                    ft.Text("Cloud Manager", size=10, color=ACCENT_BLUE),
                ], spacing=2, horizontal_alignment="center"),
                padding=ft.Padding.only(top=20, bottom=16),
            ),
            ft.Divider(height=1, color=BORDER_COLOR),
            ft.Container(height=8),
            # Nav buttons
            nav_home,
            nav_settings,
            nav_logs,
            ft.Container(expand=True),
            # Status at bottom
            ft.Container(
                content=ft.Column([
                    ft.Divider(height=1, color=BORDER_COLOR),
                    ft.Container(height=4),
                    status_badge,
                    ft.Text("v2.0", size=9, color=TEXT_MUTED, text_align="center"),
                ], horizontal_alignment="center", spacing=4),
                padding=ft.Padding.only(bottom=12),
            ),
        ], spacing=4, horizontal_alignment="center"),
        width=160,
        bgcolor=BG_CARD,
        border=ft.Border.only(right=ft.BorderSide(1, BORDER_COLOR)),
        padding=ft.Padding.symmetric(horizontal=12),
    )

    # ─── Main Layout ──────────────────────────────
    page.add(
        ft.Row([
            sidebar,
            content_area,
        ], spacing=0, expand=True)
    )

    # Welcome log
    add_log("ComfyUI Cloud Manager v2.0 ready.", "success")
    add_log("Configure API Key and GDrive ID in Settings to get started.", "info")


if __name__ == "__main__":
    ft.run(main)
