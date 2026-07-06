"""
main.py - data-driven tkinter GUI

Menu structure comes from menu.json (nested menus supported).
File paths and preferences come from settings.csv (flat key,value).
The window and menubar are constructed at runtime; nothing is hardcoded
except the action handlers, which menu items reference by name.
"""

import csv
import json
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- settings

def load_settings(path):
    """Read flat key,value CSV into a dict of strings."""
    settings = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row.get("key") or "").strip()
            if key:
                settings[key] = (row.get("value") or "").strip()
    return settings


def load_menu(path):
    """Read menu structure from JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- application

class App:
    def __init__(self, settings, menu_def):
        self.settings = settings
        self.root = tk.Tk()
        self.root.title(settings.get("app_title", "App"))
        w = settings.get("window_width", "800")
        h = settings.get("window_height", "500")
        self.root.geometry(f"{w}x{h}")

        # action registry: menu items reference these by name
        self.actions = {
            "open_path": self.open_path,
            "run_script": self.run_script,
            "show_about": self.show_about,
            "show_author": self.show_author,
            "exit_app": self.root.quit,
        }

        self.build_menubar(menu_def)
        self.status = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self.status, anchor="w",
                 relief="sunken").pack(side="bottom", fill="x")

    # ------------------------------------------------------------ menu build

    def build_menubar(self, menu_def):
        menubar = tk.Menu(self.root)
        for top in menu_def.get("menus", []):
            menubar.add_cascade(label=top["label"],
                                menu=self.build_submenu(top.get("items", [])))
        self.root.config(menu=menubar)

    def build_submenu(self, items):
        """Recursively build a tk.Menu from a list of item definitions."""
        menu = tk.Menu(self.root, tearoff=0)
        for item in items:
            if item.get("type") == "separator":
                menu.add_separator()
            elif "items" in item:  # nested submenu
                menu.add_cascade(label=item["label"],
                                 menu=self.build_submenu(item["items"]))
            else:
                menu.add_command(label=item["label"],
                                 command=self.make_command(item))
        return menu

    def make_command(self, item):
        """Bind an item's named action + args into a zero-arg callback."""
        action = item.get("action", "")
        args = item.get("args", {})

        def command():
            handler = self.actions.get(action)
            if handler is None:
                messagebox.showwarning(
                    "Not implemented",
                    f"No handler registered for action '{action}'.")
                return
            handler(**args) if args else handler()

        return command

    # ------------------------------------------------------------ actions

    def resolve(self, setting_key):
        """Look up a path in settings; warn if missing."""
        path = self.settings.get(setting_key, "")
        if not path:
            messagebox.showerror("Settings",
                                 f"'{setting_key}' not found in settings.csv")
            return None
        return path

    def open_path(self, setting_key):
        path = self.resolve(setting_key)
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showerror("Open", f"Path does not exist:\n{path}")
            return
        if sys.platform.startswith("win"):
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        self.status.set(f"Opened {path}")

    def run_script(self, setting_key):
        script = self.resolve(setting_key)
        if not script:
            return
        python_exe = self.settings.get("python_exe", sys.executable)
        subprocess.Popen([python_exe, script],
                         cwd=os.path.dirname(script) or ".")

        self.status.set(f"Launched {os.path.basename(script)}")

    def show_about(self):
        messagebox.showinfo(
            "About",
            f"{self.settings.get('app_title', 'App')}\n"
            "Menu structure: menu.json\n"
            "Preferences: settings.csv")
        
    def show_author(self):
        messagebox.showinfo(
            "Author",
             f"{self.settings.get('app_title', 'App')}\n"
            "Created by: Bradley  Eizenga\n"
            "As at: July 2026")    

    def run(self):
        self.root.mainloop()

# ---------------------------------------------------------------- entry point

def main():
    settings_path = os.path.join(BASE_DIR, "settings.csv")
    print(settings_path)
    settings = load_settings(settings_path)
    menu_path = settings.get("menu_file", "menu.json")
    if not os.path.isabs(menu_path):
        menu_path = os.path.join(BASE_DIR, menu_path)
    menu_def = load_menu(menu_path)
    App(settings, menu_def).run()


if __name__ == "__main__":
    main()
