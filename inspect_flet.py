import flet as ft
import inspect

with open("flet_inspection.txt", "w") as f:
    f.write(f"Flet Version: {ft.version}\n")
    f.write("="*50 + "\n")
    
    try:
        f.write("\n--- ft.Tab.__init__ ---\n")
        f.write(str(inspect.signature(ft.Tab.__init__)) + "\n")
        f.write(ft.Tab.__doc__ or "No docstring")
    except Exception as e:
        f.write(f"Error inspecting Tab: {e}")

    try:
        f.write("\n\n--- ft.FilledButton.__init__ ---\n")
        f.write(str(inspect.signature(ft.FilledButton.__init__)) + "\n")
    except Exception as e:
        f.write(f"Error inspecting FilledButton: {e}")

    try:
        f.write("\n\n--- ft.app signature ---\n")
        f.write(str(inspect.signature(ft.app)) + "\n")
    except Exception as e:
        f.write(f"Error inspecting app: {e}")
