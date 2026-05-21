import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

try:
    from hdbcli import dbapi
except ImportError:
    dbapi = None

from sap_report.infrastructure.config import Settings

from ._base import _render_in_list


LOGGER = logging.getLogger(__name__)

_QUERIES_DIR = Path(__file__).resolve().parent / "queries" / "hana"

REPORTE_VENTAS_PATH = _QUERIES_DIR / "reporte_ventas.sql"
REPORTE_NOTAS_CREDITO_PATH = _QUERIES_DIR / "reporte_notas_credito.sql"
VALIDAR_ARTICULOS_PATH = _QUERIES_DIR / "validar_articulos.sql"
VALIDAR_IGV_DOCUMENTOS_PATH = _QUERIES_DIR / "validar_igv_documentos.sql"
VALIDAR_IGV_ITEMS_PATH = _QUERIES_DIR / "validar_igv_items.sql"
ACTUALIZAR_IGV_COMERCIAL_PATH = _QUERIES_DIR / "actualizar_igv_comercial.sql"
ACTUALIZAR_IGV_PEDRAL_PATH = _QUERIES_DIR / "actualizar_igv_pedral.sql"
ACTUALIZAR_IGV_HILOS_PATH = _QUERIES_DIR / "actualizar_igv_hilos.sql"
REVISAR_HILOS_PATH = _QUERIES_DIR / "revisar_hilos.sql"
PRESTAMO_STOCK_PATH = _QUERIES_DIR / "prestamo_stock.sql"
PRESTAMO_LOGPROCESO_PATH = _QUERIES_DIR / "prestamo_logproceso.sql"
PRESTAMO_LOGPROCESO_DEV_PATH = _QUERIES_DIR / "prestamo_logproceso_dev.sql"
PRESTAMO_TRANI_PATH = _QUERIES_DIR / "prestamo_trani.sql"
VALIDACION_NC_PATH = _QUERIES_DIR / "validacion_nc.sql"
VALIDACION_NC_ARTICULOS_PATH = _QUERIES_DIR / "validacion_nc_articulos.sql"
VALIDAR_PAGOS_PATH = _QUERIES_DIR / "validar_pagos.sql"
DATOS_FACTURA_PATH = _QUERIES_DIR / "datos_factura.sql"


