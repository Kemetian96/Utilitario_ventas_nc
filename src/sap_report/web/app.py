import os
import shutil
import subprocess
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, jsonify, render_template, request, send_file, session, url_for

from sap_report.application import PAYMENT_ACCOUNT_OPTIONS
from sap_report.bootstrap import build_service


_RESUMEN_CACHE: dict[str, tuple[float, list]] = {}
_RESUMEN_TTL = 600  # segundos

SL_COMPANIES = {
    "COMERCIALMONT": "B1H_COMERCIALMONT_PROD",
    "PEDRAL": "B1H_PEDRAL_PROD",
}
SL_COMPANY_DEFAULT = "COMERCIALMONT"

SL_BOT_CONFIG = {
    "COMERCIALMONT": {"U_BOT_TIPO": "VTA_COMMONT", "U_BOT_CODCIA": "B1H_COMERCIALMONT_PROD"},
    "PEDRAL":        {"U_BOT_TIPO": "VTA_PEDRAL",  "U_BOT_CODCIA": "B1H_PEDRAL_PROD"},
}


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
        "page": "por-enviar",
        "title": "Por Enviar",
        "subtitle": "Anuladas, pendientes y ventas.",
        "url": "/por-enviar",
        "sidebar": True,
    },
    {
        "page": "prestamo",
        "title": "Préstamo",
        "subtitle": "Diferencias de stock recientes.",
        "url": "/prestamo",
        "sidebar": True,
    },
    {
        "page": "ejecutar-reporte",
        "title": "Ejecutar reporte",
        "subtitle": "SAP, TUTATI y comparación.",
        "url": "/ejecutar-reporte",
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
        "page": "consultar-pago-sap",
        "title": "Consultar pago SAP",
        "subtitle": "Detalle de pago por orden web.",
        "url": "/consultar-pago-sap",
        "sidebar": True,
    },
    {
        "page": "enviar-pago-sap",
        "title": "Envío de pago SAP",
        "subtitle": "Construye el JSON de pago para SAP B1.",
        "url": "/enviar-pago-sap",
        "sidebar": True,
    },
    {
        "page": "validacion-nubefact",
        "title": "Validación Nubefact",
        "subtitle": "Visor de documentos Nubefact últimos 7 días.",
        "url": "/validacion-nubefact",
        "sidebar": True,
    },
    {
        "page": "revisar-hilos",
        "title": "Revisar hilos",
        "subtitle": "Consulta rápida de pendientes.",
        "url": "/revisar-hilos",
        "sidebar": False,
    },
]


