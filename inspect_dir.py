import flet as ft
with open("flet_dir.txt", "w") as f:
    f.write("\n".join(dir(ft)))
