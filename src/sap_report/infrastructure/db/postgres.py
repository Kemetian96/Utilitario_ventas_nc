import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg2

from sap_report.domain import fecha_a_cuid
from sap_report.infrastructure.config import Settings


LOGGER = logging.getLogger(__name__)

_QUERIES_DIR = Path(__file__).resolve().parent / "queries" / "postgres"

REPORTE_VENTAS_PATH = _QUERIES_DIR / "reporte_ventas.sql"
REPORTE_NOTAS_CREDITO_PATH = _QUERIES_DIR / "reporte_notas_credito.sql"
MIGRAR_OC_PATH = _QUERIES_DIR / "migrar_oc.sql"
DATOS_PAGO_PATH = _QUERIES_DIR / "datos_pago.sql"
DATOS_RMA_PATH = _QUERIES_DIR / "datos_rma.sql"


class PostgresRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._query_reporte_ventas = REPORTE_VENTAS_PATH.read_text(encoding="utf-8")
        self._query_reporte_notas_credito = REPORTE_NOTAS_CREDITO_PATH.read_text(encoding="utf-8")
        self._query_migrar_oc = MIGRAR_OC_PATH.read_text(encoding="utf-8")
        self._query_datos_pago = DATOS_PAGO_PATH.read_text(encoding="utf-8")
        self._query_datos_rma = DATOS_RMA_PATH.read_text(encoding="utf-8")

    def ejecutar_consulta_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql(self._query_reporte_ventas, fecha_inicio, fecha_fin)

    def ejecutar_consulta_nc_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql(self._query_reporte_notas_credito, fecha_inicio, fecha_fin)

    def consultar_datos_pago(self, orden: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._consultar_por_orden(self._query_datos_pago, orden)

    def consultar_datos_rma(self, orden: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._consultar_por_orden(self._query_datos_rma, orden)

    def ejecutar_migrar_oc(self, fecha: date) -> None:
        sql = self._query_migrar_oc.replace("{{fecha}}", fecha.strftime("%Y-%m-%d"))
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = self._connect()
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

    def probar_conexion(self) -> None:
        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
            conn.close()

    def _connect(self, *, keepalives: bool = False):
        kwargs: dict[str, Any] = {
            "host": self._settings.pg_host,
            "dbname": self._settings.pg_name,
            "user": self._settings.pg_user,
            "password": self._settings.pg_password,
            "port": self._settings.pg_port,
            "sslmode": self._settings.pg_sslmode,
            "connect_timeout": self._settings.pg_connect_timeout,
        }
        if keepalives:
            kwargs.update(
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
            )
        return psycopg2.connect(**kwargs)

    def _consultar_por_orden(
        self,
        query: str,
        orden: str,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        conn = None
        cur = None
        try:
            conn = self._connect(keepalives=True)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(query, {"orden": orden})
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
            return rows, cols
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    def _ejecutar_sql(
        self,
        query: str,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())
        params = {
            "fecha1": fecha_a_cuid(inicio_dt),
            "fecha2": fecha_a_cuid(fin_dt),
        }

        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            cur = None
            try:
                conn = self._connect(keepalives=True)
                conn.autocommit = True
                cur = conn.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                if cur.description is None:
                    raise RuntimeError("La consulta PostgreSQL no devolvio metadatos de columnas.")
                cols = [c[0] for c in cur.description]
                return rows, cols
            except psycopg2.OperationalError as exc:
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