def create_app() -> Flask:
    settings, service = build_service()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "sap-web-secret-key-local")

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
                elif accion == "enviar":
                    id_movement_raw = request.form.get("id_movement", "").strip()
                    if not id_movement_raw.isdigit():
                        raise ValueError("Id_movement invalido.")
                    sp_msg = service.enviar_movimiento_por_enviar(int(id_movement_raw))
                    success = sp_msg or f"Movimiento {id_movement_raw} enviado correctamente."
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

    @app.route("/consultar-pago-sap", methods=["GET", "POST"])
    def consultar_pago_sap() -> str:
        import json as _json
        orden_value = ""
        result_json: str | None = None
        pagos: list[dict] = []
        success: str | None = None
        error: str | None = None

        # Sociedad activa desde sesión
        sociedad_key = session.get("sl_sociedad", SL_COMPANY_DEFAULT)
        if sociedad_key not in SL_COMPANIES:
            sociedad_key = SL_COMPANY_DEFAULT

        if request.method == "POST":
            accion = request.form.get("accion", "consultar").strip()

            # Cambio de sociedad
            if accion == "cambiar_sociedad":
                nueva = request.form.get("sociedad", SL_COMPANY_DEFAULT).strip()
                if nueva in SL_COMPANIES:
                    session["sl_sociedad"] = nueva
                    sociedad_key = nueva
                return render_template(
                    "consultar_pago_sap.html",
                    current_page="consultar-pago-sap",
                    orden_value="",
                    result_json=None,
                    pagos=[],
                    success=None,
                    error=None,
                    sociedad_key=sociedad_key,
                    sl_companies=SL_COMPANIES,
                )

            company_db = SL_COMPANIES[sociedad_key]
            orden_value = request.form.get("orden", "").strip()

            if accion == "anular":
                doc_entry_raw = request.form.get("doc_entry", "").strip()
                try:
                    if not doc_entry_raw.isdigit():
                        raise ValueError("DocEntry inválido.")
                    service.anular_pago_sap(int(doc_entry_raw), company_db)
                    success = f"Pago {doc_entry_raw} anulado correctamente en SAP ({sociedad_key})."
                except Exception as exc:
                    error = str(exc)

            if orden_value:
                try:
                    data = service.consultar_pago_sap(orden_value, company_db)
                    result_json = _json.dumps(data, indent=2, ensure_ascii=False)
                    pagos = []
                    for v in data.get("value", []):
                        if not v.get("DocEntry"):
                            continue
                        nombre_pago, tipo_pago = _determinar_tipo_pago(v.get("TransferAccount"), v.get("U_SYP_MPPG"))
                        pagos.append({
                            "doc_entry": v.get("DocEntry"),
                            "nombre_pago": nombre_pago,
                            "tipo_pago": tipo_pago,
                            "fecha": v.get("DocDate", "")[:10],
                            "monto": v.get("TransferSum", 0),
                            "ta": str(v.get("TransferAccount") or ""),
                            "mpg": str(v.get("U_SYP_MPPG") or ""),
                        })
                except Exception as exc:
                    error = str(exc)

        return render_template(
            "consultar_pago_sap.html",
            current_page="consultar-pago-sap",
            orden_value=orden_value,
            result_json=result_json,
            pagos=pagos,
            success=success,
            error=error,
            sociedad_key=sociedad_key,
            sl_companies=SL_COMPANIES,
        )

    @app.route("/enviar-pago-sap", methods=["GET", "POST"])
    def enviar_pago_sap() -> str:
        import json as _json
        result_json: str | None = None
        error: str | None = None
        form_data: dict = {}

        sociedad_key = session.get("sl_sociedad", SL_COMPANY_DEFAULT)
        if sociedad_key not in SL_COMPANIES:
            sociedad_key = SL_COMPANY_DEFAULT

        if request.method == "GET":
            orden_param = request.args.get("orden", "").strip()
            tipo_pago_param = request.args.get("tipo_pago_key", "").strip()
            if orden_param:
                form_data["orden"] = orden_param
            if tipo_pago_param:
                form_data["tipo_pago_key"] = tipo_pago_param
                parts = tipo_pago_param.split("|", 1)
                form_data["transfer_account"] = parts[0] if parts else ""
                form_data["u_syp_mppg"] = parts[1] if len(parts) > 1 else ""

        success: str | None = None

        if request.method == "POST":
            accion = request.form.get("accion", "generar").strip()

            if accion == "enviar":
                payload_raw = request.form.get("payload_json", "").strip()
                try:
                    payload_dict = _json.loads(payload_raw)
                    company_db = SL_COMPANIES[sociedad_key]
                    resp = service.crear_pago_sap(payload_dict, company_db)
                    doc_entry = resp.get("DocEntry", "")
                    success = f"Pago creado correctamente en SAP ({sociedad_key}). DocEntry: {doc_entry}"
                    result_json = payload_raw
                except Exception as exc:
                    error = str(exc)
                    result_json = payload_raw
                return render_template(
                    "enviar_pago_sap.html",
                    current_page="enviar-pago-sap",
                    sociedad_key=sociedad_key,
                    sl_companies=SL_COMPANIES,
                    envio_options=_ENVIO_PAGO_OPTIONS,
                    form_data=form_data,
                    result_json=result_json,
                    error=error,
                    success=success,
                    pagos_candidatos=None,
                )

            if accion == "cambiar_sociedad":
                nueva = request.form.get("sociedad", SL_COMPANY_DEFAULT).strip()
                if nueva in SL_COMPANIES:
                    session["sl_sociedad"] = nueva
                    sociedad_key = nueva
            else:
                form_data = dict(request.form)
                ta = request.form.get("transfer_account", "").strip()
                mpg = request.form.get("u_syp_mppg", "").strip()
                orden = request.form.get("orden", "").strip()

                # Busca id_opt y tipo del método de pago seleccionado
                id_opt: int | None = None
                tipo_opt: str = ""
                nombre_opt: str = ""
                for opt in _ENVIO_PAGO_OPTIONS:
                    if opt["ta"] == ta and opt["mpg"] == mpg:
                        id_opt = opt["id_opt"]
                        tipo_opt = opt["tipo"]
                        nombre_opt = opt["nombre"]
                        break

                try:
                    # Consulta datos desde PostgreSQL
                    pg_rows = service.consultar_datos_pago_pg(orden)

                    if not pg_rows:
                        raise ValueError(f"No se encontró la orden '{orden}' en TUTATI.")

                    # Filtra candidatos por tipo de pago; si no hay match usa todos
                    candidatos = (
                        [r for r in pg_rows if r.get("Pago") == id_opt]
                        if id_opt is not None else []
                    )
                    if not candidatos:
                        candidatos = pg_rows

                    # Múltiples candidatos y aún no se ha confirmado → pedir selección
                    if len(candidatos) > 1 and accion != "confirmar":
                        return render_template(
                            "enviar_pago_sap.html",
                            current_page="enviar-pago-sap",
                            sociedad_key=sociedad_key,
                            sl_companies=SL_COMPANIES,
                            envio_options=_ENVIO_PAGO_OPTIONS,
                            form_data=form_data,
                            result_json=None,
                            error=None,
                            pagos_candidatos=candidatos,
                        )

                    if accion == "confirmar":
                        row_index = int(request.form.get("row_index", 0))
                        datos = candidatos[min(row_index, len(candidatos) - 1)]
                    else:
                        datos = candidatos[0]

                    monto = str(datos.get("monto") or "")
                    bot_cfg = SL_BOT_CONFIG.get(sociedad_key, SL_BOT_CONFIG[SL_COMPANY_DEFAULT])
                    id_store = datos.get("id_stores")

                    # Caja Tda: TransferAccount viene de MySQL (payments_account de la tienda)
                    if tipo_opt == "Caja Tda" and id_store is not None:
                        ta = service.consultar_payments_account_tienda(int(id_store)) or ta

                    # Construye CounterReference y U_PLA_CODTUTATI según tipo de pago
                    referencia = str(datos.get("referencia") or "").strip()
                    fecha_datos = str(datos.get("fecha") or "").strip()
                    eid_tienda = ""
                    if id_store is not None:
                        eid_tienda = (service.consultar_eid_tienda(int(id_store)) or "").strip()

                    uid_orders_final = str(datos.get("uid_orders") or orden).strip()
                    codtutati = str(datos.get("eid_orders") or "").strip()

                    if nombre_opt == "RMA":
                        rma = service.consultar_datos_rma_pg(uid_orders_final)
                        uid_rmas = str(rma.get("uid_rmas") or "").strip() if rma else ""
                        codtutati = str(rma.get("id_users") or "").strip() if rma else ""
                        cr_sufijo = uid_rmas
                    elif tipo_opt == "Caja Tda":
                        cr_sufijo = fecha_datos
                    else:
                        cr_sufijo = referencia

                    counter_reference = f"{eid_tienda}-{cr_sufijo}" if eid_tienda else cr_sufijo

                    # Consulta DocEntry y U_BOT_DOCENTRY desde SAP HANA
                    schema = SL_COMPANIES[sociedad_key]
                    factura = service.consultar_datos_factura_sap(orden, schema)
                    inv_doc_entry = int(factura["DocEntry"]) if factura and factura.get("DocEntry") is not None else ""
                    bot_docentry = int(factura["U_BOT_DOCENTRY"]) if factura and factura.get("U_BOT_DOCENTRY") is not None else ""

                    payload: dict[str, Any] = {
                        "TransferSum": monto,
                        "U_PLA_ORDENWEB": uid_orders_final,
                        "CardCode": "C99999999999",
                        "DocDate": fecha_datos,
                        "TransferAccount": ta,
                        "U_PLA_CODTUTATI": codtutati,
                        "U_SYP_COD0325": "3D0835",
                        "U_SYP_COD0318": "3D0101",
                        "CounterReference": counter_reference,
                        "TransferReference": uid_orders_final,
                        "U_SYP_MPPG": mpg,
                        "U_SYP_TPOOPERI": "01",
                        "ProjectCode": "MONEDERO" if nombre_opt == "RMA" else "",
                        "PaymentInvoices": [
                            {
                                "SumApplied": monto,
                                "U_BOT_NUMATCARD": codtutati,
                                "AppliedFC": monto,
                                "DocEntry": inv_doc_entry,
                                "DocLine": 0,
                                "InvoiceType": "it_Invoice",
                            }
                        ],
                        "DocType": "rCustomer",
                        "U_BOT_ROBOT": "S",
                        "U_BOT_DOCENTRY": bot_docentry,
                        "U_BOT_TIPO": bot_cfg["U_BOT_TIPO"],
                        "U_BOT_CODCIA": bot_cfg["U_BOT_CODCIA"],
                        "U_BOT_ACCION": 5,
                        "U_SGE_INTERCOMPANY": "N",
                        "U_SGE_ECOMMERCE": "N",
                    }
                    if tipo_opt != "Cuentas por pagar - saldo":
                        cashflow_id = 59 if tipo_opt == "Caja Tda" else 60
                        payload["CashFlowAssignments"] = [
                            {"CashFlowLineItemID": cashflow_id, "PaymentMeans": "pmtBankTransfer"}
                        ]
                    result_json = _json.dumps(payload, indent=2, ensure_ascii=False)
                except Exception as exc:
                    error = str(exc)

        return render_template(
            "enviar_pago_sap.html",
            current_page="enviar-pago-sap",
            sociedad_key=sociedad_key,
            sl_companies=SL_COMPANIES,
            envio_options=_ENVIO_PAGO_OPTIONS,
            form_data=form_data,
            result_json=result_json,
            error=error,
            success=success,
            pagos_candidatos=None,
        )

    @app.get("/validacion-nubefact")
    def validacion_nubefact() -> str:
        rows: list[dict] = []
        cols: list[str] = []
        error: str | None = None
        try:
            rows, cols = service.consultar_nubefact()
        except Exception as exc:
            error = str(exc)
        return render_template(
            "validacion_nubefact.html",
            current_page="validacion-nubefact",
            rows=rows,
            cols=cols,
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


_TIPO_PAGO_MAP: list[tuple[str | None, str | None, str, str, int | None]] = [
    # (TransferAccount, U_SYP_MPPG, nombre, tipo, id_orders_payments_types)
    # None en ta/mpg = campo vacío en la tabla → no se valida ese campo
    # None en id = sin equivalencia en orders_payments_types
    ("10310002", "005", "Visa (VisaNet)",                               "Tarjetas Visanet",              1),
    ("10310002", "006", "Visa Crédito",                                 "Tarjetas Visanet",             23),
    ("10310002", "005", "Visa Debito",                                  "Tarjetas Visanet",             24),
    ("10310001", None,  "Mastercard (MC Peru)",                         "Tarjetas MCM",                  2),
    ("10310001", "005", "Mastercard Crédito",                           "Tarjetas MCM",                 25),
    ("10310001", "006", "Mastercard Débito",                            "Tarjetas MCM",                 26),
    ("10310003", "006", "Amex (Expressnet)",                            "Tarjetas Expressnet",           3),
    ("10310020", "003", "Tarjeta de crédito o débito, Yape, Plin - Izipay", "Pago Izipay",             34),
    ("10310020", None,  "Tarjeta de crédito o débito - Izipay",         "Pago Izipay",                  33),
    ("10300003", "001", "Dep. bco. BCP",                                "Deposito BCP",                 12),
    ("10300006", None,  "Dep. bco. Scotiabank",                         "Deposito Scotiabank",          13),
    ("10300007", None,  "Dep. bco. Interbank",                          "Deposito Interbank",           14),
    ("10300008", None,  "Dep. bco. BBVA",                               "Deposito BBVA",                15),
    (None,       "008", "Soles",                                       "Caja Tda",                   16),
    (None,       "008", "Dólares",                                     "Caja Tda",                   17),    
    ("46111004", "001", "Monedero",                                     "Cuentas por pagar - saldo",    18),
    ("46111004", "004", "RMA",                                          "Cuentas por pagar - saldo",    19),
    ("64111001", None,  "Transferencia Gratuita",                       "IGV - Retiro de bienes",       21),
    ("46111005", None,  "Puntos",                                       "Puntos y obsequios otorgados", 22),
    ("10310004", "006", "Diners",                                       "Tarjetas Diners",              28),
    ("10310017", "006", "Tarjeta de crédito o débito - Mercado Pago",   "Tarjetas Mercadopago",          9),
    ("10310017", "001", "PagoEfectivo - Mercado Pago",                  "Tarjetas Mercadopago",         10),
    ("10310006", "006", "Estilos",                                      "Tarjetas Estilos",             30),
    ("10300004", None,  "Dep. bco. BCP - Activa",                       "Efectivo Activa",              31),
    ("10310005", "006", "Tarjetas Openpay",                             "Tarjetas Openpay",             58),
]


_ENVIO_PAGO_OPTIONS: list[dict] = [
    {"nombre": nombre, "tipo": tipo, "ta": ta or "", "mpg": mpg or "", "id_opt": id_opt}
    for ta, mpg, nombre, tipo, id_opt in _TIPO_PAGO_MAP
]


def _determinar_tipo_pago(transfer_account: Any, u_syp_mppg: Any) -> tuple[str, str]:
    ta = str(transfer_account or "").strip()
    mpg = str(u_syp_mppg or "").strip()
    for rule_ta, rule_mpg, nombre, tipo, _id in _TIPO_PAGO_MAP:
        if rule_ta is not None and ta != rule_ta:
            continue
        if rule_mpg is not None and mpg != rule_mpg:
            continue
        return nombre, tipo
    return ta or "Desconocido", ""


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
