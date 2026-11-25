import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser
import zipfile
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

APP_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "XboxEnPC"
CONFIG_FILE = APP_DIR / "config.json"

GAMES = [
    {"name": "XCL", "description": "Configura el ejecutable de XCL para iniciarlo desde aquí."},
    {"name": "Victory", "description": "Configura el ejecutable de Victory para iniciarlo desde aquí."},
    {"name": "Hyphen", "description": "Configura el ejecutable de Hyphen para iniciarlo desde aquí."},
]

REPOSITORIES = {
    "XCL": "xcl-dev/xcl",
    "Victory": "Marvisak/VIctory",
    "Hyphen": "fxceless/victory-fork",
}

BG = "#090b10"
PANEL = "#171522"
PANEL2 = "#201c2d"
PURPLE = "#873cff"
GREEN = "#19df8b"
TEXT = "#f4efff"
MUTED = "#aaa2ba"


def discover_windows_apps():
    """Busca accesos directos y entradas de aplicaciones instaladas en Windows."""
    found = {}
    if os.name != "nt":
        return found

    targets = {game["name"].lower(): game["name"] for game in GAMES}
    roots = [
        Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.getenv("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.getenv("USERPROFILE", "")) / "Desktop",
        Path(os.getenv("PUBLIC", "C:/Users/Public")) / "Desktop",
    ]

    for root in roots:
        if not root.exists():
            continue
        try:
            for item in root.rglob("*"):
                if item.is_file() and item.suffix.lower() in (".lnk", ".url", ".exe"):
                    stem = item.stem.lower()
                    for target, display_name in targets.items():
                        if target in stem and display_name not in found:
                            found[display_name] = str(item)
        except (PermissionError, OSError):
            pass

    try:
        import winreg
        uninstall_paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, key_path in uninstall_paths:
            try:
                parent = winreg.OpenKey(hive, key_path)
            except OSError:
                continue
            with parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        sub_name = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, sub_name) as sub:
                            values = {}
                            for value_name in ("DisplayName", "InstallLocation", "DisplayIcon"):
                                try:
                                    values[value_name] = winreg.QueryValueEx(sub, value_name)[0]
                                except OSError:
                                    pass
                        display = str(values.get("DisplayName", "")).lower()
                        for target, display_name in targets.items():
                            if target in display and display_name not in found:
                                candidate = str(values.get("DisplayIcon") or values.get("InstallLocation") or "")
                                candidate = candidate.strip().strip('"').split(",")[0]
                                if candidate and Path(candidate).exists():
                                    found[display_name] = candidate
                    except OSError:
                        continue
    except Exception:
        pass

    return found


