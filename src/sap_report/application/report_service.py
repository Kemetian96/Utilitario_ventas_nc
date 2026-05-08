import calendar
import logging
import time
from datetime import date, datetime, time as datetime_time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sap_report.domain import cuid_a_fecha, fecha_a_cuid
from sap_report.infrastructure.db import MySQLRepository, PostgresRepository, SapHanaRepository, SapServiceLayerRepository
from sap_report.infrastructure.export import (
    exportar_comparacion,
    exportar_excel,
    exportar_pestana_excel,
)


LOGGER = logging.getLogger(__name__)


class ReportService:
    def __init__(
        self,
        sap_repository: SapHanaRepository,
        postgres_repository: PostgresRepository,
        mysql_repository: MySQLRepository,
        sl_repository: SapServiceLayerRepository,
        sap_output_path: Path,
        postgres_output_path: Path,
        comparacion_output_path: Path,
    ) -> None:
        # Dependencias de acceso a datos y rutas de salida.
        self._sap_repository = sap_repository
        self._postgres_repository = postgres_repository
        self._mysql_repository = mysql_repository
        self._sl_repository = sl_repository
        self._sap_output_path = sap_output_path
        self._postgres_output_path = postgres_output_path
        self._comparacion_output_path = comparacion_output_path

    def ejecutar_reporte(
        self,
        fecha_inicio_date: date,
        fecha_fin_date: date,
        status_cb=None,
    ) -> dict[str, int | str | None]:
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
            # Ejecuta lotes SAP por dia y exporta el reporte base.
            sap_rows, sap_cols = self._ejecutar_por_lotes(
                fecha_inicio_date,
                fecha_fin_date,
                self._sap_repository,
                "SAP",
                status_cb,
            )
            exportar_excel(sap_rows, sap_cols, self._sap_output_path)
            # Ejecuta notas de credito SAP y agrega pestaña de acumulado.
            sap_nc_rows, sap_nc_cols = self._ejecutar_por_lotes(
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

        try:
            # Ejecuta lotes PostgreSQL por dia y exporta el reporte base.
            pg_rows, pg_cols = self._ejecutar_por_lotes(
                fecha_inicio_date,
                fecha_fin_date,
                self._postgres_repository,
                "POSTGRES",
                status_cb,
            )
            exportar_excel(pg_rows, pg_cols, self._postgres_output_path)
            # Ejecuta notas de credito PostgreSQL y agrega pestaña de acumulado.
            pg_nc_rows, pg_nc_cols = self._ejecutar_por_lotes(
                fecha_inicio_date,
                fecha_fin_date,
                self._postgres_repository,
                "POSTGRES_NC",
                status_cb,
                query_method_name="ejecutar_consulta_nc_sql",
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

        if sap_error and pg_error:
            # Si ambos fallan, se informa error global.
            raise RuntimeError(
                f"SAP fallo: {sap_error} | PostgreSQL fallo: {pg_error}"
            )

        # Genera comparacion solo si ambas fuentes se exportaron sin error.
        comparacion_error: str | None = None
        comparacion_nc_error: str | None = None
        if (not sap_error) and (not pg_error) and sap_cols and pg_cols:
            try:
                self._generar_comparacion(
                    sap_rows,
                    sap_cols,
                    pg_rows,
                    pg_cols,
                    sheet_name="Comparacion",
                )
            except Exception as exc:
                comparacion_error = str(exc)
                LOGGER.exception("Comparacion fallo durante la ejecucion")
        else:
            comparacion_error = "Comparacion omitida por error previo en SAP o PostgreSQL."

        # Genera comparacion NC en otra pestaña.
        if (not sap_error) and (not pg_error) and sap_nc_cols and pg_nc_cols:
            try:
                self._generar_comparacion(
                    sap_nc_rows,
                    sap_nc_cols,
                    pg_nc_rows,
                    pg_nc_cols,
                    sheet_name="Comparacion_NC",
                )
            except Exception as exc:
                comparacion_nc_error = str(exc)
                LOGGER.exception("Comparacion NC fallo durante la ejecucion")
        else:
            comparacion_nc_error = "Comparacion NC omitida por error previo en SAP o PostgreSQL."

        # Retorna resumen para mostrar en UI.
        return {
            "sap": len(sap_rows),
            "postgres": len(pg_rows),
            "sap_error": sap_error,
            "postgres_error": pg_error,
            "comparacion_error": comparacion_error,
            "comparacion_nc_error": comparacion_nc_error,
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

    def validar_articulos(self, status_cb=None) -> list[str]:
        # Ejecuta patch ETL (ayer y anteayer) antes de validar articulos.
        ayer = date.today() - timedelta(days=1)
        anteayer = date.today() - timedelta(days=2)
        if status_cb:
            status_cb(f"Ejecutando patch ETL: {ayer}")
        self._postgres_repository.ejecutar_migrar_oc(ayer)
        time.sleep(1)
        if status_cb:
            status_cb(f"Ejecutando patch ETL: {anteayer}")
        self._postgres_repository.ejecutar_migrar_oc(anteayer)

        # Calcula rango: un mes antes y un mes despues de hoy.
        hoy = date.today()
        fecha_inicio = _add_months(hoy, -1)
        fecha_fin = _add_months(hoy, 1)
        if status_cb:
            status_cb(f"Validando articulos: {fecha_inicio} -> {fecha_fin}")
        return self._sap_repository.ejecutar_validar_articulos(fecha_inicio, fecha_fin)

    def validar_igv(self, status_cb=None) -> dict[str, Any]:
        # Rango para IGV: maximo ultimos 3 dias (usando > inicio y < fin).
        hoy = date.today()
        fecha_inicio = hoy - timedelta(days=3)
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
                "sp_orders": 0,
                "sp_rmas": 0,
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
                "sp_orders": 0,
                "sp_rmas": 0,
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
                "sp_orders": 0,
                "sp_rmas": 0,
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

        # Ejecuta creacion de movimientos en MySQL para ultimos 3 dias.
        cuid_inicio = fecha_a_cuid(datetime.combine(hoy - timedelta(days=3), datetime.min.time()))
        cuid_fin = fecha_a_cuid(datetime.combine(hoy, datetime.min.time()))
        if status_cb:
            status_cb("Buscando UID_ORDERS pendientes...")
        uid_orders = self._mysql_repository.obtener_uid_orders_pendientes(cuid_inicio, cuid_fin)
        if status_cb:
            status_cb(f"Ejecutando SP ORDER: {len(uid_orders)}")
        ok_orders = self._mysql_repository.ejecutar_sp_create_document_movement(uid_orders, "ORDER")

        if status_cb:
            status_cb("Buscando UID_RMAS pendientes...")
        uid_rmas = self._mysql_repository.obtener_uid_rmas_pendientes(cuid_inicio, cuid_fin)
        if status_cb:
            status_cb(f"Ejecutando SP RMA: {len(uid_rmas)}")
        ok_rmas = self._mysql_repository.ejecutar_sp_create_document_movement(uid_rmas, "RMA")

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
            "sp_orders": ok_orders,
            "sp_rmas": ok_rmas,
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
                            id_order = str(row[idx_id_order]) if idx_id_order is not None and row[idx_id_order] is not None else ""
                            uid = str(row[idx_uid]) if idx_uid is not None and row[idx_uid] is not None else ""
                            docentry = docentry_por_orden.get(id_order, "")
                            material = str(row[idx_material]) if row[idx_material] is not None else ""
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
        return self._sl_repository.consultar_pago(orden, company_db)

    def anular_pago_sap(self, doc_entry: int, company_db: str) -> None:
        if doc_entry <= 0:
            raise ValueError("DocEntry inválido.")
        self._sl_repository.anular_pago(doc_entry, company_db)

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

    def _ejecutar_por_lotes(
        self,
        fecha_inicio_date: date,
        fecha_fin_date: date,
        repository,
        etiqueta: str,
        status_cb=None,
        query_method_name: str = "ejecutar_consulta_sql",
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta por dia para evitar consultas demasiado grandes.
        fecha_actual = fecha_inicio_date
        rows_total: list[tuple[Any, ...]] = []
        cols: list[str] | None = None
        paso = 0

        while fecha_actual <= fecha_fin_date:
            paso += 1
            msg = f"{etiqueta} lote {paso}: {fecha_actual} -> {fecha_actual}"
            LOGGER.info(msg)
            if status_cb:
                status_cb(msg)

            rows, cols = getattr(repository, query_method_name)(fecha_actual, fecha_actual)
            rows_total.extend(rows)
            fecha_actual += timedelta(days=1)

        if cols is None:
            raise RuntimeError(f"La consulta {etiqueta} no devolvio estructura de columnas.")

        # Devuelve todo apilado (sin consolidar).
        return rows_total, cols

    def _generar_comparacion(
        self,
        sap_rows: list[tuple[Any, ...]],
        sap_cols: list[str],
        pg_rows: list[tuple[Any, ...]],
        pg_cols: list[str],
        sheet_name: str,
    ) -> None:
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


def _find_col_index(cols: list[str], candidates: list[str]) -> int:
    # Busca columna requerida (case-insensitive).
    normalized = {c.strip().lower(): i for i, c in enumerate(cols)}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    raise RuntimeError(f"No se encontro columna requerida. Esperadas: {', '.join(candidates)}")


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

    validacion_rows, validacion_cols = sap_repository.ejecutar_validacion_nc(list(dict.fromkeys(docentries)))
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
        articulos_rows, articulos_cols = sap_repository.ejecutar_validacion_nc_articulos(
            faltantes_candidatos
        )
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
