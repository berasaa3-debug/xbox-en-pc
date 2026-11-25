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

