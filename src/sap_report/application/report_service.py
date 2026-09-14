import calendar
import logging
import re
import time
from datetime import date, datetime, time as datetime_time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from sap_report.application.email_templates import construir_correo
from sap_report.domain import cuid_a_fecha, fecha_a_cuid
from sap_report.infrastructure.db import (
    TICKET_NO_APLICA,
    LocalStore,
    MySQLRepository,
    PostgresRepository,
    SapHanaRepository,
    SapServiceLayerRepository,
)
from sap_report.infrastructure.email import SmtpMailer
from sap_report.infrastructure.export import (
    exportar_comparacion,
    exportar_excel,
    exportar_pestana_excel,
)


LOGGER = logging.getLogger(__name__)

# Crear LPN: la funcion admite hasta 200000, pero por encima de ~2000 el
# servidor corta la sesion. 2000 es el tamano que pasa de forma estable.
LPN_LOTE_MAX = 2000
LPN_TIPO = 3
# El servidor corta la sesion seguido; la misma llamada suele pasar al segundo
# o tercer intento.
LPN_INTENTOS = 10
LPN_ESPERA_REINTENTO = 6


# Alta de Mattermost: el nombre viaja como argumento del script, asi que se
# limita a letras, espacios y los signos que trae un nombre real.
MM_NOMBRE_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{1,79}$")
MM_DOCUMENTO_RE = re.compile(r"^[A-Za-z0-9]{6,15}$")


def _es_url_de_numeraciones(url: str) -> bool:
    """Los CSV viven en el bucket de la cuenta, bajo numerations-suppliers/.
    Cualquier otra direccion se rechaza."""
    return bool(
        re.match(
            r"^https://[\w.-]+\.s3\.[\w-]+\.amazonaws\.com/numerations-suppliers/",
            (url or "").strip(),
        )
    )


def _resumir_lpn(respuesta: Any) -> dict[str, Any]:
    """La funcion devuelve [[{file_href}], [{LPN_QR, LPN_RFID}, ...]] con un
    objeto por LPN: miles de entradas. Para el log y la pantalla basta el
    enlace del CSV y el rango."""
    resumen: dict[str, Any] = {}
    try:
        resumen["file_href"] = respuesta[0][0]["file_href"]
        lpns = respuesta[1] or []
        resumen["lpns"] = len(lpns)
        if lpns:
            resumen["desde"] = lpns[0].get("LPN_QR")
            resumen["hasta"] = lpns[-1].get("LPN_QR")
            resumen["rfid_desde"] = lpns[0].get("LPN_RFID")
            resumen["rfid_hasta"] = lpns[-1].get("LPN_RFID")
    except Exception:
        # Respuesta con otra forma (por ejemplo el success:false de la funcion).
        resumen["respuesta"] = respuesta
    return resumen