class SapHanaRepository:
    def __init__(self, settings: Settings) -> None:
        if dbapi is None:
            raise RuntimeError("Falta dependencia hdbcli. Instala con: pip install hdbcli")
        self._settings = settings
        self._query_reporte_ventas = REPORTE_VENTAS_PATH.read_text(encoding="utf-8")
        self._query_reporte_notas_credito = REPORTE_NOTAS_CREDITO_PATH.read_text(encoding="utf-8")
        self._query_validar_articulos = VALIDAR_ARTICULOS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_documentos = VALIDAR_IGV_DOCUMENTOS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_items = VALIDAR_IGV_ITEMS_PATH.read_text(encoding="utf-8")
        self._query_actualizar_igv_comercial = ACTUALIZAR_IGV_COMERCIAL_PATH.read_text(encoding="utf-8")
        self._query_actualizar_igv_pedral = ACTUALIZAR_IGV_PEDRAL_PATH.read_text(encoding="utf-8")
        self._query_actualizar_igv_hilos = ACTUALIZAR_IGV_HILOS_PATH.read_text(encoding="utf-8")
        self._query_revisar_hilos = REVISAR_HILOS_PATH.read_text(encoding="utf-8")
        self._query_prestamo_stock = PRESTAMO_STOCK_PATH.read_text(encoding="utf-8")
        self._query_prestamo_logproceso = PRESTAMO_LOGPROCESO_PATH.read_text(encoding="utf-8")
        self._query_prestamo_logproceso_dev = PRESTAMO_LOGPROCESO_DEV_PATH.read_text(encoding="utf-8")
        self._query_prestamo_trani = PRESTAMO_TRANI_PATH.read_text(encoding="utf-8")
        self._query_validacion_nc = VALIDACION_NC_PATH.read_text(encoding="utf-8")
        self._query_validacion_nc_articulos = VALIDACION_NC_ARTICULOS_PATH.read_text(encoding="utf-8")
        self._query_validar_pagos = VALIDAR_PAGOS_PATH.read_text(encoding="utf-8")
        self._query_datos_factura = DATOS_FACTURA_PATH.read_text(encoding="utf-8")

    def ejecutar_consulta_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        sql = self._render_query(fecha_inicio, fecha_fin)
        return self._ejecutar_sql(sql)

    def ejecutar_consulta_nc_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_reporte_notas_credito)
        return self._ejecutar_sql(sql)

    def ejecutar_validar_articulos(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> list[str]:
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_validar_articulos)
        rows, _cols = self._ejecutar_sql(sql)
        return [str(row[0]) for row in rows if row and row[0]]

    def ejecutar_validar_igv(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_validar_igv_documentos)
        return self._ejecutar_sql(sql)

    def ejecutar_validar_igv_items(self, items: list[str]) -> list[str]:
        if not items:
            return []
        items_in = _render_in_list(items)
        sql = self._query_validar_igv_items.replace("{{items_in}}", items_in)
        rows, _cols = self._ejecutar_sql(sql)
        return [str(r[0]) for r in rows if r and r[0]]

    def ejecutar_actualizar_igv_comercial(self, items: list[str]) -> int:
        if not items:
            return 0
        items_in = _render_in_list(items)
        sql = self._query_actualizar_igv_comercial.replace("{{items_in}}", items_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_actualizar_igv_pedral(self, items: list[str]) -> int:
        if not items:
            return 0
        items_in = _render_in_list(items)
        sql = self._query_actualizar_igv_pedral.replace("{{items_in}}", items_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_actualizar_igv_hilos(self, docentries: list[str]) -> int:
        if not docentries:
            return 0
        doc_in = _render_in_list(docentries)
        sql = self._query_actualizar_igv_hilos.replace("{{docentries_in}}", doc_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_revisar_hilos(self) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql(self._query_revisar_hilos)

    def ejecutar_prestamo_stock(
        self,
        items: list[str],
        centros: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not items or not centros:
            return [], ["ItemCode", "WhsCode", "ItemWarehouse", "Stock", "Procencia"]
        items_in = _render_in_list(items)
        centros_in = _render_in_list(centros)
        sql = (
            self._query_prestamo_stock.replace("{{items_in}}", items_in)
            .replace("{{centros_in}}", centros_in)
        )
        return self._ejecutar_sql(sql)

    def obtener_docentries_prestamo(
        self,
        fecha_desde: date,
    ) -> list[str]:
        sql = self._query_prestamo_logproceso.replace(
            "{{fecha_desde}}", fecha_desde.strftime("%Y-%m-%d")
        )
        rows, _cols = self._ejecutar_sql(sql)
        return [str(row[0]).strip() for row in rows if row and row[0] is not None and str(row[0]).strip()]

    def obtener_keys_prestamo_dev(self, fecha_desde: date) -> list[str]:
        sql = self._query_prestamo_logproceso_dev.replace(
            "{{fecha_desde}}", fecha_desde.strftime("%Y-%m-%d")
        )
        rows, _cols = self._ejecutar_sql(sql)
        return [str(row[0]).strip() for row in rows if row and row[0] is not None and str(row[0]).strip()]

    def ejecutar_prestamo_trani(self, keys: list[str]) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not keys:
            return [], ["U_BOT_CODARTICULO", "U_PLA_CANTIDAD", "U_BOT_ALMACEN_DEVID"]
        keys_in = _render_in_list(keys)
        sql = self._query_prestamo_trani.replace("{{keys_in}}", keys_in)
        return self._ejecutar_sql(sql)

    def ejecutar_validacion_nc(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not docentries:
            return [], ["DocEntry", "U_BOT_DOCENTRY"]
        docentries_in = _render_in_list(docentries)
        sql = self._query_validacion_nc.replace("{{U_BOT_DOCENTRY}}", docentries_in)
        return self._ejecutar_sql(sql)

    def ejecutar_validacion_nc_articulos(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not docentries:
            return [], ["DocEntry", "U_BOT_CODARTICULO"]
        docentries_in = _render_in_list(docentries)
        sql = self._query_validacion_nc_articulos.replace("{{DOCENTRY_IN}}", docentries_in)
        return self._ejecutar_sql(sql)

    def ejecutar_validar_pagos(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        account_name: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        account_name_safe = account_name.replace("'", "''")
        sql = (
            self._query_validar_pagos
            .replace("{{fecha_inicio}}", fecha_inicio.strftime("%Y-%m-%d"))
            .replace("{{fecha_fin}}", fecha_fin.strftime("%Y-%m-%d"))
            .replace("{{account_name}}", account_name_safe)
        )
        return self._ejecutar_sql(sql)

    def ejecutar_datos_factura(self, orden: str, schema: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        sql = (
            self._query_datos_factura
            .replace("{{schema}}", schema)
            .replace("{{orden}}", orden.replace("'", "''"))
        )
        return self._ejecutar_sql(sql)

    def ejecutar_visor_nubefact(self, fecha: date) -> tuple[list[tuple[Any, ...]], list[str]]:
        fecha_str = fecha.strftime("%Y-%m-%d")
        sql = f"CALL B1H_INVERSIONES_PROD.PLA_VISOR_NUBEFACT('{fecha_str}')"
        return self._ejecutar_sql(sql)

    def probar_conexion(self) -> None:
        conn = dbapi.connect(**self._conn_kwargs())
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM DUMMY")
            cur.fetchone()
        finally:
            cur.close()
            conn.close()

    def _conn_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "address": self._settings.sap_hana_host,
            "port": self._settings.sap_hana_port,
            "user": self._settings.sap_hana_user,
            "password": self._settings.sap_hana_password,
        }
        if self._settings.sap_hana_encrypt is not None:
            kwargs["encrypt"] = self._settings.sap_hana_encrypt
        if self._settings.sap_hana_ssl_validate_certificate is not None:
            kwargs["sslValidateCertificate"] = self._settings.sap_hana_ssl_validate_certificate
        if self._settings.sap_hana_connect_timeout is not None:
            kwargs["connecttimeout"] = self._settings.sap_hana_connect_timeout
        if self._settings.sap_hana_ssl_trust_store:
            kwargs["sslTrustStore"] = self._settings.sap_hana_ssl_trust_store
        if self._settings.sap_hana_ssl_key_store_password:
            kwargs["sslKeyStorePassword"] = self._settings.sap_hana_ssl_key_store_password
        return kwargs

    def _ejecutar_sql(self, sql: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = dbapi.connect(**self._conn_kwargs())
                cur = conn.cursor()
                cur.execute(sql)
                rows = cur.fetchall()
                if cur.description is None:
                    raise RuntimeError("La consulta SAP no devolvio metadatos de columnas.")
                cols = [c[0] for c in cur.description]
                return rows, cols
            except dbapi.Error as exc:
                LOGGER.warning(
                    "Conexion SAP caida (intento %s/%s): %s | encrypt=%s | sslValidateCertificate=%s",
                    intento,
                    self._settings.reintentos,
                    exc,
                    self._settings.sap_hana_encrypt,
                    self._settings.sap_hana_ssl_validate_certificate,
                )
                if intento == self._settings.reintentos:
                    raise
                time.sleep(self._settings.espera_segundos)
            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()

        raise RuntimeError("No se pudo ejecutar la consulta SAP tras todos los reintentos.")

    def _ejecutar_sql_modificacion(self, sql: str) -> int:
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = dbapi.connect(**self._conn_kwargs())
                cur = conn.cursor()
                cur.execute(sql)
                return cur.rowcount if cur.rowcount is not None else 0
            except dbapi.Error as exc:
                LOGGER.warning(
                    "Operacion SAP caida (intento %s/%s): %s",
                    intento,
                    self._settings.reintentos,
                    exc,
                )
                if intento == self._settings.reintentos:
                    raise
                time.sleep(self._settings.espera_segundos)
            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()

        raise RuntimeError("No se pudo ejecutar la operacion SAP tras todos los reintentos.")

    def _render_query(self, fecha_inicio: date, fecha_fin: date, query_template: str | None = None) -> str:
        template = query_template or self._query_reporte_ventas
        return (
            template
            .replace("{{fecha_inicio}}", fecha_inicio.strftime("%Y-%m-%d"))
            .replace("{{fecha_fin}}", fecha_fin.strftime("%Y-%m-%d"))
        )
