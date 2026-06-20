import logging
import time
from contextlib import contextmanager
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
ORDEN_PAGO_PATH = _QUERIES_DIR / "orden_pago.sql"


class PostgresRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._query_reporte_ventas = REPORTE_VENTAS_PATH.read_text(encoding="utf-8")
        self._query_reporte_notas_credito = REPORTE_NOTAS_CREDITO_PATH.read_text(encoding="utf-8")
        self._query_migrar_oc = MIGRAR_OC_PATH.read_text(encoding="utf-8")
        self._query_datos_pago = DATOS_PAGO_PATH.read_text(encoding="utf-8")
        self._query_datos_rma = DATOS_RMA_PATH.read_text(encoding="utf-8")
        self._query_orden_pago = ORDEN_PAGO_PATH.read_text(encoding="utf-8")
        # Conexion persistente opcional. Cuando _sesion_activa es True, las
        # queries reusan self._conn en lugar de abrir/cerrar una nueva cada vez.
        # Si la conexion muere, se reabre automaticamente dentro de la sesion.
        self._conn = None
        self._sesion_activa = False

    @contextmanager
    def sesion(self):
        """Mantiene una conexion viva mientras dure el bloque. Si la conexion
        muere durante una query, se descarta y se reabre transparentemente.
        """
        self._sesion_activa = True
        try:
            yield
        finally:
            self._sesion_activa = False
            conn = self._conn
            self._conn = None
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _obtener_conn_para_query(self) -> tuple[Any, bool]:
        """Devuelve (conn, es_persistente). Reabre la persistente si murio."""
        if self._sesion_activa:
            if self._conn is None:
                self._conn = self._connect(keepalives=True)
                self._conn.autocommit = True
                cur = self._conn.cursor()
                try:
                    cur.execute("SET statement_timeout = 0")
                finally:
                    cur.close()
            return self._conn, True
        # Sin sesion: conexion temporal
        conn = self._connect(keepalives=True)
        conn.autocommit = True
        cur = conn.cursor()
        try:
            cur.execute("SET statement_timeout = 0")
        finally:
            cur.close()
        return conn, False

    def ejecutar_consulta_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())
        return self.ejecutar_consulta_sql_rango(inicio_dt, fin_dt)

    def ejecutar_consulta_nc_sql(
        self,
        fecha_inicio: date,
        fecha_fin: date,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
        fin_dt = datetime.combine(fecha_fin + timedelta(days=1), datetime.min.time())
        return self.ejecutar_consulta_nc_sql_rango(inicio_dt, fin_dt)

    def ejecutar_consulta_sql_rango(
        self,
        inicio_dt: datetime,
        fin_dt: datetime,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql_datetime(self._query_reporte_ventas, inicio_dt, fin_dt)

    def ejecutar_consulta_nc_sql_rango(
        self,
        inicio_dt: datetime,
        fin_dt: datetime,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._ejecutar_sql_datetime(self._query_reporte_notas_credito, inicio_dt, fin_dt)

    def consultar_datos_pago(self, orden: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._consultar_por_orden(self._query_datos_pago, orden)

    def consultar_datos_rma(self, orden: str) -> tuple[list[tuple[Any, ...]], list[str]]:
        return self._consultar_por_orden(self._query_datos_rma, orden)

    def consultar_orden_pago(
        self,
        uids: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not uids:
            return [], ["uid_orders", "order_payment_type"]
        placeholders = ", ".join(["%s"] * len(uids))
        query = self._query_orden_pago.replace("{{uids}}", placeholders)
        conn = None
        cur = None
        try:
            conn = self._connect(keepalives=True)
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SET statement_timeout = 0")
            cur.execute(query, tuple(uids))
            rows = cur.fetchall()
            cols = [c[0] for c in cur.description] if cur.description else []
            return rows, cols
        finally:
            if cur:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

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

    def _ejecutar_sql_datetime(
        self,
        query: str,
        inicio_dt: datetime,
        fin_dt: datetime,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        params = {
            "fecha1": fecha_a_cuid(inicio_dt),
            "fecha2": fecha_a_cuid(fin_dt),
        }

        # El killer del servidor es ciclico (~2-3s). 1s de sleep entre intentos
        # cae entre ciclos. Si hay sesion() abierta se reusa la conexion;
        # solo se abre una nueva cuando esta muere.
        max_intentos = max(self._settings.reintentos, 10)
        for intento in range(1, max_intentos + 1):
            conn = None
            cur = None
            try:
                conn, _ = self._obtener_conn_para_query()
                cur = conn.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                if cur.description is None:
                    raise RuntimeError("La consulta PostgreSQL no devolvio metadatos de columnas.")
                cols = [c[0] for c in cur.description]
                return rows, cols
            except psycopg2.OperationalError as exc:
                # La conexion murio; descartar la persistente para que la
                # proxima iteracion abra una nueva (dentro de la misma sesion).
                if conn is not None and conn is self._conn:
                    self._conn = None
                LOGGER.warning(
                    "Conexion PostgreSQL caida (intento %s/%s): %s",
                    intento,
                    max_intentos,
                    exc,
                )
                if intento == max_intentos:
                    raise
                time.sleep(1.0)
            finally:
                if cur:
                    try:
                        cur.close()
                    except Exception:
                        pass
                # Cerrar conn solo si NO es la persistente vigente
                if conn is not None and conn is not self._conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

        raise RuntimeError("No se pudo ejecutar la consulta PostgreSQL tras todos los reintentos.")
