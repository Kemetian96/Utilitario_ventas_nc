import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2
try:
    import pymysql
except ImportError:
    pymysql = None
try:
    from hdbcli import dbapi
except ImportError:
    dbapi = None

from sap_report.domain import fecha_a_cuid
from sap_report.infrastructure.config import Settings


LOGGER = logging.getLogger(__name__)
# Rutas SQL por motor.
SAP_QUERY_PATH = Path(__file__).resolve().parent / "queries" / "SAP.sql"
SAP_NC_QUERY_PATH = Path(__file__).resolve().parent / "queries" / "sap_nc.sql"
PG_QUERY_PATH = Path(__file__).resolve().parent / "queries" / "TUTATI.sql"
PG_NC_QUERY_PATH = Path(__file__).resolve().parent / "queries" / "tutati_nc.sql"
SAP_VALIDAR_ARTICULOS_PATH = Path(__file__).resolve().parent / "queries" / "validar_articulos.sql"
SAP_VALIDAR_IGV_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_sap.sql"
SAP_VALIDAR_IGV_ITEMS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_sap_items.sql"
SAP_VALIDAR_IGV_UPDATE_COMERCIAL_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_update_comercial.sql"
SAP_VALIDAR_IGV_UPDATE_PEDRAL_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_update_pedral.sql"
SAP_VALIDAR_IGV_UPDATE_HILOS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_update_hilos.sql"
SAP_REVISAR_HILOS_PATH = Path(__file__).resolve().parent / "queries" / "revisar_hilos.sql"
SAP_PRESTAMO_STOCK_PATH = Path(__file__).resolve().parent / "queries" / "prestamo_stock.sql"
SAP_PRESTAMO_LOGPROCESO_PATH = Path(__file__).resolve().parent / "queries" / "prestamo_logproceso.sql"
SAP_VALIDACION_NC_PATH = Path(__file__).resolve().parent / "queries" / "ValidacionNC.sql"
SAP_VALIDACION_NC_ARTICULOS_PATH = Path(__file__).resolve().parent / "queries" / "ValidacionNCArticulos.sql"
SAP_VALIDAR_PAGOS_PATH = Path(__file__).resolve().parent / "queries" / "Validar_pagos_sap.sql"
PG_PATCH_ETL_PATH = Path(__file__).resolve().parent / "queries" / "migrar_OC.sql"
MYSQL_VALIDAR_IGV_DOCS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_mysql_docs.sql"
MYSQL_VALIDAR_IGV_ITEMS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_mysql_items.sql"
MYSQL_VALIDAR_IGV_PEND_ORDERS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_mysql_pendientes_orders.sql"
MYSQL_VALIDAR_IGV_PEND_RMAS_PATH = Path(__file__).resolve().parent / "queries" / "validar_igv_mysql_pendientes_rmas.sql"
MYSQL_VALIDAR_PAGOS_PATH = Path(__file__).resolve().parent / "queries" / "Validar_pagos_tutati.sql"
MYSQL_POR_ENVIAR_PATH = Path(__file__).resolve().parent / "queries" / "PorEnviar.sql"
MYSQL_ANULAR_MOVIMIENTO_PATH = Path(__file__).resolve().parent / "queries" / "anular_movimiento_por_enviar.sql"