class Launcher:
    def __init__(self, root):
        self.root = root
        self.root.title("Xbox en PC")
        self.root.geometry("560x690")
        self.root.minsize(500, 600)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self.config = self.load_config()
        self.page = "Jugar"
        self.repo_status = {}

        self.matrix = tk.Canvas(root, bg=BG, highlightthickness=0)
        self.matrix.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.columns = []
        self.root.bind("<Configure>", self.resize_matrix)
        self.animate_matrix()

        self.ui = tk.Frame(root, bg=BG)
        self.ui.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.84, relheight=0.91)

        self.auto_detect(save=True)
        self.build()

    def load_config(self):
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Configuración no válida")
            data.setdefault("games", {})
            data.setdefault("installer", "")
            return data
        except (OSError, ValueError, json.JSONDecodeError):
            return {"games": {}, "installer": ""}

    def save_config(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(self.config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def auto_detect(self, save=False):
        found = discover_windows_apps()
        games = self.config.setdefault("games", {})
        for game in GAMES:
            name = game["name"]
            path = found.get(name)
            old_path = games.get(name, "")
            if path and (not old_path or not Path(old_path).exists()):
                games[name] = path
        if save:
            self.save_config()
        return found

    def detect_and_refresh(self):
        found = self.auto_detect(save=True)
        self.build()
        if found:
            messagebox.showinfo("Detección completada", "Se han detectado aplicaciones compatibles.")
        else:
            messagebox.showinfo(
                "Detección completada",
                "No se han encontrado aplicaciones instaladas. Puedes elegir sus archivos .exe manualmente."
            )

    def resize_matrix(self, event=None):
        if event and event.widget is not self.root:
            return
        width = max(self.root.winfo_width(), 1)
        self.matrix.delete("all")
        self.columns = []
        for x in range(0, width, 22):
            self.columns.append([x, -((x * 7) % 500), 8 + (x % 5)])

    def animate_matrix(self):
        if not self.root.winfo_exists():
            return
        self.matrix.delete("rain")
        height = max(self.root.winfo_height(), 1)
        for column in self.columns:
            x, y, speed = column
            for j in range(8):
                yy = y - j * 17
                if 0 <= yy <= height:
                    self.matrix.create_text(
                        x, yy, text=chr(0x30A0 + ((x + int(yy)) % 96)),
                        fill="#075b37" if j else "#19a86a",
                        font=("Consolas", 10), tags="rain"
                    )
            column[1] += speed
            if column[1] - 140 > height:
                column[1] = -20
        self.root.after(85, self.animate_matrix)

    def clear_ui(self):
        for child in self.ui.winfo_children():
            child.destroy()

    def build(self):
        self.clear_ui()
        header = tk.Frame(self.ui, bg="#8c2bd5", height=92)
        header.pack(fill="x", pady=(0, 12))
        header.pack_propagate(False)
        tk.Label(
            header, text="Xbox en PC", bg="#8c2bd5", fg="white",
            font=("Segoe UI", 22, "bold")
        ).pack(anchor="w", padx=18, pady=(14, 0))
        tk.Label(
            header, text="Juegos de PC · Tu biblioteca en un solo lugar",
            bg="#8c2bd5", fg="#f7dfff", font=("Segoe UI", 9)
        ).pack(anchor="w", padx=19)

        nav = tk.Frame(self.ui, bg=BG)
        nav.pack(fill="x", pady=(0, 12))
        self.nav_button(nav, "Jugar")
        self.nav_button(nav, "Instalar")

        if self.page == "Jugar":
            self.play_page()
        else:
            self.install_page()

        footer = tk.Frame(self.ui, bg=BG)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        tk.Label(
            footer, text="Biblioteca local · Xbox en PC", bg=BG, fg=MUTED,
            font=("Segoe UI", 8)
        ).pack(side="left")
        tk.Button(
            footer, text="Configuración", command=self.settings,
            bg=PANEL2, fg=TEXT, activebackground=PURPLE,
            activeforeground="white", relief="flat", padx=12, pady=5,
            cursor="hand2"
        ).pack(side="right")

    def nav_button(self, parent, label):
        active = self.page == label
        tk.Button(
            parent, text=label, command=lambda: self.change_page(label),
            bg=PURPLE if active else PANEL,
            fg="white" if active else MUTED,
            activebackground=PURPLE, activeforeground="white",
            relief="flat", font=("Segoe UI", 10, "bold"),
            cursor="hand2", padx=30, pady=7
        ).pack(side="left", expand=True, fill="x", padx=4)

    def change_page(self, page):
        self.page = page
        self.build()

    def card(self, name, description):
        card = tk.Frame(self.ui, bg=PANEL, padx=14, pady=10)
        card.pack(fill="x", pady=5)
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x")
        tk.Label(
            top, text=name, bg=PANEL, fg=TEXT,
            font=("Segoe UI", 12, "bold")
        ).pack(side="left")

        path = self.config.get("games", {}).get(name, "")
        state = "Configurado" if path and Path(path).exists() else "Falta seleccionar el .exe"
        tk.Label(
            top, text=state, bg=PANEL,
            fg=GREEN if state == "Configurado" else MUTED,
            font=("Segoe UI", 8)
        ).pack(side="right")

        tk.Label(
            card, text=description, bg=PANEL, fg=MUTED,
            font=("Segoe UI", 8), wraplength=390, justify="left"
        ).pack(anchor="w", pady=(3, 8))

        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x")
        tk.Button(
            row, text=f"Jugar con {name}",
            command=lambda n=name: self.launch_game(n),
            bg=GREEN, fg="#062417", activebackground="#62f5b5",
            relief="flat", font=("Segoe UI", 9, "bold"),
            cursor="hand2", padx=18, pady=7
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            row, text="Elegir .exe",
            command=lambda n=name: self.choose_game(n),
            bg=PANEL2, fg=TEXT, activebackground=PURPLE,
            activeforeground="white", relief="flat",
            cursor="hand2", padx=12, pady=7
        ).pack(side="left", padx=(8, 0))

    def play_page(self):
        title_row = tk.Frame(self.ui, bg=BG)
        title_row.pack(fill="x", pady=(0, 5))
        tk.Label(
            title_row, text="Tus juegos", bg=BG, fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(side="left")
        tk.Button(
            title_row, text="Detectar automáticamente",
            command=self.detect_and_refresh,
            bg=PANEL2, fg=TEXT, activebackground=PURPLE,
            activeforeground="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        ).pack(side="right")

        for game in GAMES:
            self.card(game["name"], game["description"])

        tk.Label(
            self.ui,
            text="Los programas se ejecutan desde archivos instalados en tu PC.",
            bg=BG, fg="#d49b48", font=("Segoe UI", 8),
            wraplength=420
        ).pack(anchor="w", pady=8)

    def install_page(self):
        intro = tk.Frame(self.ui, bg=PANEL, padx=14, pady=12)
        intro.pack(fill="x", pady=(0, 8))
        tk.Label(
            intro, text="Instalar y actualizar", bg=PANEL, fg=TEXT,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor="w")
        tk.Label(
            intro,
            text="Consulta las versiones publicadas en GitHub. Si un proyecto no publica instalador para Windows, te lo indicaremos.",
            bg=PANEL, fg=MUTED, font=("Segoe UI", 8),
            wraplength=410, justify="left"
        ).pack(anchor="w", pady=(4, 8))
        tk.Button(
            intro, text="Comprobar actualizaciones",
            command=self.check_all_releases,
            bg=PURPLE, fg="white", activebackground="#a76bff",
            relief="flat", cursor="hand2", padx=12, pady=7
        ).pack(anchor="w")

        self.repo_status = {}
        for app_name, repo in REPOSITORIES.items():
            card = tk.Frame(self.ui, bg=PANEL, padx=12, pady=9)
            card.pack(fill="x", pady=4)
            head = tk.Frame(card, bg=PANEL)
            head.pack(fill="x")
            tk.Label(
                head, text=app_name, bg=PANEL, fg=TEXT,
                font=("Segoe UI", 10, "bold")
            ).pack(side="left")
            tk.Label(
                head, text=repo, bg=PANEL, fg=MUTED,
                font=("Segoe UI", 7)
            ).pack(side="right")
            status = tk.Label(
                card, text="Sin comprobar", bg=PANEL, fg=MUTED,
                font=("Segoe UI", 8), wraplength=410, justify="left"
            )
            status.pack(anchor="w", pady=(5, 6))
            self.repo_status[app_name] = status

            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x")
            tk.Button(
                row, text="Ver GitHub",
                command=lambda r=repo: webbrowser.open(f"https://github.com/{r}"),
                bg=PANEL2, fg=TEXT, activebackground=PURPLE,
                activeforeground="white", relief="flat",
                cursor="hand2", padx=10, pady=5
            ).pack(side="left")
            tk.Button(
                row, text="Instalar / actualizar",
                command=lambda a=app_name, r=repo: self.install_latest_release(a, r),
                bg=GREEN, fg="#062417", activebackground="#62f5b5",
                relief="flat", cursor="hand2", padx=10, pady=5
            ).pack(side="right")

        tk.Label(
            self.ui,
            text="La descarga automática solo funciona si el proyecto publica instaladores en GitHub Releases.",
            bg=BG, fg="#d49b48", font=("Segoe UI", 8),
            wraplength=420, justify="left"
        ).pack(anchor="w", pady=7)

    def github_release(self, repo):
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "XboxEnPC-Launcher/1.0",
                "Accept": "application/vnd.github+json",
            }
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def check_all_releases(self):
        for label in self.repo_status.values():
            label.config(text="Comprobando GitHub…", fg=MUTED)

        def worker():
            results = {}
            for name, repo in REPOSITORIES.items():
                try:
                    release = self.github_release(repo)
                    assets = release.get("assets", [])
                    installers = [
                        asset for asset in assets
                        if asset.get("name", "").lower().endswith((".exe", ".msi", ".zip"))
                    ]
                    results[name] = (
                        release.get("tag_name", "Versión sin etiqueta"),
                        len(installers),
                    )
                except urllib.error.HTTPError as error:
                    results[name] = ("Sin releases publicados" if error.code == 404 else f"Error HTTP {error.code}", 0)
                except Exception as error:
                    results[name] = (f"No se pudo consultar: {error}", 0)
            self.root.after(0, lambda: self.show_release_results(results))

        threading.Thread(target=worker, daemon=True).start()

    def show_release_results(self, results):
        for name, (version, count) in results.items():
            label = self.repo_status.get(name)
            if not label:
                continue
            if count:
                label.config(text=f"{version} · {count} archivo(s) descargable(s)", fg=GREEN)
            elif "Sin releases" in version:
                label.config(text="No hay instalador publicado en Releases; solo está disponible el código fuente.", fg="#e7b45b")
            else:
                label.config(text=version, fg="#e7b45b")

    def install_latest_release(self, app_name, repo):
        status = self.repo_status.get(app_name)
        if status:
            status.config(text="Buscando instalador oficial…", fg=MUTED)

        def worker():
            try:
                release = self.github_release(repo)
                assets = release.get("assets", [])
                candidates = [
                    asset for asset in assets
                    if asset.get("name", "").lower().endswith((".exe", ".msi", ".zip"))
                ]
                if not candidates:
                    result = ("none", release.get("tag_name", ""))
                else:
                    windows = [
                        asset for asset in candidates
                        if any(word in asset.get("name", "").lower()
                               for word in ("windows", "win64", "win-x64", "x64"))
                    ]
                    result = ("asset", (windows or candidates)[0], release.get("tag_name", ""))
            except urllib.error.HTTPError as error:
                result = ("missing" if error.code == 404 else "error", str(error))
            except Exception as error:
                result = ("error", str(error))
            self.root.after(0, lambda: self.handle_install_result(app_name, repo, result))

        threading.Thread(target=worker, daemon=True).start()

    def handle_install_result(self, app_name, repo, result):
        kind = result[0]
        if kind == "none":
            messagebox.showinfo(
                "Sin instalador disponible",
                f"{app_name} no tiene un instalador .exe, .msi o .zip publicado en GitHub Releases."
            )
            return
        if kind == "missing":
            messagebox.showinfo("Sin versiones publicadas", f"{app_name} todavía no tiene versiones publicadas.")
            return
        if kind == "error":
            messagebox.showerror("Error de GitHub", result[1])
            return

        asset, tag = result[1], result[2]
        filename = asset.get("name", "")
        if not messagebox.askyesno(
            "Confirmar descarga",
            f"¿Descargar {filename} ({tag}) desde {repo}?\n\nInstala archivos solo si confías en el proyecto."
        ):
            return
        threading.Thread(
            target=self.download_release_asset,
            args=(app_name, asset),
            daemon=True
        ).start()

    def download_release_asset(self, app_name, asset):
        try:
            target_dir = APP_DIR / "downloads"
            target_dir.mkdir(parents=True, exist_ok=True)
            filename = Path(asset["name"]).name
            destination = target_dir / filename
            request = urllib.request.Request(
                asset["browser_download_url"],
                headers={"User-Agent": "XboxEnPC-Launcher/1.0"}
            )
            with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as output:
                shutil.copyfileobj(response, output)
            self.root.after(0, lambda: self.finish_release_download(app_name, destination))
        except Exception as error:
            self.root.after(0, lambda: messagebox.showerror("Descarga fallida", str(error)))

    def finish_release_download(self, app_name, path):
        if path.suffix.lower() == ".zip":
            extract_to = APP_DIR / "apps" / app_name
            try:
                extract_to.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(path) as archive:
                    base = extract_to.resolve()
                    for member in archive.infolist():
                        resolved = (extract_to / member.filename).resolve()
                        if base not in resolved.parents and resolved != base:
                            raise ValueError("El ZIP contiene una ruta no segura.")
                    archive.extractall(extract_to)
                messagebox.showinfo(
                    "Descarga completada",
                    f"Archivo extraído en:\n{extract_to}\n\nDespués selecciona el ejecutable desde la pestaña Jugar."
                )
            except Exception as error:
                messagebox.showerror("No se pudo extraer", str(error))
        else:
            if messagebox.askyesno(
                "Descarga completada",
                f"Se descargó {path.name}. ¿Quieres abrir el instalador ahora?"
            ):
                try:
                    os.startfile(str(path))
                except Exception as error:
                    messagebox.showerror("No se pudo ejecutar", str(error))

    def choose_game(self, name):
        path = filedialog.askopenfilename(
            title=f"Seleccionar ejecutable de {name}",
            filetypes=[("Aplicaciones", "*.exe"), ("Todos los archivos", "*.*")]
        )
        if path:
            self.config.setdefault("games", {})[name] = path
            self.save_config()
            self.build()

    def launch_game(self, name):
        path = self.config.get("games", {}).get(name, "")
        if not path or not Path(path).is_file():
            messagebox.showinfo(
                "Selecciona el programa",
                f"Primero elige el archivo .exe de {name}."
            )
            self.choose_game(name)
            return
        try:
            if os.name == "nt" and path.lower().endswith((".lnk", ".url")):
                os.startfile(path)
            else:
                subprocess.Popen([path], cwd=str(Path(path).parent))
        except Exception as error:
            messagebox.showerror("No se pudo iniciar", str(error))

    def settings(self):
        messagebox.showinfo(
            "Configuración",
            "Los ejecutables seleccionados se guardan en tu perfil de Windows. Puedes cambiarlos con «Elegir .exe»."
        )


if __name__ == "__main__":
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
