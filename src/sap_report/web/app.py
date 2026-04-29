from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, render_template, request, send_file, url_for

from sap_report.application import PAYMENT_ACCOUNT_OPTIONS
from sap_report.bootstrap import build_service


MODULES = [
    {
        "page": "home",
        "title": "Panel principal",
        "subtitle": "Selecciona un módulo en la barra lateral.",
        "url": "/",
    },
    {
        "page": "probar-conexiones",
        "title": "Probar conexiones",
        "subtitle": "Verifica SAP, PostgreSQL y MySQL.",
        "url": "/probar-conexiones",
    },
    {
        "page": "ejecutar-reporte",
        "title": "Ejecutar reporte",
        "subtitle": "Genera SAP, TUTATI y comparación.",
        "url": "/ejecutar-reporte",
    },
    {
        "page": "validar-articulos",
        "title": "Validar artículos",
        "subtitle": "Patch ETL y URLs de validación.",
        "url": "/validar-articulos",
    },
    {
        "page": "validar-igv",
        "title": "Validar IGV",
        "subtitle": "Cruces y acciones operativas.",
        "url": "/validar-igv",
    },
    {
        "page": "revisar-hilos",
        "title": "Revisar hilos",
        "subtitle": "Consulta rápida de pendientes.",
        "url": "/revisar-hilos",
    },
    {
        "page": "prestamo",
        "title": "Préstamo",
        "subtitle": "Diferencias de stock recientes.",
        "url": "/prestamo",
    },
    {
        "page": "validar-pagos",
        "title": "Validar pagos",
        "subtitle": "Comparación SAP vs TUTATI.",
        "url": "/validar-pagos",
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