def _particionar(total: int, maximo: int) -> list[int]:
    """14000 con maximo 10000 -> [10000, 4000]."""
    lotes = [maximo] * (total // maximo)
    resto = total % maximo
    if resto:
        lotes.append(resto)
    return lotes


class ReportService:
    def __init__(
        self,
        sap_repository: SapHanaRepository,
        postgres_repository: PostgresRepository,
        mysql_repository: MySQLRepository,
        sl_repository: SapServiceLayerRepository,
        mailer: SmtpMailer,
        sap_output_path: Path,
        postgres_output_path: Path,
        comparacion_output_path: Path,
        postgres_chile_repository: PostgresRepository | None = None,
        local_store: LocalStore | None = None,
        mattermost_repository: Any | None = None,
    ) -> None:
        # Dependencias de acceso a datos y rutas de salida.
        self._sap_repository = sap_repository
        self._postgres_repository = postgres_repository
        self._postgres_chile_repository = postgres_chile_repository
        self._mysql_repository = mysql_repository
        self._sl_repository = sl_repository
        self._mailer = mailer
        self._local_store = local_store
        self._mattermost_repository = mattermost_repository
        self._sap_output_path = sap_output_path
        self._postgres_output_path = postgres_output_path
        self._comparacion_output_path = comparacion_output_path

    def ejecutar_reporte(
        self,
        fecha_inicio_date: date,
        fecha_fin_date: date,
        status_cb=None,
    ) -> dict[str, Any]:
        # Validacion basica del rango (inicio no puede ser mayor al fin).
        if fecha_inicio_date > fecha_fin_date:
            raise ValueError("La fecha inicio no puede ser mayor a la fecha fin.")

        if status_cb:
            status_cb(f"Procesando rango: {fecha_inicio_date} -> {fecha_fin_date}")

        # Acumuladores y errores por fuente (SAP y PostgreSQL).
        sap_rows: list[tuple[Any, ...]] = []
        sap_cols: list[str] | None = None
        sap_nc_rows: list[tuple[Any, ...]] = []
        sap_nc_cols: list[str] | None = None
        pg_rows: list[tuple[Any, ...]] = []
        pg_cols: list[str] | None = None
        pg_nc_rows: list[tuple[Any, ...]] = []
        pg_nc_cols: list[str] | None = None
        sap_error: str | None = None
        pg_error: str | None = None

        try:
            # PostgreSQL primero (es lo mas fragil; usa sesion persistente
            # para reusar 1 sola conexion mientras dure el bloque).
            with self._postgres_repository.sesion():
                pg_rows, pg_cols = self._ejecutar_postgres_con_fallback(
                    fecha_inicio_date,
                    fecha_fin_date,
                    "POSTGRES",
                    status_cb,
                    query_method_name="ejecutar_consulta_sql_rango",
                )
                exportar_excel(pg_rows, pg_cols, self._postgres_output_path)
                pg_nc_rows, pg_nc_cols = self._ejecutar_postgres_con_fallback(
                    fecha_inicio_date,
                    fecha_fin_date,
                    "POSTGRES_NC",
                    status_cb,
                    query_method_name="ejecutar_consulta_nc_sql_rango",
                )
            pg_nc_acum_rows, pg_nc_acum_cols = _acumular_tutati_nc(pg_nc_rows, pg_nc_cols)
            exportar_pestana_excel(
                pg_nc_acum_rows,
                pg_nc_acum_cols,
                self._postgres_output_path,
                sheet_name="Acumulado_NC",
            )
        except Exception as exc:
            pg_error = str(exc)
            LOGGER.exception("PostgreSQL fallo durante la ejecucion")

        try:
            # SAP soporta el rango completo en una sola llamada.
            sap_rows, sap_cols = self._ejecutar_rango_completo(
                fecha_inicio_date,
                fecha_fin_date,
                self._sap_repository,
                "SAP",
                status_cb,
            )
            exportar_excel(sap_rows, sap_cols, self._sap_output_path)
            # Notas de credito SAP en una sola llamada y pestaña de acumulado.
            sap_nc_rows, sap_nc_cols = self._ejecutar_rango_completo(
                fecha_inicio_date,
                fecha_fin_date,
                self._sap_repository,
                "SAP_NC",
                status_cb,
                query_method_name="ejecutar_consulta_nc_sql",
            )
            sap_nc_acum_rows, sap_nc_acum_cols = _acumular_sap_nc(sap_nc_rows, sap_nc_cols)
            exportar_pestana_excel(
                sap_nc_acum_rows,
                sap_nc_acum_cols,
                self._sap_output_path,
                sheet_name="Acumulado_NC",
            )
        except Exception as exc:
            sap_error = str(exc)
            LOGGER.exception("SAP fallo durante la ejecucion")

        if sap_error and pg_error:
            # Si ambos fallan, se informa error global.
            raise RuntimeError(
                f"SAP fallo: {sap_error} | PostgreSQL fallo: {pg_error}"
            )

        # Genera comparacion solo si ambas fuentes se exportaron sin error.
        comparacion_error: str | None = None
        comparacion_nc_error: str | None = None
        comparacion_data: dict[str, Any] | None = None
        comparacion_nc_data: dict[str, Any] | None = None
        if (not sap_error) and (not pg_error) and sap_cols and pg_cols:
            try:
                LOGGER.info("Comparacion: inicio")
                t0 = time.perf_counter()
                comparacion_data = self._generar_comparacion(
                    sap_rows,
                    sap_cols,
                    pg_rows,
                    pg_cols,
                    sheet_name="Comparacion",
                )
                LOGGER.info("Comparacion OK en %.2fs", time.perf_counter() - t0)
            except Exception as exc:
                comparacion_error = str(exc)
                LOGGER.exception("Comparacion fallo durante la ejecucion")
        else:
            comparacion_error = "Comparacion omitida por error previo en SAP o PostgreSQL."

        # Genera comparacion NC en otra pestaña.
        if (not sap_error) and (not pg_error) and sap_nc_cols and pg_nc_cols:
            try:
                LOGGER.info("Comparacion_NC: inicio")
                t0 = time.perf_counter()
                comparacion_nc_data = self._generar_comparacion(
                    sap_nc_rows,
                    sap_nc_cols,
                    pg_nc_rows,
                    pg_nc_cols,
                    sheet_name="Comparacion_NC",
                )
                LOGGER.info("Comparacion_NC OK en %.2fs", time.perf_counter() - t0)
            except Exception as exc:
                comparacion_nc_error = str(exc)
                LOGGER.exception("Comparacion NC fallo durante la ejecucion")
        else:
            comparacion_nc_error = "Comparacion NC omitida por error previo en SAP o PostgreSQL."

        LOGGER.info("Reporte completo. Retornando a UI.")

        # Retorna resumen para mostrar en UI.
        return {
            "sap": len(sap_rows),
            "postgres": len(pg_rows),
            "sap_error": sap_error,
            "postgres_error": pg_error,
            "comparacion_error": comparacion_error,
            "comparacion_nc_error": comparacion_nc_error,
            "comparacion": comparacion_data,
            "comparacion_nc": comparacion_nc_data,
        }

    def probar_conexiones(self) -> dict[str, str]:
        # Test rapido de conectividad sin correr consultas pesadas.
        sap = "OK"
        pg = "OK"
        mysql = "OK"
        try:
            self._sap_repository.probar_conexion()
        except Exception as exc:
            sap = str(exc)
        try:
            self._postgres_repository.probar_conexion()
        except Exception as exc:
            pg = str(exc)
        try:
            self._mysql_repository.probar_conexion()
        except Exception as exc:
            mysql = str(exc)
        return {"sap": sap, "postgres": pg, "mysql": mysql}

    def ejecutar_migrar_oc_recientes(self, status_cb=None) -> list[date]:
        ayer = date.today() - timedelta(days=1)
        anteayer = date.today() - timedelta(days=2)
        if status_cb:
            status_cb(f"Ejecutando patch ETL: {ayer}")
        self._postgres_repository.ejecutar_migrar_oc(ayer)
        time.sleep(1)
        if status_cb:
            status_cb(f"Ejecutando patch ETL: {anteayer}")
        self._postgres_repository.ejecutar_migrar_oc(anteayer)
        return [ayer, anteayer]

    def validar_articulos(self, status_cb=None) -> list[str]:
        hoy = date.today()
        fecha_inicio = _add_months(hoy, -1)
        fecha_fin = _add_months(hoy, 1)
        if status_cb:
            status_cb(f"Validando articulos: {fecha_inicio} -> {fecha_fin}")
        return self._sap_repository.ejecutar_validar_articulos(fecha_inicio, fecha_fin)

    def validar_igv(self, status_cb=None) -> dict[str, Any]:
        # Rango para IGV: todo el mes en curso. Si hoy es del 1 al 5,
        # se incluye tambien el mes anterior (usando > inicio y < fin).
        hoy = date.today()
        inicio_mes = hoy.replace(day=1)
        if hoy.day <= 5:
            fecha_inicio = _add_months(inicio_mes, -1)
        else:
            fecha_inicio = inicio_mes
        fecha_fin = hoy + timedelta(days=1)
        upd_hilos = 0
        if status_cb:
            status_cb(f"Validando IGV en SAP: {fecha_inicio} -> {fecha_fin}")

        sap_rows, sap_cols = self._sap_repository.ejecutar_validar_igv(fecha_inicio, fecha_fin)
        if not sap_cols:
            return {
                "sap_docentries": 0,
                "items_total": 0,
                "items_igv": 0,
                "upd_comercial": 0,
                "upd_pedral": 0,
                "upd_hilos": 0,
                "docentries": [],
            }

        idx_doc = _find_col_index(sap_cols, ["u_bot_docentry"])
        idx_inv = _find_col_index(sap_cols, ["total_inv"])
        idx_ret = _find_col_index(sap_cols, ["total_retail"])

        docentries: list[str] = []
        for row in sap_rows:
            total_inv = row[idx_inv]
            total_ret = row[idx_ret]
            if total_inv is None or total_ret is None:
                continue
            if str(total_inv).strip() == "" or str(total_ret).strip() == "":
                continue
            docentries.append(str(row[idx_doc]))
        docentries_out = list(dict.fromkeys(docentries))
        if status_cb:
            status_cb(f"Validando IGV en MySQL: {len(docentries_out)} DocEntry")

        doc_rows, doc_cols = self._mysql_repository.ejecutar_validar_igv_docs(docentries)
        if not doc_rows:
            return {
                "sap_docentries": len(docentries_out),
                "items_total": 0,
                "items_igv": 0,
                "upd_comercial": 0,
                "upd_pedral": 0,
                "upd_hilos": upd_hilos,
                "docentries": docentries_out,
            }

        idx_doc_id = _find_col_index(doc_cols, ["id_document"])
        document_ids = [str(r[idx_doc_id]) for r in doc_rows if r[idx_doc_id] is not None]

        items_rows, items_cols = self._mysql_repository.ejecutar_validar_igv_items(document_ids)
        if not items_cols:
            return {
                "sap_docentries": len(docentries_out),
                "items_total": 0,
                "items_igv": 0,
                "upd_comercial": 0,
                "upd_pedral": 0,
                "upd_hilos": upd_hilos,
                "docentries": docentries_out,
            }

        idx_material = _find_col_index(items_cols, ["material"])
        items_set: set[str] = set()
        for row in items_rows:
            value = row[idx_material]
            if value is None:
                continue
            items_set.add(str(value))

        items = sorted(items_set)
        items_igv = self._sap_repository.ejecutar_validar_igv_items(items)
        if status_cb:
            status_cb(f"Actualizando IGV en SAP: {len(items_igv)} items")

        upd_comercial = self._sap_repository.ejecutar_actualizar_igv_comercial(items_igv)
        upd_pedral = self._sap_repository.ejecutar_actualizar_igv_pedral(items_igv)

        if docentries_out:
            if status_cb:
                status_cb(f"Actualizando Hilos en SAP: {len(docentries_out)} DocEntry")
            upd_hilos = self._sap_repository.ejecutar_actualizar_igv_hilos(docentries_out)

        return {
            "sap_docentries": len(docentries_out),
            "items_total": len(items),
            "items_igv": len(items_igv),
            "upd_comercial": upd_comercial,
            "upd_pedral": upd_pedral,
            "upd_hilos": upd_hilos,
            "docentries": docentries_out,
        }

    def consultar_prestamo(
        self,
        status_cb=None,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        columnas = [
            "UID_ORDERS",
            "U_BOT_DOCENTRY",
            "Material",
            "Centro",
            "Consignado",
            "B2B",
            "Stock_SAP",
            "Cantidad_MYSQL",
            "Diferencia",
        ]
        fecha_desde = date.today() - timedelta(days=3)
        memoria: list[tuple[str, str, str, str, str, Any, Any, Any]] = []
        materiales: set[str] = set()
        centros: set[str] = set()

        # Flujo 1: LOGPROCESO (estatus=0) → MySQL docs → MySQL items
        if status_cb:
            status_cb(f"Prestamo flujo-1: buscando DocEntry desde {fecha_desde}...")
        docentries = self._sap_repository.obtener_docentries_prestamo(fecha_desde)
        if docentries:
            if status_cb:
                status_cb(f"Prestamo flujo-1: {len(docentries)} DocEntry en MySQL...")
            doc_rows, doc_cols = self._mysql_repository.ejecutar_validar_igv_docs(docentries)
            if doc_rows:
                idx_doc_id = _find_col_index(doc_cols, ["id_document"])
                idx_docentry = _find_col_index(doc_cols, ["docentry"])
                docentry_por_orden = {
                    str(r[idx_doc_id]): str(r[idx_docentry])
                    for r in doc_rows
                    if r[idx_doc_id] is not None and r[idx_docentry] is not None
                }
                document_ids = [str(r[idx_doc_id]) for r in doc_rows if r[idx_doc_id] is not None]
                if document_ids:
                    items_rows, items_cols = self._mysql_repository.ejecutar_validar_igv_items(document_ids)
                    if items_rows:
                        idx_id_order = _find_col_index_optional(items_cols, ["id_orders"])
                        idx_uid = _find_col_index_optional(items_cols, ["uid_orders"])
                        idx_material = _find_col_index(items_cols, ["material"])
                        idx_centro = _find_col_index(items_cols, ["centro"])
                        idx_matcentro = _find_col_index(items_cols, ["material_centro"])
                        idx_cantidad = _find_col_index(items_cols, ["cantidad"])
                        idx_consignado = _find_col_index_optional(items_cols, ["consignado"])
                        idx_b2b = _find_col_index_optional(items_cols, ["b2b"])
                        for row in items_rows:
                            material = str(row[idx_material]) if row[idx_material] is not None else ""
                            if material == "70000192":
                                continue  # Flete, no se considera en prestamo
                            id_order = str(row[idx_id_order]) if idx_id_order is not None and row[idx_id_order] is not None else ""
                            uid = str(row[idx_uid]) if idx_uid is not None and row[idx_uid] is not None else ""
                            docentry = docentry_por_orden.get(id_order, "")
                            centro = str(row[idx_centro]) if row[idx_centro] is not None else ""
                            matcentro = str(row[idx_matcentro]) if row[idx_matcentro] is not None else material + centro
                            cantidad = row[idx_cantidad]
                            consignado = row[idx_consignado] if idx_consignado is not None else ""
                            b2b = row[idx_b2b] if idx_b2b is not None else ""
                            memoria.append((uid, docentry, material, centro, matcentro, cantidad, consignado, b2b))
                            if material:
                                materiales.add(material)
                            if centro:
                                centros.add(centro)

        # Flujo 2: LOGPROCESO DEV (estatus=A, proceso LIKE DEV%) → @SGE_TRANI
        if status_cb:
            status_cb(f"Prestamo flujo-2: buscando U_BOT_KEY DEV desde {fecha_desde}...")
        keys_dev = self._sap_repository.obtener_keys_prestamo_dev(fecha_desde)
        if keys_dev:
            if status_cb:
                status_cb(f"Prestamo flujo-2: {len(keys_dev)} keys en @SGE_TRANI...")
            trani_rows, trani_cols = self._sap_repository.ejecutar_prestamo_trani(keys_dev)
            if trani_rows:
                idx_mat = _find_col_index(trani_cols, ["u_bot_codarticulo"])
                idx_cant = _find_col_index(trani_cols, ["u_pla_cantidad"])
                idx_alm = _find_col_index(trani_cols, ["u_bot_almacen_devid"])
                for row in trani_rows:
                    material = str(row[idx_mat]) if row[idx_mat] is not None else ""
                    if material == "70000192":
                        continue  # Flete, no se considera en prestamo
                    centro = str(row[idx_alm]) if row[idx_alm] is not None else ""
                    matcentro = material + centro
                    cantidad = row[idx_cant]
                    memoria.append(("", "", material, centro, matcentro, cantidad, "", ""))
                    if material:
                        materiales.add(material)
                    if centro:
                        centros.add(centro)

        if not memoria or not materiales or not centros:
            return [], columnas

        if status_cb:
            status_cb(
                f"Prestamo: consultando SAP ({len(materiales)} materiales, {len(centros)} centros)..."
            )
        sap_rows, sap_cols = self._sap_repository.ejecutar_prestamo_stock(
            sorted(materiales),
            sorted(centros),
        )
        if not sap_rows:
            return [], columnas

        idx_itemwarehouse = _find_col_index(sap_cols, ["itemwarehouse"])
        idx_stock = _find_col_index(sap_cols, ["stock"])
        sap_map: dict[str, float] = {}
        for row in sap_rows:
            key = str(row[idx_itemwarehouse]).strip() if row[idx_itemwarehouse] is not None else ""
            if not key:
                continue
            sap_map[key] = _to_float(row[idx_stock])

        resultados: list[tuple[Any, ...]] = []
        for uid, docentry, material, centro, matcentro, cantidad, consignado, b2b in memoria:
            stock = sap_map.get(matcentro, 0.0)
            cantidad_num = _to_float(cantidad)
            diff = cantidad_num - stock
            if diff <= 0:
                continue
            resultados.append((uid, docentry, material, centro, consignado, b2b, stock, cantidad_num, diff))

        return resultados, columnas

    def revisar_hilos(self) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Consulta de hilos pendientes en SAP.
        return self._sap_repository.ejecutar_revisar_hilos()

    def consultar_por_enviar(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        tipo: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        cuid_inicio = fecha_a_cuid(datetime.combine(fecha_inicio, datetime_time.min))
        cuid_fin = fecha_a_cuid(datetime.combine(fecha_fin, datetime_time(23, 59, 59)))
        return self._mysql_repository.ejecutar_por_enviar(cuid_inicio, cuid_fin, tipo)

    def consultar_venta_doble(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        cuid_inicio = fecha_a_cuid(datetime.combine(fecha_inicio, datetime_time.min))
        cuid_fin = fecha_a_cuid(datetime.combine(fecha_fin, datetime_time(23, 59, 59)))
        return self._mysql_repository.obtener_pendientes_venta_doble(cuid_inicio, cuid_fin)

    def listar_plantillas_correo(self) -> list[dict[str, str]]:
        from sap_report.application.email_templates import EMAIL_TEMPLATES

        return [{"id": t["id"], "nombre": t["nombre"]} for t in EMAIL_TEMPLATES]

    def enviar_correo(self, template_id: str, fecha: date) -> str:
        fecha_str = fecha.strftime("%d/%m/%Y")
        correo = construir_correo(template_id, fecha_str)
        self._mailer.send(
            to=correo["to"],
            subject=correo["asunto"],
            body=correo["cuerpo"],
            cc=correo["cc"],
            html=correo["cuerpo_html"],
        )
        return f"Correo «{correo['asunto']}» enviado correctamente."

    def enviar_venta_doble(self, uid: str, tipo: str) -> int:
        uid = uid.strip()
        tipo = tipo.strip().upper()
        if not uid:
            raise ValueError("UID vacío.")
        if tipo not in ("ORDER", "RMA"):
            raise ValueError(f"Tipo inválido para venta doble: {tipo!r}")
        return self._mysql_repository.ejecutar_sp_create_document_movement([uid], tipo)

    def validar_movimiento(self, id_document: int, tipo: str) -> dict[str, Any]:
        if id_document <= 0:
            raise ValueError("id_document inválido.")
        tipo = tipo.strip()
        providers = {
            "id_Outbound": self._mysql_repository.consultar_items_outbound,
            "id_Inbound": self._mysql_repository.consultar_items_inbound,
        }
        provider = providers.get(tipo)
        if provider is None:
            raise ValueError(f"Tipo no soportado para validar: {tipo!r}")
        rows, _ = provider([id_document])
        return self._comparar_items_contra_stock(id_document, tipo, rows)

    def _comparar_items_contra_stock(
        self,
        id_document: int,
        tipo: str,
        mysql_rows: list[tuple[Any, ...]],
    ) -> dict[str, Any]:
        result = {
            "tipo": tipo,
            "id_document": id_document,
            "items_total": len(mysql_rows),
            "faltantes": [],
        }
        if not mysql_rows:
            return result

        mysql_items: list[dict[str, Any]] = []
        articulos: set[str] = set()
        centros: set[str] = set()
        for row in mysql_rows:
            articulo = str(row[0]).strip() if row[0] is not None else ""
            centro = str(row[1]).strip() if row[1] is not None else ""
            if not articulo or not centro:
                continue
            cantidad = _to_float(row[2])
            mysql_items.append({"articulo": articulo, "centro": centro, "cantidad": cantidad})
            articulos.add(articulo)
            centros.add(centro)

        if not articulos or not centros:
            return result

        sap_rows, sap_cols = self._sap_repository.ejecutar_prestamo_stock(
            sorted(articulos), sorted(centros)
        )
        idx_iw = _find_col_index(sap_cols, ["itemwarehouse"])
        idx_stock = _find_col_index(sap_cols, ["stock"])
        sap_map: dict[str, float] = {}
        for row in sap_rows:
            key = str(row[idx_iw]).strip() if row[idx_iw] is not None else ""
            if not key:
                continue
            sap_map[key] = _to_float(row[idx_stock])

        faltantes: list[dict[str, Any]] = []
        for item in mysql_items:
            key = f"{item['articulo']}{item['centro']}"
            stock = sap_map.get(key, 0.0)
            diff = item["cantidad"] - stock
            if diff > 0:
                faltantes.append(
                    {
                        "articulo": item["articulo"],
                        "centro": item["centro"],
                        "cantidad_mysql": item["cantidad"],
                        "stock_sap": stock,
                        "diferencia": diff,
                    }
                )
        result["faltantes"] = faltantes
        return result

    def enviar_movimiento_por_enviar(self, id_movement: int) -> str:
        if id_movement <= 0:
            raise ValueError("Id_movement invalido.")
        return self._mysql_repository.enviar_movimiento_por_enviar(id_movement)

    def anular_movimiento_por_enviar(self, id_movement: int) -> int:
        # Actualiza el movimiento a estado 9 para reflejar anulacion manual.
        if id_movement <= 0:
            raise ValueError("Id_movement invalido.")
        return self._mysql_repository.anular_movimiento_por_enviar(id_movement)

    def consultar_pago_sap(self, orden: str, company_db: str) -> dict[str, Any]:
        orden = orden.strip()
        if not orden:
            raise ValueError("Orden vacía.")
        data = self._sl_repository.consultar_pago(orden, company_db)
        if not data.get("value"):
            try:
                rows, cols = self._postgres_repository.consultar_datos_pago(orden)
                if rows:
                    uid = dict(zip(cols, rows[0])).get("uid_orders")
                    if uid and uid != orden:
                        data = self._sl_repository.consultar_pago(uid, company_db)
            except Exception:
                pass
        return data

    def anular_pago_sap(self, doc_entry: int, company_db: str) -> None:
        if doc_entry <= 0:
            raise ValueError("DocEntry inválido.")
        self._sl_repository.anular_pago(doc_entry, company_db)

    def crear_pago_sap(self, payload: dict[str, Any], company_db: str) -> dict[str, Any]:
        if not payload:
            raise ValueError("Payload vacío.")
        return self._sl_repository.crear_pago(payload, company_db)

    def consultar_datos_pago_pg(self, orden: str) -> list[dict[str, Any]]:
        orden = orden.strip()
        if not orden:
            raise ValueError("Orden vacía.")
        rows, cols = self._postgres_repository.consultar_datos_pago(orden)
        return [dict(zip(cols, row)) for row in rows]

    def consultar_eid_tienda(self, id_store: int) -> str | None:
        return self._mysql_repository.consultar_eid_tienda(id_store)

    def consultar_payments_account_tienda(self, id_store: int) -> str | None:
        return self._mysql_repository.consultar_payments_account_tienda(id_store)

    def consultar_orden_pago(
        self,
        uids_texto: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Parsea UIDs uno por linea, descarta vacios y duplica.
        lista = [u.strip() for u in (uids_texto or "").splitlines() if u.strip()]
        # Elimina duplicados preservando orden.
        lista = list(dict.fromkeys(lista))
        if not lista:
            raise ValueError("Ingresa al menos un UID.")
        return self._postgres_repository.consultar_orden_pago(lista)

    def consultar_datos_rma_pg(self, orden: str) -> dict[str, Any] | None:
        orden = orden.strip()
        if not orden:
            raise ValueError("Orden vacía.")
        rows, cols = self._postgres_repository.consultar_datos_rma(orden)
        if not rows:
            return None
        return dict(zip(cols, rows[0]))

    def consultar_datos_factura_sap(self, orden: str, schema: str) -> dict[str, Any] | None:
        orden = orden.strip()
        if not orden:
            raise ValueError("Orden vacía.")
        rows, cols = self._sap_repository.ejecutar_datos_factura(orden, schema)
        if not rows:
            return None
        return dict(zip(cols, rows[0]))

    def consultar_nubefact(self) -> tuple[list[dict[str, Any]], list[str]]:
        today = date.today()
        fechas = [today - timedelta(days=i) for i in range(1, 8)]
        # {fecha_str: {estado: cantidad}}
        pivot: dict[str, dict[str, Any]] = {}
        all_estados: list[str] = []
        for fecha in fechas:
            fecha_str = fecha.strftime("%Y-%m-%d")
            try:
                rows, _ = self._sap_repository.ejecutar_visor_nubefact(fecha)
                pivot[fecha_str] = {}
                for row in rows:
                    # col 0 = estado_documento, col 1 = cantidad
                    estado = re.sub(r'^\d+\.\s*', '', str(row[0])) if row[0] is not None else "—"
                    cantidad = row[1] if len(row) > 1 else None
                    pivot[fecha_str][estado] = cantidad
                    if estado not in all_estados:
                        all_estados.append(estado)
            except Exception as exc:
                LOGGER.warning("Nubefact fallo para %s: %s", fecha, exc)
                pivot[fecha_str] = {}
        cols = ["Fecha"] + all_estados
        result_rows: list[dict[str, Any]] = []
        for fecha in [f.strftime("%Y-%m-%d") for f in fechas]:
            row_dict: dict[str, Any] = {"Fecha": fecha}
            for estado in all_estados:
                row_dict[estado] = pivot.get(fecha, {}).get(estado, "")
            result_rows.append(row_dict)
        return result_rows, cols

    def consultar_tickets(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows, cols = self._postgres_repository.consultar_tickets()
        result = self._construir_filas_tickets(rows, cols, "pe")

        # Chile: misma consulta contra su Postgres; se anexa al resultado.
        if self._postgres_chile_repository is not None:
            try:
                rows_cl, cols_cl = self._postgres_chile_repository.consultar_tickets()
                result += self._construir_filas_tickets(rows_cl, cols_cl or cols, "cl")
            except Exception as exc:
                LOGGER.warning("Consulta de tickets Chile fallo: %s", exc)

        # Orden global por fecha descendente (el string YYYY-MM-DD... ordena bien).
        result.sort(key=lambda f: f.get("fecha", ""), reverse=True)
        self._aplicar_marcas_tickets(result)
        return result, cols

    def _aplicar_marcas_tickets(self, filas: list[dict[str, Any]]) -> None:
        """Agrega a cada fila la marca guardada en la base local. Sin marca
        previa el ticket arranca en negro (no aplica): entra al seguimiento
        solo cuando alguien lo marca a mano."""
        marcas: dict[str, dict[str, Any]] = {}
        if self._local_store is not None:
            uids = [str(f.get("uid_tickets", "")).strip() for f in filas]
            try:
                marcas = self._local_store.marcas_tickets([u for u in uids if u])
            except Exception as exc:
                # La marca es un extra: si la base local falla, la tabla igual
                # se muestra.
                LOGGER.warning("No se pudieron leer las marcas de tickets: %s", exc)
        for fila in filas:
            marca = marcas.get(str(fila.get("uid_tickets", "")).strip())
            fila["_marca"] = marca["estado"] if marca else TICKET_NO_APLICA
            fila["_marca_usuario"] = marca["usuario"] if marca else ""
            fila["_marca_fecha"] = marca["actualizado"] if marca else ""

    def marcar_ticket(
        self,
        uid_tickets: str,
        estado: str,
        usuario: str | None = None,
    ) -> dict[str, Any]:
        """Guarda el semaforo del ticket en la base local. Persiste indefinidamente:
        la clave es el uid_tickets, no la consulta que lo trajo."""
        if self._local_store is None:
            raise RuntimeError("No hay base local configurada.")
        return self._local_store.guardar_marca_ticket(uid_tickets, estado, usuario)

    def crear_usuario_mattermost(self, nombre: str, documento: str) -> dict[str, Any]:
        """Corre el alta de usuario de Mattermost en el servidor por SSH.

        Es el mismo script que se ejecuta a mano en la terminal; la web solo
        arma la linea y devuelve lo que el script imprime.
        """
        if self._mattermost_repository is None:
            raise RuntimeError(
                "Mattermost no esta configurado. Falta MATTERMOST_SSH_HOST en .env"
            )

        # Un nombre con varios espacios seguidos crea un usuario distinto al
        # que se ve en pantalla: se normaliza antes de validar.
        nombre_limpio = " ".join(nombre.split())
        documento_limpio = documento.strip()
        if not MM_NOMBRE_RE.match(nombre_limpio):
            raise ValueError(
                "El nombre solo admite letras, espacios, punto, guion y apostrofe "
                "(entre 2 y 80 caracteres)."
            )
        if not MM_DOCUMENTO_RE.match(documento_limpio):
            raise ValueError("El documento debe tener entre 6 y 15 letras o numeros.")

        LOGGER.info("Crear usuario Mattermost: %s | %s", nombre_limpio, documento_limpio)
        resultado = self._mattermost_repository.crear_usuario(nombre_limpio, documento_limpio)
        resultado["nombre"] = nombre_limpio
        resultado["documento"] = documento_limpio
        return resultado

    def crear_lpn(
        self,
        pais: str,
        cantidad: int,
        numeracion: str,
        proveedor: str,
        tipo: int = LPN_TIPO,
        intentos: int = LPN_INTENTOS,
    ) -> list[dict[str, Any]]:
        """Crea numeraciones de proveedor en el Postgres del pais indicado.

        La funcion no admite mas de LPN_LOTE_MAX por llamada, asi que la
        cantidad se parte en lotes y se ejecuta uno por uno; se devuelve la
        respuesta de cada lote. Si un lote falla, los anteriores ya quedaron
        creados: por eso el resultado lleva el detalle lote por lote.
        """
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        if not numeracion.strip():
            raise ValueError("Falta la numeracion.")
        if not proveedor.strip():
            raise ValueError("Falta el proveedor.")

        repositorio = self._repositorio_por_pais(pais)
        lotes = _particionar(cantidad, LPN_LOTE_MAX)
        etiqueta = pais.strip().upper()
        LOGGER.info(
            "Crear LPN %s: %s en %s lote(s) %s | numeracion=%s proveedor=%s tipo=%s",
            etiqueta, cantidad, len(lotes), lotes, numeracion.strip(), proveedor.strip(), tipo,
        )

        resultados: list[dict[str, Any]] = []
        creados = 0
        inicio_total = time.perf_counter()
        for indice, lote in enumerate(lotes, start=1):
            item = self._crear_lpn_lote(
                repositorio, etiqueta, indice, len(lotes), lote,
                numeracion.strip(), proveedor.strip(), tipo, intentos,
            )
            resultados.append(item)
            if not item.get("ok"):
                LOGGER.error(
                    "Crear LPN %s: detenido. Creados %s de %s; quedaron %s lote(s) sin ejecutar.",
                    etiqueta, creados, cantidad, len(lotes) - indice,
                )
                # Sin corte seguiriamos creando numeraciones sobre un fallo que
                # no entendemos todavia.
                break
            creados += lote
        else:
            LOGGER.info(
                "Crear LPN %s: terminado. %s de %s en %s lote(s), %.1fs.",
                etiqueta, creados, cantidad, len(lotes), time.perf_counter() - inicio_total,
            )
        return resultados

    def _crear_lpn_lote(
        self,
        repositorio: PostgresRepository,
        etiqueta: str,
        indice: int,
        total_lotes: int,
        lote: int,
        numeracion: str,
        proveedor: str,
        tipo: int,
        intentos: int,
    ) -> dict[str, Any]:
        """Un lote, con reintentos. El servidor corta la sesion a menudo y la
        misma llamada suele pasar al segundo o tercer intento.

        Antes de reintentar se cuenta cuantas reservas hay: si una llamada que
        parecio fallar alcanzo a confirmar, el conteo sube y se para ahi. Sin
        esa comprobacion un reintento reservaria el rango dos veces.
        """
        item: dict[str, Any] = {"lote": indice, "cantidad": lote}
        try:
            reservas_previas = repositorio.contar_reservas_lpn(numeracion, proveedor)
        except Exception as exc:
            # Sin linea base no se puede distinguir "fallo" de "fallo pero creo":
            # se ejecuta una sola vez, sin reintentos.
            LOGGER.warning(
                "Crear LPN %s: no se pudo contar reservas previas (%s). Sin reintentos.",
                etiqueta, exc,
            )
            reservas_previas = None
            intentos = 1

        ultimo_error = ""
        for intento in range(1, intentos + 1):
            LOGGER.info(
                "Crear LPN %s: lote %s/%s (%s) intento %s/%s enviando...",
                etiqueta, indice, total_lotes, lote, intento, intentos,
            )
            inicio = time.perf_counter()
            try:
                respuesta = repositorio.crear_lpn(lote, numeracion, proveedor, tipo)
                item.update(
                    ok=True,
                    respuesta=respuesta,
                    resumen=_resumir_lpn(respuesta),
                    intentos=intento,
                )
                LOGGER.info(
                    "Crear LPN %s: lote %s/%s (%s) OK en el intento %s (%.1fs) -> %s",
                    etiqueta, indice, total_lotes, lote, intento,
                    time.perf_counter() - inicio, item["resumen"],
                )
                return item
            except Exception as exc:
                ultimo_error = str(exc)
                LOGGER.error(
                    "Crear LPN %s: lote %s/%s (%s) intento %s/%s fallo tras %.1fs: %s",
                    etiqueta, indice, total_lotes, lote, intento, intentos,
                    time.perf_counter() - inicio, exc,
                )

            if reservas_previas is not None:
                try:
                    ahora = repositorio.contar_reservas_lpn(numeracion, proveedor)
                except Exception:
                    ahora = reservas_previas
                if ahora > reservas_previas:
                    LOGGER.warning(
                        "Crear LPN %s: la llamada fallo pero la reserva quedo creada. "
                        "No se reintenta.",
                        etiqueta,
                    )
                    item.update(
                        ok=True,
                        confirmado_en_base=True,
                        intentos=intento,
                        resumen={"nota": "creada pese al error de conexion"},
                    )
                    return item

            if intento < intentos:
                time.sleep(LPN_ESPERA_REINTENTO)

        item.update(ok=False, error=ultimo_error, intentos=intentos)
        return item

    def combinar_csv_lpn(self, urls: list[str]) -> tuple[str, dict[str, Any]]:
        """Descarga los CSV que genero cada lote y los junta en uno solo:
        una cabecera arriba y las filas de todos en orden.

        Devuelve (contenido, resumen). Solo acepta URLs del bucket de
        numeraciones: el servidor no descarga cualquier direccion que le
        manden.
        """
        if not urls:
            raise ValueError("No hay archivos que combinar.")

        cabecera: str | None = None
        filas: list[str] = []
        por_archivo: list[int] = []

        for indice, url in enumerate(urls, start=1):
            if not _es_url_de_numeraciones(url):
                raise ValueError(f"URL no permitida: {url}")
            # El nombre del archivo lleva espacios (la descripcion).
            respuesta = requests.get(url.replace(" ", "%20"), timeout=60)
            respuesta.raise_for_status()

            lineas = [l for l in respuesta.text.splitlines() if l.strip()]
            if not lineas:
                continue
            if cabecera is None:
                cabecera = lineas[0]
            datos = lineas[1:]      # se descarta la cabecera de cada archivo
            filas.extend(datos)
            por_archivo.append(len(datos))
            LOGGER.info("Combinar CSV LPN: archivo %s/%s -> %s filas",
                        indice, len(urls), len(datos))

        if cabecera is None:
            raise ValueError("Los archivos vinieron vacios.")

        contenido = "\n".join([cabecera] + filas) + "\n"
        codigos = [f.split(",")[0].strip() for f in filas]
        numeros = sorted(int(c) for c in codigos if c.isdigit())
        resumen: dict[str, Any] = {
            "archivos": len(por_archivo),
            "filas": len(filas),
            "filas_por_archivo": por_archivo,
            "repetidos": len(codigos) - len(set(codigos)),
        }
        if numeros:
            resumen["desde"] = numeros[0]
            resumen["hasta"] = numeros[-1]
            resumen["correlativo"] = (numeros[-1] - numeros[0] + 1) == len(numeros)
        LOGGER.info("Combinar CSV LPN: %s", resumen)
        return contenido, resumen

    def _repositorio_por_pais(self, pais: str) -> PostgresRepository:
        clave = (pais or "").strip().lower()
        if clave in ("pe", "peru", "perú"):
            return self._postgres_repository
        if clave in ("cl", "chile"):
            if self._postgres_chile_repository is None:
                raise ValueError("Postgres de Chile no esta configurado.")
            return self._postgres_chile_repository
        raise ValueError(f"Pais no valido: {pais}")

    def consultar_devoluciones(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows, cols = self._postgres_repository.consultar_devoluciones()
        result: list[dict[str, Any]] = []
        for row in rows:
            fila: dict[str, Any] = {}
            for i, col in enumerate(cols):
                val = row[i] if i < len(row) else None
                fila[col] = "" if val is None else str(val).strip()
            result.append(fila)
        return result, cols

    def consultar_resolucion_rmas(self) -> tuple[list[dict[str, Any]], list[str]]:
        """Tickets de devolucion cruzados con la resolucion de su RMA.
        Si el RMA nunca paso a estado 5, la fila queda sin resolucion."""
        rows, cols = self._postgres_repository.consultar_resolucion_tickets()
        tickets: list[dict[str, Any]] = []
        for row in rows:
            fila: dict[str, Any] = {}
            for i, col in enumerate(cols):
                val = row[i] if i < len(row) else None
                fila[col] = "" if val is None else str(val).strip()
            tickets.append(fila)

        uids = list(dict.fromkeys(t["uid_rmas"] for t in tickets if t.get("uid_rmas")))
        chg_rows, chg_cols = self._postgres_repository.consultar_resolucion_changelogs(uids)

        # Un RMA puede tener varios pasos a estado 5; se toma el mas reciente.
        resoluciones: dict[str, dict[str, str]] = {}
        idx_uid = _find_col_index_optional(chg_cols, ["uid_rmas"])
        idx_fecha = _find_col_index_optional(chg_cols, ["fecha"])
        idx_comment = _find_col_index_optional(chg_cols, ["comment"])
        for row in chg_rows:
            uid = str(row[idx_uid]).strip() if idx_uid is not None and row[idx_uid] else ""
            if not uid:
                continue
            fecha = str(row[idx_fecha]).strip() if idx_fecha is not None and row[idx_fecha] else ""
            comentario = str(row[idx_comment]).strip() if idx_comment is not None and row[idx_comment] else ""
            actual = resoluciones.get(uid)
            if actual is None or _orden_fecha_resolucion(fecha) > _orden_fecha_resolucion(actual["fecha"]):
                resoluciones[uid] = {"fecha": fecha, "comentario": comentario}

        SIN_RESOLUCION = "No tiene resolución"
        salida: list[dict[str, Any]] = []
        for t in tickets:
            resolucion = resoluciones.get(t.get("uid_rmas", ""))
            cliente = _primer_nombre_apellido(
                t.get("first_name", ""),
                t.get("last_name", ""),
            )
            # Con banco la devolucion va a cuenta; sin banco, a la tarjeta.
            a_cuenta = bool(str(t.get("banco", "") or "").strip())
            # Sin fecha de resolucion no hay nada que comunicarle al cliente.
            if resolucion:
                # Cada destino tiene su propio texto. A cuenta la fecha del RMA
                # no sirve: queda FECHA para completarla a mano.
                plantilla = _MENSAJE_CUENTA if a_cuenta else _MENSAJE_TARJETA
                mensaje = plantilla.format(
                    cliente=cliente,
                    orden=t.get("uid_orders", "") or "(sin orden)",
                    fecha="FECHA" if a_cuenta else _fecha_dd_mm_yyyy(resolucion["fecha"]),
                )
            else:
                mensaje = SIN_RESOLUCION
            salida.append(
                {
                    "fecha": t.get("fecha", "") or SIN_RESOLUCION,
                    "uid_tickets": t.get("uid_tickets", "") or SIN_RESOLUCION,
                    "uid_orders": t.get("uid_orders", "") or SIN_RESOLUCION,
                    "uid_rmas": t.get("uid_rmas", "") or SIN_RESOLUCION,
                    "cliente": cliente,
                    "banco": str(t.get("banco", "") or "").strip(),
                    "fecha_resolucion": resolucion["fecha"] if resolucion else SIN_RESOLUCION,
                    "comentario": resolucion["comentario"] if resolucion else SIN_RESOLUCION,
                    "mensaje": mensaje,
                    "_resuelto": resolucion is not None,
                    "_a_cuenta": a_cuenta,
                }
            )
        cols_salida = [
            "fecha",
            "uid_tickets",
            "uid_orders",
            "uid_rmas",
            "cliente",
            "banco",
            "fecha_resolucion",
            "comentario",
            "mensaje",
        ]
        return salida, cols_salida

    @staticmethod
    def _construir_filas_tickets(
        rows: list[tuple[Any, ...]],
        cols: list[str],
        pais: str,
    ) -> list[dict[str, Any]]:
        salida: list[dict[str, Any]] = []
        for row in rows:
            fila: dict[str, Any] = {"_pais": pais}
            for i, col in enumerate(cols):
                val = row[i] if i < len(row) else None
                fila[col] = "" if val is None else str(val).strip()
            salida.append(fila)
        return salida

    def validar_pagos(
        self,
        fecha: date,
        account_name: str,
        status_cb=None,
    ) -> dict[str, Any]:
        # Compara pagos SAP vs TUTATI para una fecha y medio de pago.
        if not account_name.strip():
            raise ValueError("Debe seleccionar un tipo de pago.")

        if status_cb:
            status_cb(f"Validar pagos SAP: {fecha} | {account_name}")
        sap_rows, sap_cols = self._sap_repository.ejecutar_validar_pagos(
            fecha,
            fecha,
            account_name,
        )

        cuid_inicio = fecha_a_cuid(datetime.combine(fecha, datetime_time.min))
        cuid_fin = fecha_a_cuid(datetime.combine(fecha, datetime_time(23, 59, 59)))
        if status_cb:
            status_cb(f"Validar pagos TUTATI: {fecha} | {account_name}")
        tutati_rows, tutati_cols = self._mysql_repository.ejecutar_validar_pagos(
            cuid_inicio,
            cuid_fin,
            account_name,
        )

        comparacion_rows, resumen = _comparar_pagos(
            sap_rows,
            sap_cols,
            tutati_rows,
            tutati_cols,
            threshold=0.01,
        )

        return {
            "fecha": fecha.isoformat(),
            "tipo_pago": account_name,
            "sap_total": len(sap_rows),
            "tutati_total": len(tutati_rows),
            "faltan_en_sap": resumen["faltan_en_sap"],
            "faltan_en_tutati": resumen["faltan_en_tutati"],
            "montos_diferentes": resumen["montos_diferentes"],
            "coinciden": resumen["coinciden"],
            "rows": comparacion_rows,
            "cols": ["Estado", "Orden", "Monto_SAP", "Monto_TUTATI", "Diferencia"],
        }

    def _ejecutar_rango_completo(
        self,
        fecha_inicio_date: date,
        fecha_fin_date: date,
        repository,
        etiqueta: str,
        status_cb=None,
        query_method_name: str = "ejecutar_consulta_sql",
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Una sola llamada con todo el rango.
        msg = f"{etiqueta}: {fecha_inicio_date} -> {fecha_fin_date}"
        LOGGER.info(msg)
        if status_cb:
            status_cb(msg)
        inicio = time.perf_counter()
        rows, cols = getattr(repository, query_method_name)(fecha_inicio_date, fecha_fin_date)
        if cols is None:
            raise RuntimeError(f"La consulta {etiqueta} no devolvio estructura de columnas.")
        rows_list = list(rows)
        LOGGER.info("%s OK: %d filas en %.2fs", etiqueta, len(rows_list), time.perf_counter() - inicio)
        return rows_list, cols

    def _ejecutar_postgres_con_fallback(
        self,
        fecha_inicio_date: date,
        fecha_fin_date: date,
        etiqueta: str,
        status_cb=None,
        query_method_name: str = "ejecutar_consulta_sql_rango",
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Itera dia por dia. Si los reintentos del repo agotan, parte ese dia
        # en 2 mitades de 12h (nunca mas chico que eso). Cada mitad reintenta
        # por su cuenta; si tambien falla, se propaga el error.
        rows_total: list[tuple[Any, ...]] = []
        cols: list[str] | None = None
        metodo = getattr(self._postgres_repository, query_method_name)
        fecha_actual = fecha_inicio_date
        paso = 0

        while fecha_actual <= fecha_fin_date:
            paso += 1
            inicio_dt = datetime.combine(fecha_actual, datetime_time.min)
            fin_dt = inicio_dt + timedelta(days=1)
            msg = f"{etiqueta} dia {paso}: {fecha_actual}"
            LOGGER.info(msg)
            if status_cb:
                status_cb(msg)

            try:
                rows, cols = metodo(inicio_dt, fin_dt)
                rows_total.extend(rows)
            except Exception as exc:
                LOGGER.warning(
                    "%s dia %s fallo todos los reintentos (%s); fallback a 12h",
                    etiqueta, fecha_actual, exc,
                )
                if status_cb:
                    status_cb(f"{etiqueta} dia {paso} fallo, dividiendo a 12h...")
                mitad_dt = inicio_dt + timedelta(hours=12)
                for sub_inicio, sub_fin in ((inicio_dt, mitad_dt), (mitad_dt, fin_dt)):
                    sub_msg = (
                        f"{etiqueta} dia {paso} sub-lote "
                        f"{sub_inicio:%H:%M}-{sub_fin:%H:%M}"
                    )
                    LOGGER.info(sub_msg)
                    if status_cb:
                        status_cb(sub_msg)
                    sub_rows, cols = metodo(sub_inicio, sub_fin)
                    rows_total.extend(sub_rows)

            fecha_actual += timedelta(days=1)

        if cols is None:
            raise RuntimeError(f"La consulta {etiqueta} no devolvio estructura de columnas.")

        return rows_total, cols

    def _generar_comparacion(
        self,
        sap_rows: list[tuple[Any, ...]],
        sap_cols: list[str],
        pg_rows: list[tuple[Any, ...]],
        pg_cols: list[str],
        sheet_name: str,
    ) -> dict[str, Any]:
        # Busca columnas necesarias por nombre (sin sensibilidad a mayusculas).
        idx_sap_ref = _find_col_index(sap_cols, ["referencia"])
        idx_sap_doc = _find_col_index(sap_cols, ["u_bot_docentry"])
        idx_sap_fecha = _find_col_index_optional(sap_cols, ["fecha"])
        idx_pg_id = _find_col_index(pg_cols, ["eid_orders", "eid"])
        idx_pg_uid = _find_col_index(pg_cols, ["uid_orders", "uid_rmas"])
        idx_pg_fecha = _find_col_index_optional(pg_cols, ["fecha"])
        idx_pg_cuid = _find_col_index_optional(pg_cols, ["cuid_documented"])

        sap_items = [
            {
                "id": _norm_id(row[idx_sap_ref]),
                "doc": str(row[idx_sap_doc]) if row[idx_sap_doc] is not None else "",
                "fecha": str(row[idx_sap_fecha]) if idx_sap_fecha is not None and row[idx_sap_fecha] is not None else "",
            }
            for row in sap_rows
            if _norm_id(row[idx_sap_ref]) != ""
        ]
        pg_items: list[dict[str, str]] = []
        for row in pg_rows:
            item_id = _norm_id(row[idx_pg_id])
            if item_id == "":
                continue
            fecha_pg = ""
            if idx_pg_fecha is not None and row[idx_pg_fecha] is not None:
                fecha_pg = str(row[idx_pg_fecha])
            elif idx_pg_cuid is not None:
                fecha_pg = _fecha_desde_cuid(row[idx_pg_cuid])
            pg_items.append(
                {
                    "id": item_id,
                    "uid": str(row[idx_pg_uid]) if row[idx_pg_uid] is not None else "",
                    "fecha": fecha_pg,
                }
            )

        # Compara por identificador y por cantidad de ocurrencias.
        sap_por_id: dict[str, list[dict[str, str]]] = {}
        for item in sap_items:
            sap_por_id.setdefault(item["id"], []).append(item)
        pg_por_id: dict[str, list[dict[str, str]]] = {}
        for item in pg_items:
            pg_por_id.setdefault(item["id"], []).append(item)

        faltan_en_sap: list[dict[str, str]] = []
        faltan_en_tutati: list[dict[str, str]] = []
        for key in sorted(set(sap_por_id.keys()) | set(pg_por_id.keys())):
            sap_list = sap_por_id.get(key, [])
            pg_list = pg_por_id.get(key, [])
            min_len = min(len(sap_list), len(pg_list))
            if len(pg_list) > min_len:
                faltan_en_sap.extend(pg_list[min_len:])
            if len(sap_list) > min_len:
                faltan_en_tutati.extend(sap_list[min_len:])

        faltantes: list[dict[str, str]] = []
        for item in faltan_en_sap:
            faltantes.append(
                {
                    "tipo_faltante": "FALTA_EN_SAP",
                    "sap": "",
                    "tutati": item["uid"],
                    "fecha": item["fecha"],
                }
            )
        for item in faltan_en_tutati:
            faltantes.append(
                {
                    "tipo_faltante": "FALTA_EN_TUTATI",
                    "sap": item["doc"],
                    "tutati": "",
                    "fecha": item["fecha"],
                }
            )

        # Diferencias de monto por identificador: SUMA (SAP) - TOTAL (TUTATI).
        diferencias = _calcular_diferencias_monto(
            sap_rows=sap_rows,
            sap_cols=sap_cols,
            pg_rows=pg_rows,
            pg_cols=pg_cols,
            threshold=0.12,
        )

        resumen = {
            "sap": len(sap_rows),
            "tutati": len(pg_rows),
            "faltan_en_sap": len(faltan_en_sap),
            "faltan_en_tutati": len(faltan_en_tutati),
        }
        extra_title: str | None = None
        extra_rows: list[dict[str, str]] | None = None
        if sheet_name == "Comparacion_NC":
            extra_title = "VALIDACION_NC"
            extra_rows = _calcular_diferencias_validacion_nc(
                sap_rows,
                sap_cols,
                self._sap_repository,
            )
        exportar_comparacion(
            resumen,
            faltantes,
            diferencias,
            self._comparacion_output_path,
            sheet_name=sheet_name,
            extra_title=extra_title,
            extra_rows=extra_rows,
        )
        # Mismos datos que van al Excel, para pintarlos en pantalla.
        return {
            "resumen": resumen,
            "faltantes": faltantes,
            "diferencias": diferencias,
            "validacion_nc": extra_rows or [],
        }


def _find_col_index(cols: list[str], candidates: list[str]) -> int:
    # Busca columna requerida (case-insensitive).
    normalized = {c.strip().lower(): i for i, c in enumerate(cols)}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    raise RuntimeError(f"No se encontro columna requerida. Esperadas: {', '.join(candidates)}")


# Devolucion a la tarjeta: lleva la fecha real de resolucion del RMA.
_MENSAJE_TARJETA = (
    "Buenas tardes, {cliente}:\n"
    "Por medio del presente, le informamos que la devolución de dinero correspondiente "
    "a la orden de compra {orden} fue realizada el día {fecha}, mediante el mismo medio "
    "de pago utilizado al momento de efectuar la compra.\n"
    "Es importante mencionar que el tiempo para que el monto se vea reflejado en su "
    "cuenta dependerá de los plazos de procesamiento y liberación establecidos por el "
    "banco emisor de la tarjeta.\n"
    "Saludos cordiales,\n"
    "Equipo Postventa."
)

# Devolucion a cuenta bancaria: la fecha queda como FECHA para completarla.
_MENSAJE_CUENTA = (
    "Buenas tardes, {cliente}:\n"
    "Por medio del presente, le informamos que la devolución de dinero correspondiente "
    "a la orden de compra {orden} fue gestionada a su cuenta bancaria el día {fecha}.\n"
    "Le recomendamos revisar los movimientos de su cuenta bancaria para verificar el "
    "abono correspondiente a la devolución.\n"
    "Saludos cordiales,\n"
    "Equipo Postventa"
)


def _fecha_dd_mm_yyyy(fecha: str) -> str:
    # El changelog trae 'YYYY-MM-DD HH:MI:SS AM'; el mensaje al cliente lleva
    # solo 31/07/2026.
    texto = str(fecha or "").strip()
    try:
        return datetime.strptime(texto, "%Y-%m-%d %I:%M:%S %p").strftime("%d/%m/%Y")
    except ValueError:
        pass
    try:
        return datetime.strptime(texto[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return texto


def _primer_nombre_apellido(first_name: str, last_name: str) -> str:
    # Solo el primer nombre y el primer apellido: los clientes suelen tener
    # nombres compuestos y la columna se vuelve ilegible.
    partes = [
        valor.split()[0]
        for valor in (str(first_name or ""), str(last_name or ""))
        if valor.split()
    ]
    return " ".join(partes) or "—"


def _orden_fecha_resolucion(fecha: str) -> tuple[int, str]:
    # El changelog trae 'YYYY-MM-DD HH:MI:SS AM'. Se parsea para comparar bien
    # (el orden alfabetico se equivoca con AM/PM); si no se puede, se cae al
    # texto tal cual.
    try:
        return (1, datetime.strptime(fecha, "%Y-%m-%d %I:%M:%S %p").isoformat())
    except (ValueError, TypeError):
        return (0, fecha or "")


def _norm_id(value: Any) -> str:
    # Normaliza identificadores a texto en mayusculas.
    if value is None:
        return ""
    return str(value).strip().upper()


def _to_float(value: Any) -> float:
    # Convierte distintos formatos numericos a float.
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    raw = str(value).strip().replace(" ", "")
    if raw == "":
        return 0.0
    if "," in raw and "." in raw:
        raw = raw.replace(",", "")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def _calcular_diferencias_monto(
    sap_rows: list[tuple[Any, ...]],
    sap_cols: list[str],
    pg_rows: list[tuple[Any, ...]],
    pg_cols: list[str],
    threshold: float,
) -> list[dict[str, str | float]]:
    # Indices de columnas requeridas para calcular diferencias.
    idx_sap_ref = _find_col_index(sap_cols, ["referencia"])
    idx_sap_doc = _find_col_index(sap_cols, ["u_bot_docentry"])
    idx_sap_suma = _find_col_index(sap_cols, ["suma"])
    idx_sap_fecha = _find_col_index_optional(sap_cols, ["fecha"])

    idx_pg_id = _find_col_index(pg_cols, ["eid_orders", "eid"])
    idx_pg_uid = _find_col_index(pg_cols, ["uid_orders", "uid_rmas"])
    idx_pg_total = _find_col_index(pg_cols, ["total"])

    # Agrupa SAP por referencia.
    sap_map: dict[str, list[dict[str, Any]]] = {}
    for row in sap_rows:
        key = _norm_id(row[idx_sap_ref])
        if key == "":
            continue
        sap_map.setdefault(key, []).append(
            {
                "u_bot_docentry": str(row[idx_sap_doc]) if row[idx_sap_doc] is not None else "",
                "fecha": str(row[idx_sap_fecha]) if idx_sap_fecha is not None and row[idx_sap_fecha] is not None else "",
                "referencia": key,
                "suma": _to_float(row[idx_sap_suma]),
            }
        )

    # Agrupa TUTATI por EID.
    pg_map: dict[str, list[dict[str, Any]]] = {}
    for row in pg_rows:
        key = _norm_id(row[idx_pg_id])
        if key == "":
            continue
        pg_map.setdefault(key, []).append(
            {
                "uid_orders": str(row[idx_pg_uid]) if row[idx_pg_uid] is not None else "",
                "eid_orders": key,
                "total": _to_float(row[idx_pg_total]),
            }
        )

    # Calcula diferencias solo si supera el umbral.
    diferencias: list[dict[str, str | float]] = []
    for key in sorted(set(sap_map.keys()) & set(pg_map.keys())):
        sap_list = sap_map[key]
        pg_list = pg_map[key]
        for sap_item, pg_item in zip(sap_list, pg_list):
            diferencia = sap_item["suma"] - pg_item["total"]
            if abs(diferencia) > threshold:
                diferencias.append(
                    {
                        "u_bot_docentry": sap_item["u_bot_docentry"],
                        "uid_orders": pg_item["uid_orders"],
                        "fecha": sap_item["fecha"],
                        "suma_sap": round(sap_item["suma"], 4),
                        "total_tutati": round(pg_item["total"], 4),
                        "diferencia": round(diferencia, 4),
                    }
                )

    return diferencias


def _acumular_sap_nc(
    rows: list[tuple[Any, ...]],
    cols: list[str],
) -> tuple[list[tuple[Any, ...]], list[str]]:
    idx_ref = _find_col_index(cols, ["referencia"])
    idx_linetotal = _find_col_index(cols, ["linetotal"])
    idx_igv = _find_col_index(cols, ["igv"])
    idx_suma = _find_col_index(cols, ["suma"])

    # Suma acumulada por referencia.
    acumulado: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _norm_id(row[idx_ref])
        if key == "":
            continue
        if key not in acumulado:
            acumulado[key] = {
                "referencia": key,
                "linetotal_acumulado": 0.0,
                "igv_acumulado": 0.0,
                "suma_acumulado": 0.0,
            }
        acumulado[key]["linetotal_acumulado"] += _to_float(row[idx_linetotal])
        acumulado[key]["igv_acumulado"] += _to_float(row[idx_igv])
        acumulado[key]["suma_acumulado"] += _to_float(row[idx_suma])

    data = [
        (
            item["referencia"],
            round(item["linetotal_acumulado"], 4),
            round(item["igv_acumulado"], 4),
            round(item["suma_acumulado"], 4),
        )
        for item in sorted(acumulado.values(), key=lambda x: x["referencia"])
    ]
    return data, [
        "referencia",
        "linetotal_acumulado",
        "igv_acumulado",
        "suma_acumulado",
    ]


def _acumular_tutati_nc(
    rows: list[tuple[Any, ...]],
    cols: list[str],
) -> tuple[list[tuple[Any, ...]], list[str]]:
    idx_eid = _find_col_index(cols, ["eid", "eid_orders"])
    idx_total = _find_col_index(cols, ["total"])
    idx_uid = _find_col_index(cols, ["uid_rmas", "uid_orders"])

    # Suma acumulada por EID.
    acumulado: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _norm_id(row[idx_eid])
        if key == "":
            continue
        if key not in acumulado:
            acumulado[key] = {
                "eid": key,
                "total_acumulado": 0.0,
                "uid_referencia": str(row[idx_uid]) if row[idx_uid] is not None else "",
            }
        acumulado[key]["total_acumulado"] += _to_float(row[idx_total])

    data = [
        (
            item["eid"],
            item["uid_referencia"],
            round(item["total_acumulado"], 4),
        )
        for item in sorted(acumulado.values(), key=lambda x: x["eid"])
    ]
    return data, ["eid", "uid_rmas_referencia", "total_acumulado"]


def _calcular_diferencias_validacion_nc(
    sap_rows: list[tuple[Any, ...]],
    sap_cols: list[str],
    sap_repository: SapHanaRepository,
) -> list[dict[str, str]]:
    # Valida que los U_BOT_DOCENTRY de NC existan en ORIN.
    idx_doc = _find_col_index(sap_cols, ["u_bot_docentry"])
    idx_fecha = _find_col_index_optional(sap_cols, ["fecha"])

    sap_items: list[dict[str, str]] = []
    docentries: list[str] = []
    for row in sap_rows:
        docentry = str(row[idx_doc]).strip() if row[idx_doc] is not None else ""
        if not docentry:
            continue
        fecha = str(row[idx_fecha]).strip() if idx_fecha is not None and row[idx_fecha] is not None else ""
        sap_items.append({"u_bot_docentry": docentry, "fecha": fecha})
        docentries.append(docentry)

    if not docentries:
        return []

    docentries_unicos = list(dict.fromkeys(docentries))
    LOGGER.info("validacion_nc: ejecutando con %d docentries", len(docentries_unicos))
    t0 = time.perf_counter()
    validacion_rows, validacion_cols = sap_repository.ejecutar_validacion_nc(docentries_unicos)
    LOGGER.info("validacion_nc OK: %d filas en %.2fs", len(validacion_rows), time.perf_counter() - t0)
    idx_valid_doc = _find_col_index_optional(validacion_cols, ["u_bot_docentry"])
    if idx_valid_doc is None:
        idx_valid_doc = _find_col_index_optional(validacion_cols, ["docentry"])
    encontrados = {
        str(row[idx_valid_doc]).strip()
        for row in validacion_rows
        if idx_valid_doc is not None and row[idx_valid_doc] is not None and str(row[idx_valid_doc]).strip()
    }

    faltantes_candidatos: list[str] = []
    vistos_faltantes: set[str] = set()
    for item in sap_items:
        docentry = item["u_bot_docentry"]
        if docentry in encontrados or docentry in vistos_faltantes:
            continue
        faltantes_candidatos.append(docentry)
        vistos_faltantes.add(docentry)

    articulos_por_doc: dict[str, set[str]] = {}
    if faltantes_candidatos:
        LOGGER.info("validacion_nc_articulos: ejecutando con %d docentries", len(faltantes_candidatos))
        t0 = time.perf_counter()
        articulos_rows, articulos_cols = sap_repository.ejecutar_validacion_nc_articulos(
            faltantes_candidatos
        )
        LOGGER.info("validacion_nc_articulos OK: %d filas en %.2fs", len(articulos_rows), time.perf_counter() - t0)
        idx_art_doc = _find_col_index(articulos_cols, ["docentry"])
        idx_art_cod = _find_col_index(articulos_cols, ["u_bot_codarticulo"])
        for row in articulos_rows:
            docentry = str(row[idx_art_doc]).strip() if row[idx_art_doc] is not None else ""
            articulo = str(row[idx_art_cod]).strip() if row[idx_art_cod] is not None else ""
            if not docentry or not articulo:
                continue
            articulos_por_doc.setdefault(docentry, set()).add(articulo)

    diferencias: list[dict[str, str]] = []
    vistos: set[str] = set()
    for item in sap_items:
        docentry = item["u_bot_docentry"]
        if docentry in encontrados or docentry in vistos:
            continue
        articulos_doc = articulos_por_doc.get(docentry, set())
        if articulos_doc == {"70000192"}:
            vistos.add(docentry)
            continue
        diferencias.append(
            {
                "u_bot_docentry": docentry,
                "fecha": item["fecha"],
                "diferencia": "FALTA_EN_ORIN",
            }
        )
        vistos.add(docentry)
    return diferencias


def _comparar_pagos(
    sap_rows: list[tuple[Any, ...]],
    sap_cols: list[str],
    tutati_rows: list[tuple[Any, ...]],
    tutati_cols: list[str],
    threshold: float,
) -> tuple[list[tuple[str, str, float, float, float]], dict[str, int]]:
    # Compara ordenes y montos entre SAP y TUTATI.
    sap_map = _extraer_pagos_por_orden(
        sap_rows,
        sap_cols,
        order_candidates=["u_pla_ordenweb"],
        amount_candidates=["doctotal"],
    )
    tutati_map = _extraer_pagos_por_orden(
        tutati_rows,
        tutati_cols,
        order_candidates=["uid_orders"],
        amount_candidates=["amount"],
    )

    comparacion_rows: list[tuple[str, str, float, float, float]] = []
    resumen = {
        "faltan_en_sap": 0,
        "faltan_en_tutati": 0,
        "montos_diferentes": 0,
        "coinciden": 0,
    }

    for orden in sorted(set(sap_map.keys()) | set(tutati_map.keys())):
        monto_sap = sap_map.get(orden)
        monto_tutati = tutati_map.get(orden)
        if monto_sap is None:
            resumen["faltan_en_sap"] += 1
            comparacion_rows.append(
                (
                    "FALTA_EN_SAP",
                    orden,
                    0.0,
                    round(monto_tutati or 0.0, 2),
                    round(-(monto_tutati or 0.0), 2),
                )
            )
            continue
        if monto_tutati is None:
            resumen["faltan_en_tutati"] += 1
            comparacion_rows.append(
                ("FALTA_EN_TUTATI", orden, round(monto_sap, 2), 0.0, round(monto_sap, 2))
            )
            continue

        diferencia = round(monto_sap - monto_tutati, 2)
        if abs(diferencia) > threshold:
            resumen["montos_diferentes"] += 1
            comparacion_rows.append(
                ("MONTO_DIFERENTE", orden, round(monto_sap, 2), round(monto_tutati, 2), diferencia)
            )
        else:
            resumen["coinciden"] += 1

    return comparacion_rows, resumen


def _extraer_pagos_por_orden(
    rows: list[tuple[Any, ...]],
    cols: list[str],
    order_candidates: list[str],
    amount_candidates: list[str],
) -> dict[str, float]:
    # Agrupa montos por orden para comparar ambos lados.
    idx_order = _find_col_index(cols, order_candidates)
    idx_amount = _find_col_index(cols, amount_candidates)

    grouped: dict[str, float] = {}
    for row in rows:
        orden = _norm_id(row[idx_order])
        if not orden:
            continue
        grouped[orden] = grouped.get(orden, 0.0) + _to_float(row[idx_amount])
    return grouped


def _find_col_index_optional(cols: list[str], candidates: list[str]) -> int | None:
    # Busca columna opcional; si no existe devuelve None.
    normalized = {c.strip().lower(): i for i, c in enumerate(cols)}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def _fecha_desde_cuid(cuid_value: Any) -> str:
    # Obtiene solo fecha DD-MM-YYYY desde CUID, si es valido.
    if cuid_value is None:
        return ""
    try:
        return cuid_a_fecha(cuid_value).strftime("%d-%m-%Y")
    except Exception:
        return ""


def _add_months(value: date, months: int) -> date:
    # Suma o resta meses manteniendo el dia dentro del mes.
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(value.day, last_day)
    return date(year, month, day)
