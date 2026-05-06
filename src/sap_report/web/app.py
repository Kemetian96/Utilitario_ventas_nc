import os
import shutil
import subprocess
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_file, url_for

from sap_report.application import PAYMENT_ACCOUNT_OPTIONS
from sap_report.bootstrap import build_service


_RESUMEN_CACHE: dict[str, tuple[float, list]] = {}
_RESUMEN_TTL = 600  # segundos


MODULES = [
    {
        "page": "home",
        "title": "Panel principal",
        "subtitle": "Selecciona un módulo.",
        "url": "/",
        "sidebar": False,
    },
    {
        "page": "probar-conexiones",
        "title": "Probar conexiones",
        "subtitle": "Verifica SAP, PostgreSQL y MySQL.",
        "url": "/probar-conexiones",
        "sidebar": False,
    },
    {
        "page": "ejecutar-reporte",
        "title": "Ejecutar reporte",
        "subtitle": "SAP, TUTATI y comparación.",
        "url": "/ejecutar-reporte",
        "sidebar": True,
    },
    {
        "page": "validar-articulos",
        "title": "Validar artículos",
        "subtitle": "Patch ETL y URLs de validación.",
        "url": "/validar-articulos",
        "sidebar": True,
    },
    {
        "page": "validar-igv",
        "title": "Validar IGV",
        "subtitle": "Cruces y acciones operativas.",
        "url": "/validar-igv",
        "sidebar": True,
    },
    {
        "page": "revisar-hilos",
        "title": "Revisar hilos",
        "subtitle": "Consulta rápida de pendientes.",
        "url": "/revisar-hilos",
        "sidebar": False,
    },
    {
        "page": "prestamo",
        "title": "Préstamo",
        "subtitle": "Diferencias de stock recientes.",
        "url": "/prestamo",
        "sidebar": True,
    },
    {
        "page": "validar-pagos",
        "title": "Validar pagos",
        "subtitle": "Comparación SAP vs TUTATI.",
        "url": "/validar-pagos",
        "sidebar": True,
    },
    {
        "page": "por-enviar",
        "title": "Por Enviar",
        "subtitle": "Anuladas, pendientes y ventas.",
        "url": "/por-enviar",
        "sidebar": True,
    },
]


