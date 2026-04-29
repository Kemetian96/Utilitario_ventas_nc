import os
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser
from datetime import date, datetime
from tkinter import scrolledtext
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from sap_report.application import PAYMENT_ACCOUNT_OPTIONS, ReportService

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None


def _parse_env_date(value: str) -> date:
    # Acepta fecha ISO o YYYY-MM-DD.
    value = value.strip()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d").date()


def _find_browser_cmd() -> str | None:
    # Prioriza Chrome y luego Brave en Windows.
    candidates = [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("brave"),
        shutil.which("brave.exe"),
    ]
    for cand in candidates:
        if cand:
            return cand

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    paths = [
        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def run_ui(
    service: ReportService,
    fecha_inicio_default_raw: str,
    fecha_fin_default_raw: str,
    ui_width: int,
    ui_height: int,
) -> None:
    # Dependencia de selector de fecha.
    if DateEntry is None:
        raise RuntimeError("Falta dependencia 'tkcalendar'. Instala con: pip install tkcalendar")

    # Valores iniciales del calendario.
    fecha_inicio_default = _parse_env_date(fecha_inicio_default_raw)
    fecha_fin_default = _parse_env_date(fecha_fin_default_raw)

    # Configura ventana principal.
    root = tk.Tk()
    root.title("Reporte SAP")
    root.geometry(f"{ui_width}x{max(ui_height, 320)}")
    root.resizable(False, False)

    # Estilos visuales (tema claro con acento).
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    bg = "#F6F7FB"
    card_bg = "#FFFFFF"
    accent = "#2B7A78"
    accent_dark = "#1F5F5D"
    text_main = "#1F2937"
    text_muted = "#6B7280"

    root.configure(bg=bg)
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card_bg, borderwidth=1, relief="solid")
    style.configure("TLabel", background=bg, foreground=text_main, font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=bg, foreground=text_muted, font=("Segoe UI", 9))
    style.configure("Accent.TButton", background=accent, foreground="white", padding=(10, 6))
    style.map(
        "Accent.TButton",
        background=[("active", accent_dark), ("pressed", accent_dark)],
        foreground=[("active", "white"), ("pressed", "white")],
    )
    style.configure("Secondary.TButton", background=card_bg, foreground=text_main, padding=(10, 6))
    style.configure("Small.TButton", background=card_bg, foreground=text_main, padding=(3, 3), font=("Segoe UI",7))
    style.map(
        "Secondary.TButton",
        background=[("active", "#EEF2F7"), ("pressed", "#E5E7EB")],
    )

    estado_var = tk.StringVar(value="Selecciona el rango y ejecuta.")

    # Layout principal.
    main = ttk.Frame(root, padding=18)
    main.pack(fill="both", expand=True)

    title = ttk.Label(main, text="Reporte SAP", font=("Segoe UI", 12, "bold"), foreground=text_main)
    title.pack(anchor="w", pady=(0, 8))

    header = ttk.Frame(main)
    header.pack(fill="x", pady=(0, 6))
    header_label = ttk.Label(header, text="Rango de fechas", font=("Segoe UI", 10, "bold"), foreground=text_main)
    header_label.pack(side="left")
    probar_btn = ttk.Button(header, text="Probar conexion", width=14, style="Small.TButton")
    probar_btn.pack(side="right")

    card = ttk.Frame(main, padding=12, style="Card.TFrame")
    card.pack(fill="x")

    ttk.Label(card, text="Fecha inicio").grid(row=0, column=0, sticky="w", pady=(0, 8))
    fecha_inicio_entry = DateEntry(
        card,
        width=16,
        date_pattern="yyyy-mm-dd",
        year=fecha_inicio_default.year,
        month=fecha_inicio_default.month,
        day=fecha_inicio_default.day,
    )
    fecha_inicio_entry.grid(row=0, column=1, sticky="w", pady=(0, 8), padx=(8, 0))

    ttk.Label(card, text="Fecha fin").grid(row=1, column=0, sticky="w")
    fecha_fin_entry = DateEntry(
        card,
        width=16,
        date_pattern="yyyy-mm-dd",
        year=fecha_fin_default.year,
        month=fecha_fin_default.month,
        day=fecha_fin_default.day,
    )
    fecha_fin_entry.grid(row=1, column=1, sticky="w", padx=(8, 0))

    actions = ttk.Frame(main)
    actions.pack(fill="x", pady=(14, 0))
    actions.grid_columnconfigure(0, weight=1)
    actions.grid_columnconfigure(1, weight=1)

    validar_btn = ttk.Button(actions, text="Validar Articulos", width=17, style="Secondary.TButton")
    validar_btn.grid(row=0, column=0, sticky="w")
    validar_igv_btn = ttk.Button(actions, text="Validar Igv", width=17, style="Secondary.TButton")
    validar_igv_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

    revisar_hilos_btn = ttk.Button(actions, text="Revisar Hilos", width=17, style="Secondary.TButton")
    revisar_hilos_btn.grid(row=1, column=0, sticky="w", pady=(8, 0))
    prestamo_btn = ttk.Button(actions, text="Prestamo", width=17, style="Secondary.TButton")
    prestamo_btn.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

    validar_pagos_btn = ttk.Button(actions, text="Validar Pagos", width=17, style="Secondary.TButton")
    validar_pagos_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    ejecutar_btn = ttk.Button(actions, text="Ejecutar reporte", width=17, style="Accent.TButton")
    ejecutar_btn.grid(row=3, column=0, columnspan=2, pady=(10, 0))

    ttk.Label(main, textvariable=estado_var, style="Muted.TLabel").pack(anchor="w", pady=(14, 0))

    running = {"value": False}

    def set_estado(msg: str) -> None:
        # Actualiza etiqueta de estado desde cualquier hilo.
        root.after(0, lambda: estado_var.set(msg))

    def _centrar_ventana(window: tk.Toplevel, width: int, height: int) -> None:
        # Centra una ventana en la pantalla con tamaño fijo.
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = max(0, int((screen_w - width) / 2))
        y = max(0, int((screen_h - height) / 2))
        window.geometry(f"{width}x{height}+{x}+{y}")

    def on_run() -> None:
        # Evita ejecuciones simultaneas.
        if running["value"]:
            return

        fecha_inicio = fecha_inicio_entry.get_date()
        fecha_fin = fecha_fin_entry.get_date()

        running["value"] = True
        ejecutar_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Ejecutando consulta...")

        def worker() -> None:
            # Ejecuta en segundo plano para no congelar UI.
            try:
                totals = service.ejecutar_reporte(
                    fecha_inicio_date=fecha_inicio,
                    fecha_fin_date=fecha_fin,
                    status_cb=set_estado,
                )
                root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Ejecucion completada",
                        "SAP filas: {sap}\nPostgreSQL filas: {pg}\n\n"
                        "SAP error: {sap_err}\nPostgreSQL error: {pg_err}\nComparacion: {comp_err}\nComparacion NC: {comp_nc_err}".format(
                            sap=totals["sap"],
                            pg=totals["postgres"],
                            sap_err=totals["sap_error"] or "OK",
                            pg_err=totals["postgres_error"] or "OK",
                            comp_err=totals["comparacion_error"] or "OK",
                            comp_nc_err=totals["comparacion_nc_error"] or "OK",
                        ),
                    ),
                )
                set_estado("Proceso completado.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker, daemon=True).start()

    def on_test() -> None:
        # Prueba conexiones SAP/PostgreSQL sin ejecutar reporte.
        if running["value"]:
            return
        running["value"] = True
        ejecutar_btn.state(["disabled"])
        probar_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Probando conexiones...")

        def worker_test() -> None:
            # Test en background para mantener interfaz fluida.
            try:
                result = service.probar_conexiones()
                root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Resultado conexiones",
                        "SAP: {sap}\nPostgreSQL: {pg}\nMySQL: {mysql}".format(
                            sap=result["sap"],
                            pg=result["postgres"],
                            mysql=result["mysql"],
                        ),
                    ),
                )
                set_estado("Prueba de conexiones completada.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: probar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker_test, daemon=True).start()

    def on_validar() -> None:
        # Ejecuta validacion de articulos sin bloquear la UI.
        if running["value"]:
            return
        running["value"] = True
        ejecutar_btn.state(["disabled"])
        probar_btn.state(["disabled"])
        validar_btn.state(["disabled"])
        validar_igv_btn.state(["disabled"])
        revisar_hilos_btn.state(["disabled"])
        prestamo_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Validando articulos...")

        def worker_validar() -> None:
            try:
                urls = service.validar_articulos(status_cb=set_estado)
                if urls:
                    browser_cmd = _find_browser_cmd()
                    if browser_cmd:
                        subprocess.Popen([browser_cmd, "--guest", "--new-window", urls[0]])
                        for url in urls[1:]:
                            subprocess.Popen([browser_cmd, "--guest", "--new-tab", url])
                    else:
                        webbrowser.open_new(urls[0])
                        for url in urls[1:]:
                            webbrowser.open_new_tab(url)
                root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Validar Articulos",
                        f"Se abrieron {len(urls)} URLs en el navegador.",
                    ),
                )
                set_estado("Validacion completada.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: probar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_igv_btn.state(["!disabled"]))
                root.after(0, lambda: revisar_hilos_btn.state(["!disabled"]))
                root.after(0, lambda: prestamo_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker_validar, daemon=True).start()

    def on_validar_igv() -> None:
        # Ejecuta validacion IGV sin bloquear la UI.
        if running["value"]:
            return
        running["value"] = True
        ejecutar_btn.state(["disabled"])
        probar_btn.state(["disabled"])
        validar_btn.state(["disabled"])
        validar_igv_btn.state(["disabled"])
        revisar_hilos_btn.state(["disabled"])
        prestamo_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Validando IGV...")

        def worker_igv() -> None:
            try:
                resumen = service.validar_igv(status_cb=set_estado)
                root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Validar Igv",
                        "U_BOT_DOCENTRY detectados: {sap_docentries}\n"
                        "Items total: {items_total}\nItems IGV: {items_igv}\n"
                        "Actualizados Comercial: {upd_comercial}\nActualizados Pedral: {upd_pedral}\n"
                        "Hilos actualizados: {upd_hilos}\n"
                        "SP ORDER ejecutados: {sp_orders}\nSP RMA ejecutados: {sp_rmas}".format(
                            sap_docentries=resumen["sap_docentries"],
                            items_total=resumen["items_total"],
                            items_igv=resumen["items_igv"],
                            upd_comercial=resumen["upd_comercial"],
                            upd_pedral=resumen["upd_pedral"],
                            upd_hilos=resumen["upd_hilos"],
                            sp_orders=resumen["sp_orders"],
                            sp_rmas=resumen["sp_rmas"],
                        ),
                    ),
                )
                docentries = resumen.get("docentries", [])
                if docentries:
                    root.after(0, lambda: _mostrar_docentries(docentries, "U_BOT_DOCENTRY Validar IGV"))
                set_estado("Validacion IGV completada.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: probar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_igv_btn.state(["!disabled"]))
                root.after(0, lambda: revisar_hilos_btn.state(["!disabled"]))
                root.after(0, lambda: prestamo_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker_igv, daemon=True).start()

    def _mostrar_hilos(rows: list[tuple[Any, ...]]) -> None:
        # Muestra resultados en una ventana tipo tabla.
        window = tk.Toplevel(root)
        window.title("Revisar Hilos")
        window.geometry("360x320")
        window.configure(bg=bg)

        table_frame = ttk.Frame(window)
        table_frame.pack(fill="both", expand=True, padx=12, pady=12)

        columns = ("hilo", "cantidad")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        tree.heading("hilo", text="Hilo")
        tree.heading("cantidad", text="Cantidad")
        tree.column("hilo", width=160, anchor="w")
        tree.column("cantidad", width=120, anchor="center")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        for row in rows:
            hilo = row[0] if len(row) > 0 else ""
            cantidad = row[1] if len(row) > 1 else ""
            tree.insert("", "end", values=(hilo, cantidad))

    def _mostrar_prestamo(rows: list[tuple[Any, ...]], cols: list[str]) -> None:
        # Muestra resultados de prestamo en tabla.
        window = tk.Toplevel(root)
        window.title("Prestamo")
        _centrar_ventana(window, 980, 460)
        window.configure(bg=bg)

        table_frame = ttk.Frame(window)
        table_frame.pack(fill="both", expand=True, padx=12, pady=12)

        columns = tuple(c.lower() for c in cols)
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=10)
        for col in cols:
            key = col.lower()
            tree.heading(key, text=col)
            width = 120 if key in ("material", "centro") else 140
            if key == "u_bot_docentry":
                width = 150
            tree.column(key, width=width, anchor="center")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        for row in rows:
            tree.insert("", "end", values=row)

        def _copiar_filas(filas: list[tuple[Any, ...]]) -> None:
            if not filas:
                return
            header = "\t".join(cols)
            body = "\n".join("\t".join(str(v) for v in fila) for fila in filas)
            texto = header + "\n" + body
            window.clipboard_clear()
            window.clipboard_append(texto)
            window.update()

        def _copiar_seleccion() -> None:
            seleccion = tree.selection()
            filas = [tree.item(item_id, "values") for item_id in seleccion]
            _copiar_filas(filas)

        def _copiar_todo() -> None:
            filas = [tree.item(item_id, "values") for item_id in tree.get_children("")]
            _copiar_filas(filas)

        botones = ttk.Frame(window)
        botones.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(botones, text="Copiar seleccion", style="Secondary.TButton", command=_copiar_seleccion).pack(
            side="left"
        )
        ttk.Button(botones, text="Copiar todo", style="Secondary.TButton", command=_copiar_todo).pack(
            side="left", padx=(8, 0)
        )

    def _mostrar_docentries(docentries: list[str], title: str = "U_BOT_DOCENTRY evaluados") -> None:
        # Muestra lista de U_BOT_DOCENTRY con opcion de copiar.
        window = tk.Toplevel(root)
        window.title(f"{title} ({len(docentries)})")
        _centrar_ventana(window, 420, 460)
        window.configure(bg=bg)

        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        columns = ("docentry",)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        tree.heading("docentry", text="U_BOT_DOCENTRY")
        tree.column("docentry", width=240, anchor="center")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        for value in docentries:
            tree.insert("", "end", values=(value,))

        def _copiar_filas(filas: list[tuple[Any, ...]]) -> None:
            if not filas:
                return
            body = "\n".join(str(fila[0]) for fila in filas)
            window.clipboard_clear()
            window.clipboard_append(body)
            window.update()

        def _copiar_seleccion() -> None:
            seleccion = tree.selection()
            filas = [tree.item(item_id, "values") for item_id in seleccion]
            _copiar_filas(filas)

        def _copiar_todo_doc() -> None:
            filas = [tree.item(item_id, "values") for item_id in tree.get_children("")]
            _copiar_filas(filas)

        botones = ttk.Frame(window)
        botones.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(botones, text="Copiar seleccion", style="Secondary.TButton", command=_copiar_seleccion).pack(
            side="left"
        )
        ttk.Button(botones, text="Copiar todo", style="Secondary.TButton", command=_copiar_todo_doc).pack(
            side="left", padx=(8, 0)
        )

    def _mostrar_validacion_pagos(resultado: dict[str, Any]) -> None:
        # Muestra resumen y diferencias de la validacion de pagos.
        window = tk.Toplevel(root)
        window.title("Validar Pagos")
        _centrar_ventana(window, 920, 520)
        window.configure(bg=bg)
        fecha_resultado = _parse_env_date(resultado["fecha"])
        tipo_pago_resultado = resultado["tipo_pago"]

        def _cerrar_y_regresar() -> None:
            if window.winfo_exists():
                window.destroy()
            root.after(
                0,
                lambda: _abrir_validar_pagos(
                    fecha_default=fecha_resultado,
                    tipo_pago_default=tipo_pago_resultado,
                ),
            )

        window.protocol("WM_DELETE_WINDOW", _cerrar_y_regresar)

        resumen_texto = (
            f"Fecha: {resultado['fecha']} | Tipo: {resultado['tipo_pago']} | "
            f"SAP: {resultado['sap_total']} | TUTATI: {resultado['tutati_total']} | "
            f"Faltan en SAP: {resultado['faltan_en_sap']} | "
            f"Faltan en TUTATI: {resultado['faltan_en_tutati']} | "
            f"Montos diferentes: {resultado['montos_diferentes']} | "
            f"Coinciden: {resultado['coinciden']}"
        )

        ttk.Label(
            window,
            text=resumen_texto,
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 8))

        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cols = resultado["cols"]
        rows = resultado["rows"]
        columns = tuple(c.lower() for c in cols)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=14)
        for col in cols:
            key = col.lower()
            tree.heading(key, text=col)
            width = 150
            if key == "orden":
                width = 240
            tree.column(key, width=width, anchor="center")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        if rows:
            for row in rows:
                tree.insert("", "end", values=row)
        else:
            tree.insert("", "end", values=("SIN_DIFERENCIAS", "", 0.0, 0.0, 0.0))

        def _copiar_filas(filas: list[tuple[Any, ...]]) -> None:
            if not filas:
                return
            header = "\t".join(cols)
            body = "\n".join("\t".join(str(v) for v in fila) for fila in filas)
            texto = header + "\n" + body
            window.clipboard_clear()
            window.clipboard_append(texto)
            window.update()

        def _copiar_seleccion() -> None:
            seleccion = tree.selection()
            filas = [tree.item(item_id, "values") for item_id in seleccion]
            _copiar_filas(filas)

        def _copiar_todo() -> None:
            filas = [tree.item(item_id, "values") for item_id in tree.get_children("")]
            _copiar_filas(filas)

        botones = ttk.Frame(window)
        botones.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(botones, text="Copiar seleccion", style="Secondary.TButton", command=_copiar_seleccion).pack(
            side="left"
        )
        ttk.Button(botones, text="Copiar todo", style="Secondary.TButton", command=_copiar_todo).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(botones, text="Volver", style="Secondary.TButton", command=_cerrar_y_regresar).pack(
            side="right"
        )

    def _abrir_validar_pagos(
        fecha_default: date | None = None,
        tipo_pago_default: str | None = None,
    ) -> None:
        # Abre ventana para elegir fecha y medio de pago.
        if running["value"]:
            return

        window = tk.Toplevel(root)
        window.title("Validar Pagos")
        _centrar_ventana(window, 390, 220)
        window.configure(bg=bg)
        window.transient(root)
        window.grab_set()
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", lambda: None if running["value"] else window.destroy())

        frame = ttk.Frame(window, padding=12, style="Card.TFrame")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(frame, text="Fecha").grid(row=0, column=0, sticky="w", pady=(0, 10))
        fecha_pago_entry = DateEntry(
            frame,
            width=16,
            date_pattern="yyyy-mm-dd",
            year=(fecha_default or fecha_fin_default).year,
            month=(fecha_default or fecha_fin_default).month,
            day=(fecha_default or fecha_fin_default).day,
        )
        fecha_pago_entry.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 10))

        ttk.Label(frame, text="Tipo de pago").grid(row=1, column=0, sticky="w")
        tipo_pago_var = tk.StringVar(value=tipo_pago_default or "Tarjetas Visanet")
        tipo_pago_combo = ttk.Combobox(
            frame,
            textvariable=tipo_pago_var,
            values=PAYMENT_ACCOUNT_OPTIONS,
            state="readonly",
            width=28,
        )
        tipo_pago_combo.grid(row=1, column=1, sticky="w", padx=(8, 0))

        ejecutar_pago_btn = ttk.Button(frame, text="Validar pagos", style="Accent.TButton")
        ejecutar_pago_btn.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))

        def _toggle_dialog(enabled: bool) -> None:
            if not window.winfo_exists():
                return
            fecha_pago_entry.configure(state="normal" if enabled else "disabled")
            tipo_pago_combo.configure(state="readonly" if enabled else "disabled")
            if enabled:
                ejecutar_pago_btn.state(["!disabled"])
            else:
                ejecutar_pago_btn.state(["disabled"])

        def _ejecutar_validar_pagos() -> None:
            if running["value"]:
                return

            fecha_pago = fecha_pago_entry.get_date()
            tipo_pago = tipo_pago_var.get().strip()
            if not tipo_pago:
                messagebox.showerror("Error", "Debe seleccionar un tipo de pago.", parent=window)
                return

            running["value"] = True
            ejecutar_btn.state(["disabled"])
            probar_btn.state(["disabled"])
            validar_btn.state(["disabled"])
            validar_igv_btn.state(["disabled"])
            revisar_hilos_btn.state(["disabled"])
            prestamo_btn.state(["disabled"])
            validar_pagos_btn.state(["disabled"])
            _toggle_dialog(False)
            set_estado(f"Validando pagos: {fecha_pago} | {tipo_pago}")

            def worker_validar_pagos() -> None:
                try:
                    resultado = service.validar_pagos(
                        fecha=fecha_pago,
                        account_name=tipo_pago,
                        status_cb=set_estado,
                    )
                    root.after(0, lambda: _mostrar_validacion_pagos(resultado))
                    root.after(0, window.destroy)
                    set_estado("Validar pagos completado.")
                except Exception as exc:
                    root.after(0, lambda: messagebox.showerror("Error", str(exc), parent=window))
                    set_estado(f"Error: {exc}")
                finally:
                    running["value"] = False
                    root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                    root.after(0, lambda: probar_btn.state(["!disabled"]))
                    root.after(0, lambda: validar_btn.state(["!disabled"]))
                    root.after(0, lambda: validar_igv_btn.state(["!disabled"]))
                    root.after(0, lambda: revisar_hilos_btn.state(["!disabled"]))
                    root.after(0, lambda: prestamo_btn.state(["!disabled"]))
                    root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))
                    root.after(0, lambda: _toggle_dialog(True))

            threading.Thread(target=worker_validar_pagos, daemon=True).start()

        ejecutar_pago_btn.configure(command=_ejecutar_validar_pagos)

    def on_revisar_hilos() -> None:
        # Ejecuta revision de hilos sin bloquear la UI.
        if running["value"]:
            return
        running["value"] = True
        ejecutar_btn.state(["disabled"])
        probar_btn.state(["disabled"])
        validar_btn.state(["disabled"])
        validar_igv_btn.state(["disabled"])
        revisar_hilos_btn.state(["disabled"])
        prestamo_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Revisando hilos...")

        def worker_hilos() -> None:
            try:
                rows, _cols = service.revisar_hilos()
                root.after(0, lambda: _mostrar_hilos(rows))
                set_estado("Revision de hilos completada.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: probar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_igv_btn.state(["!disabled"]))
                root.after(0, lambda: revisar_hilos_btn.state(["!disabled"]))
                root.after(0, lambda: prestamo_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker_hilos, daemon=True).start()

    def on_prestamo() -> None:
        # Ejecuta Prestamo usando U_BOT_KEY detectados en LOGPROCESO.
        if running["value"]:
            return
        running["value"] = True
        ejecutar_btn.state(["disabled"])
        probar_btn.state(["disabled"])
        validar_btn.state(["disabled"])
        validar_igv_btn.state(["disabled"])
        revisar_hilos_btn.state(["disabled"])
        prestamo_btn.state(["disabled"])
        validar_pagos_btn.state(["disabled"])
        set_estado("Prestamo: buscando casos con inventario negativo...")

        def worker_prestamo() -> None:
            try:
                rows, cols = service.consultar_prestamo(status_cb=set_estado)
                if not rows:
                    root.after(
                        0,
                        lambda: messagebox.showinfo(
                            "Prestamo",
                            "No se encontraron resultados para los U_BOT_KEY detectados en los ultimos 3 dias.",
                        ),
                    )
                else:
                    root.after(0, lambda: _mostrar_prestamo(rows, cols))
                set_estado("Prestamo completado.")
            except Exception as exc:
                root.after(0, lambda: messagebox.showerror("Error", str(exc)))
                set_estado(f"Error: {exc}")
            finally:
                running["value"] = False
                root.after(0, lambda: ejecutar_btn.state(["!disabled"]))
                root.after(0, lambda: probar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_btn.state(["!disabled"]))
                root.after(0, lambda: validar_igv_btn.state(["!disabled"]))
                root.after(0, lambda: revisar_hilos_btn.state(["!disabled"]))
                root.after(0, lambda: prestamo_btn.state(["!disabled"]))
                root.after(0, lambda: validar_pagos_btn.state(["!disabled"]))

        threading.Thread(target=worker_prestamo, daemon=True).start()

    ejecutar_btn.configure(command=on_run)
    probar_btn.configure(command=on_test)
    validar_btn.configure(command=on_validar)
    validar_igv_btn.configure(command=on_validar_igv)
    revisar_hilos_btn.configure(command=on_revisar_hilos)
    prestamo_btn.configure(command=on_prestamo)
    validar_pagos_btn.configure(command=_abrir_validar_pagos)
    # Inicia el loop de eventos de Tkinter.
    root.mainloop()


def prompt_env_vars(fields: list[dict[str, object]]) -> dict[str, str]:
    # Solicita credenciales si faltan en .env.
    if not fields:
        return {}
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    result: dict[str, str] = {}
    for field in fields:
        label = str(field.get("label", field.get("key", "")))
        key = str(field.get("key", ""))
        secret = bool(field.get("secret", False))
        while True:
            value = simpledialog.askstring(
                "Credenciales requeridas",
                f"Ingrese {label}:",
                show="*" if secret else None,
                parent=root,
            )
            if value is None:
                root.destroy()
                raise RuntimeError("Ingreso de credenciales cancelado.")
            value = value.strip()
            if value:
                result[key] = value
                break
    root.destroy()
    return result
