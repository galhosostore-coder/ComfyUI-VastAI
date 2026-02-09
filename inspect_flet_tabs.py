import flet as ft
import inspect

with open("flet_inspection_tabs.txt", "w") as f:
    try:
        f.write("\n--- ft.Tabs.__init__ ---\n")
        f.write(str(inspect.signature(ft.Tabs.__init__)) + "\n")
        f.write(ft.Tabs.__doc__ or "No docstring")
    except Exception as e:
        f.write(f"Error inspecting Tabs: {e}")