class SapHanaRepository:
    def __init__(self, settings: Settings) -> None:
        # Valida dependencia nativa de SAP HANA.
        if dbapi is None:
            raise RuntimeError("Falta dependencia hdbcli. Instala con: pip install hdbcli")
        self._settings = settings
        # Carga plantilla SQL de SAP.
        self._query_template = SAP_QUERY_PATH.read_text(encoding="utf-8")
        self._query_nc_template = SAP_NC_QUERY_PATH.read_text(encoding="utf-8")
        self._query_validar_articulos = SAP_VALIDAR_ARTICULOS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv = SAP_VALIDAR_IGV_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_items = SAP_VALIDAR_IGV_ITEMS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_update_comercial = SAP_VALIDAR_IGV_UPDATE_COMERCIAL_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_update_pedral = SAP_VALIDAR_IGV_UPDATE_PEDRAL_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_update_hilos = SAP_VALIDAR_IGV_UPDATE_HILOS_PATH.read_text(encoding="utf-8")
        self._query_revisar_hilos = SAP_REVISAR_HILOS_PATH.read_text(encoding="utf-8")
        self._query_prestamo_stock = SAP_PRESTAMO_STOCK_PATH.read_text(encoding="utf-8")
        self._query_prestamo_logproceso = SAP_PRESTAMO_LOGPROCESO_PATH.read_text(encoding="utf-8")
        self._query_validacion_nc = SAP_VALIDACION_NC_PATH.read_text(encoding="utf-8")
        self._query_validacion_nc_articulos = SAP_VALIDACION_NC_ARTICULOS_PATH.read_text(
            encoding="utf-8"
        )
        self._query_validar_pagos = SAP_VALIDAR_PAGOS_PATH.read_text(encoding="utf-8")

    def ejecutar_consulta_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Reemplaza fechas en formato esperado por SAP.
        sql = self._render_query(fecha_inicio, fecha_fin)
        return self._ejecutar_sql(sql)

    def ejecutar_consulta_nc_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta SQL de notas de credito en SAP.
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_nc_template)
        return self._ejecutar_sql(sql)

    def ejecutar_validar_articulos(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> list[str]:
        # Ejecuta SQL de validacion de articulos y devuelve URLs.
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_validar_articulos)
        rows, _cols = self._ejecutar_sql(sql)
        return [str(row[0]) for row in rows if row and row[0]]

    def ejecutar_validar_igv(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta SQL de validacion IGV en SAP.
        sql = self._render_query(fecha_inicio, fecha_fin, self._query_validar_igv)
        return self._ejecutar_sql(sql)

    def ejecutar_validar_igv_items(self, items: list[str]) -> list[str]:
        # Consulta Items con TaxCodeAR = IGV en SAP.
        if not items:
            return []
        items_in = _render_in_list(items)
        sql = self._query_validar_igv_items.replace("{{items_in}}", items_in)
        rows, _cols = self._ejecutar_sql(sql)
        return [str(r[0]) for r in rows if r and r[0]]

    def ejecutar_actualizar_igv_comercial(self, items: list[str]) -> int:
        # Actualiza TaxCodeAP en B1H_COMERCIALMONT_PROD.
        if not items:
            return 0
        items_in = _render_in_list(items)
        sql = self._query_validar_igv_update_comercial.replace("{{items_in}}", items_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_actualizar_igv_pedral(self, items: list[str]) -> int:
        # Actualiza TaxCodeAP en B1H_PEDRAL_PROD.
        if not items:
            return 0
        items_in = _render_in_list(items)
        sql = self._query_validar_igv_update_pedral.replace("{{items_in}}", items_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_actualizar_igv_hilos(self, docentries: list[str]) -> int:
        # Actualiza U_BOT_HILOS y U_BOT_FLAG_ANULACION en SAP.
        if not docentries:
            return 0
        doc_in = _render_in_list(docentries)
        sql = self._query_validar_igv_update_hilos.replace("{{docentries_in}}", doc_in)
        return self._ejecutar_sql_modificacion(sql)

    def ejecutar_revisar_hilos(self) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta consulta de hilos pendientes en SAP.
        return self._ejecutar_sql(self._query_revisar_hilos)

    def ejecutar_prestamo_stock(
        self,
        items: list[str],
        centros: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta consulta de stock por item/centro en SAP.
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
        # Busca DocEntry afectados por error de inventario negativo.
        sql = self._query_prestamo_logproceso.replace(
            "{{fecha_desde}}", fecha_desde.strftime("%Y-%m-%d")
        )
        rows, _cols = self._ejecutar_sql(sql)
        return [str(row[0]).strip() for row in rows if row and row[0] is not None and str(row[0]).strip()]

    def ejecutar_validacion_nc(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Valida U_BOT_DOCENTRY de NC contra ORIN.
        if not docentries:
            return [], ["DocEntry", "U_BOT_DOCENTRY"]
        docentries_in = _render_in_list(docentries)
        sql = self._query_validacion_nc.replace("{{U_BOT_DOCENTRY}}", docentries_in)
        return self._ejecutar_sql(sql)

    def ejecutar_validacion_nc_articulos(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Obtiene articulos por DocEntry para excluir NC especiales.
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
        # Ejecuta conciliacion de pagos en SAP por fecha y medio de pago.
        account_name_safe = account_name.replace("'", "''")
        sql = (
            self._query_validar_pagos
            .replace("{{fecha_inicio}}", fecha_inicio.strftime("%Y-%m-%d"))
            .replace("{{fecha_fin}}", fecha_fin.strftime("%Y-%m-%d"))
            .replace("{{account_name}}", account_name_safe)
        )
        return self._ejecutar_sql(sql)

    def _ejecutar_sql(self, sql: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Reintenta la conexion ante fallos temporales.
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn_kwargs = {
                    # Config minima equivalente a DBeaver.
                    "address": self._settings.sap_hana_host,
                    "port": self._settings.sap_hana_port,
                    "user": self._settings.sap_hana_user,
                    "password": self._settings.sap_hana_password,
                }
                if self._settings.sap_hana_encrypt is not None:
                    # Opcional: se activa solo si viene en .env.
                    conn_kwargs["encrypt"] = self._settings.sap_hana_encrypt
                if self._settings.sap_hana_ssl_validate_certificate is not None:
                    conn_kwargs["sslValidateCertificate"] = self._settings.sap_hana_ssl_validate_certificate
                if self._settings.sap_hana_connect_timeout is not None:
                    conn_kwargs["connecttimeout"] = self._settings.sap_hana_connect_timeout
                if self._settings.sap_hana_ssl_trust_store:
                    conn_kwargs["sslTrustStore"] = self._settings.sap_hana_ssl_trust_store
                if self._settings.sap_hana_ssl_key_store_password:
                    conn_kwargs["sslKeyStorePassword"] = self._settings.sap_hana_ssl_key_store_password

                conn = dbapi.connect(
                    **conn_kwargs,
                )
                cur = conn.cursor()
                # Ejecuta SQL y devuelve filas + cabeceras.
                cur.execute(sql)
                rows = cur.fetchall()
                if cur.description is None:
                    raise RuntimeError("La consulta SAP no devolvio metadatos de columnas.")
                cols = [c[0] for c in cur.description]
                return rows, cols
            except dbapi.Error as exc:
                # Registra diagnostico detallado por intento.
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
        # Ejecuta SQL de actualizacion en SAP y devuelve filas afectadas.
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn_kwargs = {
                    "address": self._settings.sap_hana_host,
                    "port": self._settings.sap_hana_port,
                    "user": self._settings.sap_hana_user,
                    "password": self._settings.sap_hana_password,
                }
                if self._settings.sap_hana_encrypt is not None:
                    conn_kwargs["encrypt"] = self._settings.sap_hana_encrypt
                if self._settings.sap_hana_ssl_validate_certificate is not None:
                    conn_kwargs["sslValidateCertificate"] = self._settings.sap_hana_ssl_validate_certificate
                if self._settings.sap_hana_connect_timeout is not None:
                    conn_kwargs["connecttimeout"] = self._settings.sap_hana_connect_timeout
                if self._settings.sap_hana_ssl_trust_store:
                    conn_kwargs["sslTrustStore"] = self._settings.sap_hana_ssl_trust_store
                if self._settings.sap_hana_ssl_key_store_password:
                    conn_kwargs["sslKeyStorePassword"] = self._settings.sap_hana_ssl_key_store_password

                conn = dbapi.connect(**conn_kwargs)
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

    def probar_conexion(self) -> None:
        # Conexion corta para validar credenciales/red sin ejecutar reporte.
        conn_kwargs = {
            "address": self._settings.sap_hana_host,
            "port": self._settings.sap_hana_port,
            "user": self._settings.sap_hana_user,
            "password": self._settings.sap_hana_password,
        }
        if self._settings.sap_hana_encrypt is not None:
            conn_kwargs["encrypt"] = self._settings.sap_hana_encrypt
        if self._settings.sap_hana_ssl_validate_certificate is not None:
            conn_kwargs["sslValidateCertificate"] = self._settings.sap_hana_ssl_validate_certificate
        if self._settings.sap_hana_connect_timeout is not None:
            conn_kwargs["connecttimeout"] = self._settings.sap_hana_connect_timeout
        if self._settings.sap_hana_ssl_trust_store:
            conn_kwargs["sslTrustStore"] = self._settings.sap_hana_ssl_trust_store
        if self._settings.sap_hana_ssl_key_store_password:
            conn_kwargs["sslKeyStorePassword"] = self._settings.sap_hana_ssl_key_store_password

        conn = dbapi.connect(**conn_kwargs)
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM DUMMY")
            cur.fetchone()
        finally:
            cur.close()
            conn.close()

    def _render_query(self, fecha_inicio: date, fecha_fin: date, query_template: str | None = None) -> str:
        # Formato de fecha solicitado: YYYY-MM-DD.
        template = query_template or self._query_template
        return (
            template
            .replace("{{fecha_inicio}}", fecha_inicio.strftime("%Y-%m-%d"))
            .replace("{{fecha_fin}}", fecha_fin.strftime("%Y-%m-%d"))
        )


class PostgresRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Carga SQL parametrizado para PostgreSQL.
        self._query = PG_QUERY_PATH.read_text(encoding="utf-8")
        self._query_nc = PG_NC_QUERY_PATH.read_text(encoding="utf-8")
        self._query_patch_etl = PG_PATCH_ETL_PATH.read_text(encoding="utf-8")

    def ejecutar_consulta_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql(self._query, fecha_inicio, fecha_fin)

    def ejecutar_consulta_nc_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta SQL de notas de credito en PostgreSQL.
        return self._ejecutar_sql(self._query_nc, fecha_inicio, fecha_fin)

    def _ejecutar_sql(
        self,
        query: str,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Convierte rango fecha->CUID para filtro en PostgreSQL.
        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())
        params = {
            "fecha1": fecha_a_cuid(inicio_dt),
            "fecha2": fecha_a_cuid(fin_dt),
        }

        # Reintenta la conexion ante cortes.
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = psycopg2.connect(
                    host=self._settings.pg_host,
                    dbname=self._settings.pg_name,
                    user=self._settings.pg_user,
                    password=self._settings.pg_password,
                    port=self._settings.pg_port,
                    sslmode=self._settings.pg_sslmode,
                    connect_timeout=self._settings.pg_connect_timeout,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                )
                conn.autocommit = True
                cur = conn.cursor()
                # Ejecuta SQL y devuelve filas + cabeceras.
                cur.execute(query, params)
                rows = cur.fetchall()
                if cur.description is None:
                    raise RuntimeError("La consulta PostgreSQL no devolvio metadatos de columnas.")
                cols = [c[0] for c in cur.description]
                return rows, cols
            except psycopg2.OperationalError as exc:
                # Log por intento para diagnostico de red.
                LOGGER.warning(
                    "Conexion PostgreSQL caida (intento %s/%s): %s",
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

        raise RuntimeError("No se pudo ejecutar la consulta PostgreSQL tras todos los reintentos.")

    def probar_conexion(self) -> None:
        # Conexion corta para validar acceso a PostgreSQL.
        conn = psycopg2.connect(
            host=self._settings.pg_host,
            dbname=self._settings.pg_name,
            user=self._settings.pg_user,
            password=self._settings.pg_password,
            port=self._settings.pg_port,
            sslmode=self._settings.pg_sslmode,
            connect_timeout=self._settings.pg_connect_timeout,
        )
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
            conn.close()

    def ejecutar_migrar_oc(self, fecha: date) -> None:
        # Ejecuta migracion OC en PostgreSQL con fecha especifica.
        sql = self._query_patch_etl.replace("{{fecha}}", fecha.strftime("%Y-%m-%d"))
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = psycopg2.connect(
                    host=self._settings.pg_host,
                    dbname=self._settings.pg_name,
                    user=self._settings.pg_user,
                    password=self._settings.pg_password,
                    port=self._settings.pg_port,
                    sslmode=self._settings.pg_sslmode,
                    connect_timeout=self._settings.pg_connect_timeout,
                )
                conn.autocommit = True
                cur = conn.cursor()
                cur.execute(sql)
                LOGGER.info("Migrar_OC ejecutado OK para fecha %s", fecha)
                return
            except psycopg2.OperationalError as exc:
                LOGGER.warning(
                    "Migrar_OC fallo (intento %s/%s) para fecha %s: %s",
                    intento,
                    self._settings.reintentos,
                    fecha,
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


class MySQLRepository:
    def __init__(self, settings: Settings) -> None:
        # Valida dependencia de MySQL.
        if pymysql is None:
            raise RuntimeError("Falta dependencia pymysql. Instala con: pip install pymysql")
        # Valida que las credenciales obligatorias esten presentes.
        if not settings.mysql_host:
            raise ValueError("Falta MYSQL_HOST en .env")
        if not settings.mysql_name:
            raise ValueError("Falta MYSQL_NAME en .env")
        if not settings.mysql_user:
            raise ValueError("Falta MYSQL_USER en .env")
        if not settings.mysql_password:
            raise ValueError("Falta MYSQL_PASSWORD en .env")
        self._settings = settings
        self._mysql_host = settings.mysql_host
        self._mysql_name = settings.mysql_name
        self._mysql_user = settings.mysql_user
        self._mysql_password = settings.mysql_password
        self._mysql_port = settings.mysql_port or 3306
        self._mysql_connect_timeout = settings.mysql_connect_timeout or 10
        self._query_validar_igv_docs = MYSQL_VALIDAR_IGV_DOCS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_items = MYSQL_VALIDAR_IGV_ITEMS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_pend_orders = MYSQL_VALIDAR_IGV_PEND_ORDERS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_pend_rmas = MYSQL_VALIDAR_IGV_PEND_RMAS_PATH.read_text(encoding="utf-8")
        self._query_validar_pagos = MYSQL_VALIDAR_PAGOS_PATH.read_text(encoding="utf-8")
        self._query_por_enviar = MYSQL_POR_ENVIAR_PATH.read_text(encoding="utf-8")
        self._query_anular_movimiento = MYSQL_ANULAR_MOVIMIENTO_PATH.read_text(encoding="utf-8")

    def probar_conexion(self) -> None:
        # Conexion corta para validar acceso a MySQL.
        conn = pymysql.connect(
            host=self._mysql_host,
            user=self._mysql_user,
            password=self._mysql_password,
            database=self._mysql_name,
            port=self._mysql_port,
            connect_timeout=self._mysql_connect_timeout,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()

    def ejecutar_sql(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta SQL en MySQL con reintentos.
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = pymysql.connect(
                    host=self._mysql_host,
                    user=self._mysql_user,
                    password=self._mysql_password,
                    database=self._mysql_name,
                    port=self._mysql_port,
                    connect_timeout=self._mysql_connect_timeout,
                )
                with conn.cursor() as cur:
                    if params is None:
                        cur.execute(query)
                    else:
                        cur.execute(query, params)
                    rows = cur.fetchall()
                    cols = [desc[0] for desc in cur.description] if cur.description else []
                    return list(rows), cols
            except pymysql.MySQLError as exc:
                LOGGER.warning(
                    "Conexion MySQL caida (intento %s/%s): %s",
                    intento,
                    self._settings.reintentos,
                    exc,
                )
                if intento == self._settings.reintentos:
                    raise
                time.sleep(self._settings.espera_segundos)
            finally:
                if conn:
                    conn.close()

        raise RuntimeError("No se pudo ejecutar la consulta MySQL tras todos los reintentos.")

    def ejecutar_validar_igv_docs(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta query de documentos en MySQL.
        if not docentries:
            return [], ["id_document", "DocEntry"]
        doc_in = _render_in_list(docentries)
        sql = self._query_validar_igv_docs.replace("{{docentries_in}}", doc_in)
        return self.ejecutar_sql(sql)

    def ejecutar_validar_igv_items(
        self,
        document_ids: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta query de items en MySQL.
        if not document_ids:
            return [], []
        doc_in = _render_in_list(document_ids)
        sql = self._query_validar_igv_items.replace("{{documents_in}}", doc_in)
        return self.ejecutar_sql(sql)

    def obtener_uid_orders_pendientes(self, cuid_inicio: int, cuid_fin: int) -> list[str]:
        # Obtiene UID_ORDERS pendientes para crear movimiento.
        sql = (
            self._query_validar_igv_pend_orders
            .replace("{{cuid_inicio}}", str(cuid_inicio))
            .replace("{{cuid_fin}}", str(cuid_fin))
        )
        rows, _cols = self.ejecutar_sql(sql)
        return [str(r[0]) for r in rows if r and r[0]]

    def obtener_uid_rmas_pendientes(self, cuid_inicio: int, cuid_fin: int) -> list[str]:
        # Obtiene UID_RMAS pendientes para crear movimiento.
        sql = (
            self._query_validar_igv_pend_rmas
            .replace("{{cuid_inicio}}", str(cuid_inicio))
            .replace("{{cuid_fin}}", str(cuid_fin))
        )
        rows, _cols = self.ejecutar_sql(sql)
        return [str(r[0]) for r in rows if r and r[0]]

    def ejecutar_sp_create_document_movement(self, uids: list[str], tipo: str) -> int:
        # Ejecuta el SP de movimiento para cada UID.
        if not uids:
            return 0
        total_ok = 0
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = pymysql.connect(
                    host=self._mysql_host,
                    user=self._mysql_user,
                    password=self._mysql_password,
                    database=self._mysql_name,
                    port=self._mysql_port,
                    connect_timeout=self._mysql_connect_timeout,
                )
                with conn.cursor() as cur:
                    for uid in uids:
                        cur.execute("CALL main.sp_create_document_movement(%s, %s)", (uid, tipo))
                        total_ok += 1
                return total_ok
            except pymysql.MySQLError as exc:
                LOGGER.warning(
                    "SP create_document_movement fallo (intento %s/%s) tipo %s: %s",
                    intento,
                    self._settings.reintentos,
                    tipo,
                    exc,
                )
                total_ok = 0
                if intento == self._settings.reintentos:
                    raise
                time.sleep(self._settings.espera_segundos)
            finally:
                if conn:
                    conn.close()

        return total_ok

    def ejecutar_validar_pagos(
        self,
        cuid_inicio: int,
        cuid_fin: int,
        account_name: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        # Ejecuta conciliacion de pagos en MySQL por fecha y medio de pago.
        account_name_safe = account_name.replace("'", "''")
        sql = (
            self._query_validar_pagos
            .replace("{{cuid_inicio}}", str(cuid_inicio))
            .replace("{{cuid_fin}}", str(cuid_fin))
            .replace("{{account_name}}", account_name_safe)
        )
        return self.ejecutar_sql(sql)

    _FILTROS_POR_ENVIAR = {
        "anuladas": "j.id_outbounds_statuses < 0",
        "pendientes": (
            "t1.id_documents_movements_types NOT IN (13,14,15)"
            " AND t1.id_documents_movements_statuses IN (1,2,3,4)"
        ),
        "ventas_nc": (
            "t1.id_documents_movements_types IN (9,10)"
            " AND t1.id_documents_movements_statuses IN (1,2,3,4)"
        ),
    }

    def ejecutar_por_enviar(
        self,
        cuid_inicio: int,
        cuid_fin: int,
        tipo: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        filtro = self._FILTROS_POR_ENVIAR.get(tipo)
        if filtro is None:
            raise ValueError(f"Tipo invalido para por_enviar: {tipo!r}")
        sql = (
            self._query_por_enviar
            .replace("{{cuid_inicio}}", str(cuid_inicio))
            .replace("{{cuid_fin}}", str(cuid_fin))
            .replace("{{filtro_adicional}}", filtro)
        )
        return self.ejecutar_sql(sql)

    def anular_movimiento_por_enviar(self, id_movement: int) -> int:
        # Marca el movimiento como anulado (estado 9) en MySQL.
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = pymysql.connect(
                    host=self._mysql_host,
                    user=self._mysql_user,
                    password=self._mysql_password,
                    database=self._mysql_name,
                    port=self._mysql_port,
                    connect_timeout=self._mysql_connect_timeout,
                    autocommit=True,
                )
                with conn.cursor() as cur:
                    cur.execute(self._query_anular_movimiento, (id_movement,))
                    return cur.rowcount if cur.rowcount is not None else 0
            except pymysql.MySQLError as exc:
                LOGGER.warning(
                    "Actualizar estado por_enviar fallo (intento %s/%s) id_movement %s: %s",
                    intento,
                    self._settings.reintentos,
                    id_movement,
                    exc,
                )
                if intento == self._settings.reintentos:
                    raise
                time.sleep(self._settings.espera_segundos)
            finally:
                if conn:
                    conn.close()

        raise RuntimeError("No se pudo actualizar el movimiento en MySQL tras todos los reintentos.")


def _render_in_list(values: list[str]) -> str:
    # Renderiza lista para IN ('a','b','c') con escape basico.
    safe = []
    for value in values:
        raw = str(value).replace("'", "''")
        safe.append(f"'{raw}'")
    return ", ".join(safe)