def create_app() -> Flask:
    settings, service = build_service()
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.context_processor
    def inject_layout_context() -> dict[str, Any]:
        if not request.endpoint or request.endpoint == "index":
            current_page = "home"
        else:
            current_page = request.endpoint.replace("_", "-")
        current_module = _get_current_module(current_page)
        return {
            "modules": MODULES,
            "current_module": current_module,
        }

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            current_page="home",
        )

    @app.get("/api/conexiones")
    def api_conexiones():
        try:
            result = service.probar_conexiones()
            return jsonify(result)
        except Exception as exc:
            msg = str(exc)
            return jsonify({"sap": msg, "postgres": msg, "mysql": msg}), 200

    @app.get("/api/hilos")
    def api_hilos():
        try:
            rows, _ = service.revisar_hilos()
            safe_rows = [[str(r[0]), r[1]] for r in (rows or [])]
            return jsonify({"count": len(safe_rows), "rows": safe_rows})
        except Exception as exc:
            return jsonify({"count": -1, "rows": [], "error": str(exc)}), 200

    @app.get("/api/resumen-pagos")
    def api_resumen_pagos():
        fecha_raw = request.args.get("fecha", "").strip()
        if not fecha_raw:
            return jsonify({"error": "Falta el parámetro fecha"}), 400
        try:
            fecha = _parse_date(fecha_raw)
        except Exception:
            return jsonify({"error": "Fecha inválida"}), 400

        force = request.args.get("force", "0") == "1"
        fecha_key = fecha.isoformat()
        if not force:
            cached = _RESUMEN_CACHE.get(fecha_key)
            if cached:
                ts, diferencias = cached
                if time.time() - ts < _RESUMEN_TTL:
                    return jsonify({"fecha": fecha_key, "diferencias": diferencias})

        def _consultar(tipo: str):
            try:
                r = service.validar_pagos(fecha=fecha, account_name=tipo)
                if r["faltan_en_sap"] > 0 or r["faltan_en_tutati"] > 0 or r["montos_diferentes"] > 0:
                    diff_total = round(sum(abs(row[4]) for row in r.get("rows", [])), 2)
                    return {
                        "tipo": tipo,
                        "faltan_sap": r["faltan_en_sap"],
                        "faltan_tutati": r["faltan_en_tutati"],
                        "dif_monto": r["montos_diferentes"],
                        "diff_total": diff_total,
                    }
            except Exception:
                pass
            return None

        resultados: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(_consultar, tipo): tipo for tipo in PAYMENT_ACCOUNT_OPTIONS}
            for future in as_completed(futures):
                item = future.result()
                if item:
                    resultados[item["tipo"]] = item

        diferencias = [resultados[t] for t in PAYMENT_ACCOUNT_OPTIONS if t in resultados]
        _RESUMEN_CACHE[fecha_key] = (time.time(), diferencias)
        return jsonify({"fecha": fecha_key, "diferencias": diferencias})

    @app.post("/api/lanzar-articulos")
    def api_lanzar_articulos():
        data = request.get_json(silent=True) or {}
        urls = [u for u in data.get("urls", []) if isinstance(u, str) and u.startswith("http")]
        if not urls:
            return jsonify({"ok": False, "error": "Sin URLs válidas"}), 400
        browser_cmd = _find_browser_cmd()
        if browser_cmd:
            subprocess.Popen([browser_cmd, "--guest", "--new-window", urls[0]])
            for url in urls[1:]:
                subprocess.Popen([browser_cmd, "--guest", "--new-tab", url])
            return jsonify({"ok": True})
        webbrowser.open_new(urls[0])
        for url in urls[1:]:
            webbrowser.open_new_tab(url)
        return jsonify({"ok": True, "fallback": True})

    @app.route("/probar-conexiones", methods=["GET", "POST"])
    def probar_conexiones() -> str:
        result: dict[str, str] | None = None
        error: str | None = None
        if request.method == "POST":
            try:
                result = service.probar_conexiones()
            except Exception as exc:
                error = str(exc)

        return render_template(
            "probar_conexiones.html",
            current_page="probar-conexiones",
            result=result,
            error=error,
        )

    @app.route("/ejecutar-reporte", methods=["GET", "POST"])
    def ejecutar_reporte() -> str:
        fecha_inicio_value = settings.fecha_inicio_default[:10]
        fecha_fin_value = settings.fecha_fin_default[:10]
        result: dict[str, Any] | None = None
        error: str | None = None

        if request.method == "POST":
            fecha_inicio_value = request.form.get("fecha_inicio", fecha_inicio_value).strip()
            fecha_fin_value = request.form.get("fecha_fin", fecha_fin_value).strip()
            try:
                result = service.ejecutar_reporte(
                    fecha_inicio_date=_parse_date(fecha_inicio_value),
                    fecha_fin_date=_parse_date(fecha_fin_value),
                )
            except Exception as exc:
                error = str(exc)

        return render_template(
            "ejecutar_reporte.html",
            current_page="ejecutar-reporte",
            fecha_inicio_value=fecha_inicio_value,
            fecha_fin_value=fecha_fin_value,
            result=result,
            error=error,
            downloads=_build_downloads(settings),
        )

    @app.route("/validar-articulos", methods=["GET", "POST"])
    def validar_articulos() -> str:
        urls: list[str] | None = None
        error: str | None = None
        if request.method == "POST":
            try:
                urls = service.validar_articulos()
            except Exception as exc:
                error = str(exc)

        return render_template(
            "validar_articulos.html",
            current_page="validar-articulos",
            urls=urls,
            error=error,
        )

    @app.route("/validar-igv", methods=["GET", "POST"])
    def validar_igv() -> str:
        result: dict[str, Any] | None = None
        error: str | None = None
        if request.method == "POST":
            try:
                result = service.validar_igv()
            except Exception as exc:
                error = str(exc)

        return render_template(
            "validar_igv.html",
            current_page="validar-igv",
            result=result,
            error=error,
        )

    @app.route("/revisar-hilos", methods=["GET", "POST"])
    def revisar_hilos() -> str:
        rows: list[tuple[Any, ...]] | None = None
        cols = ["Hilo", "Cantidad"]
        error: str | None = None
        if request.method == "POST":
            try:
                rows, _service_cols = service.revisar_hilos()
            except Exception as exc:
                error = str(exc)

        return render_template(
            "revisar_hilos.html",
            current_page="revisar-hilos",
            rows=rows,
            cols=cols,
            error=error,
        )

    @app.route("/prestamo", methods=["GET", "POST"])
    def prestamo() -> str:
        rows: list[tuple[Any, ...]] | None = None
        cols: list[str] | None = None
        error: str | None = None
        if request.method == "POST":
            try:
                rows, cols = service.consultar_prestamo()
            except Exception as exc:
                error = str(exc)

        return render_template(
            "prestamo.html",
            current_page="prestamo",
            rows=rows,
            cols=cols,
            error=error,
        )

    @app.route("/validar-pagos", methods=["GET", "POST"])
    def validar_pagos() -> str:
        fecha_value = settings.fecha_fin_default[:10]
        tipo_pago_value = "Tarjetas Visanet"
        result: dict[str, Any] | None = None
        error: str | None = None

        if request.method == "POST":
            fecha_value = request.form.get("fecha", fecha_value).strip()
            tipo_pago_value = request.form.get("tipo_pago", tipo_pago_value).strip()
            try:
                fecha_pago = _parse_date(fecha_value)
                result = service.validar_pagos(
                    fecha=fecha_pago,
                    account_name=tipo_pago_value,
                )
            except Exception as exc:
                error = str(exc)

        return render_template(
            "validar_pagos.html",
            current_page="validar-pagos",
            fecha_value=fecha_value,
            tipo_pago_value=tipo_pago_value,
            payment_options=PAYMENT_ACCOUNT_OPTIONS,
            result=result,
            error=error,
        )

    @app.route("/por-enviar", methods=["GET", "POST"])
    def por_enviar() -> str:
        fecha_inicio_value = settings.fecha_inicio_default[:10]
        fecha_fin_value = settings.fecha_fin_default[:10]
        tipo_value = "pendientes"
        rows: list[tuple[Any, ...]] | None = None
        cols: list[str] | None = None
        success: str | None = None
        error: str | None = None

        if request.method == "POST":
            fecha_inicio_value = request.form.get("fecha_inicio", fecha_inicio_value).strip()
            fecha_fin_value = request.form.get("fecha_fin", fecha_fin_value).strip()
            tipo_value = request.form.get("tipo", tipo_value).strip()
            try:
                accion = request.form.get("accion", "consultar").strip()
                if accion == "anular":
                    id_movement_raw = request.form.get("id_movement", "").strip()
                    if not id_movement_raw.isdigit():
                        raise ValueError("Id_movement invalido.")
                    updated = service.anular_movimiento_por_enviar(int(id_movement_raw))
                    if updated > 0:
                        success = f"Movimiento {id_movement_raw} actualizado a estado 9."
                    else:
                        error = f"No se actualizo el movimiento {id_movement_raw}."
                rows, cols = service.consultar_por_enviar(
                    fecha_inicio=_parse_date(fecha_inicio_value),
                    fecha_fin=_parse_date(fecha_fin_value),
                    tipo=tipo_value,
                )
            except Exception as exc:
                error = str(exc)

        return render_template(
            "por_enviar.html",
            current_page="por-enviar",
            fecha_inicio_value=fecha_inicio_value,
            fecha_fin_value=fecha_fin_value,
            tipo_value=tipo_value,
            rows=rows,
            cols=cols,
            success=success,
            error=error,
        )

    @app.get("/descargas/<kind>")
    def descargar_archivo(kind: str):
        output_map = {
            "sap": settings.sap_output_path,
            "tutati": settings.pg_output_path,
            "comparacion": settings.comparacion_output_path,
        }
        raw_path = output_map.get(kind)
        if raw_path is None:
            abort(404)
        final_path = _resolve_output_path(raw_path)
        if not final_path.exists():
            abort(404)
        return send_file(final_path, as_attachment=True, download_name=final_path.name)

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=8000, debug=False)


def _parse_date(raw: str) -> date:
    value = raw.strip()
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return datetime.strptime(value, "%Y-%m-%d").date()


def _resolve_output_path(raw_path: Path) -> Path:
    if raw_path.is_absolute():
        return raw_path
    return (Path.cwd() / raw_path).resolve()


def _build_downloads(settings) -> list[dict[str, str]]:
    return [
        {
            "label": "SAP.xlsx",
            "kind": "sap",
            "url": url_for("descargar_archivo", kind="sap"),
        },
        {
            "label": "TUTATI.xlsx",
            "kind": "tutati",
            "url": url_for("descargar_archivo", kind="tutati"),
        },
        {
            "label": "COMPARACION.xlsx",
            "kind": "comparacion",
            "url": url_for("descargar_archivo", kind="comparacion"),
        },
    ]


def _get_current_module(current_page: str) -> dict[str, str]:
    for module in MODULES:
        if module["page"] == current_page:
            return module
    return MODULES[0]


def _find_browser_cmd() -> str | None:
    candidates = [shutil.which("chrome"), shutil.which("chrome.exe"), shutil.which("brave"), shutil.which("brave.exe")]
    for cand in candidates:
        if cand:
            return cand
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    paths = [
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
        os.path.join(pf86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    return None
