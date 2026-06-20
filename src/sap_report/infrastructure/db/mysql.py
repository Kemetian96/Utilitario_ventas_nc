import logging
import time
from pathlib import Path
from typing import Any

try:
    import pymysql
except ImportError:
    pymysql = None

from sap_report.infrastructure.config import Settings

from ._base import _render_in_list


LOGGER = logging.getLogger(__name__)

_QUERIES_DIR = Path(__file__).resolve().parent / "queries" / "mysql"

VALIDAR_IGV_DOCUMENTOS_PATH = _QUERIES_DIR / "validar_igv_documentos.sql"
VALIDAR_IGV_ITEMS_PATH = _QUERIES_DIR / "validar_igv_items.sql"
PENDIENTES_ORDERS_PATH = _QUERIES_DIR / "pendientes_orders.sql"
PENDIENTES_RMAS_PATH = _QUERIES_DIR / "pendientes_rmas.sql"
VALIDAR_PAGOS_PATH = _QUERIES_DIR / "validar_pagos.sql"
POR_ENVIAR_PATH = _QUERIES_DIR / "por_enviar.sql"
ANULAR_MOVIMIENTO_PATH = _QUERIES_DIR / "anular_movimiento_por_enviar.sql"
ENVIAR_MOVIMIENTO_PATH = _QUERIES_DIR / "enviar_movimiento_por_enviar.sql"
VALIDAR_OUTBOUND_PATH = _QUERIES_DIR / "validar_outbound.sql"
VALIDAR_INBOUND_PATH = _QUERIES_DIR / "validar_inbound.sql"


class MySQLRepository:
    def __init__(self, settings: Settings) -> None:
        if pymysql is None:
            raise RuntimeError("Falta dependencia pymysql. Instala con: pip install pymysql")
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
        self._query_validar_igv_documentos = VALIDAR_IGV_DOCUMENTOS_PATH.read_text(encoding="utf-8")
        self._query_validar_igv_items = VALIDAR_IGV_ITEMS_PATH.read_text(encoding="utf-8")
        self._query_pendientes_orders = PENDIENTES_ORDERS_PATH.read_text(encoding="utf-8")
        self._query_pendientes_rmas = PENDIENTES_RMAS_PATH.read_text(encoding="utf-8")
        self._query_validar_pagos = VALIDAR_PAGOS_PATH.read_text(encoding="utf-8")
        self._query_por_enviar = POR_ENVIAR_PATH.read_text(encoding="utf-8")
        self._query_anular_movimiento = ANULAR_MOVIMIENTO_PATH.read_text(encoding="utf-8")
        self._query_enviar_movimiento = ENVIAR_MOVIMIENTO_PATH.read_text(encoding="utf-8")
        self._query_validar_outbound = VALIDAR_OUTBOUND_PATH.read_text(encoding="utf-8")
        self._query_validar_inbound = VALIDAR_INBOUND_PATH.read_text(encoding="utf-8")

    def probar_conexion(self) -> None:
        conn = self._connect()
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
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = self._connect()
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

    def consultar_items_outbound(
        self,
        ids: list[int],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not ids:
            return [], ["articulo", "centro", "cantidad"]
        ids_in = ", ".join(str(int(i)) for i in ids)
        sql = self._query_validar_outbound.replace("{{id_outbounds_in}}", ids_in)
        return self.ejecutar_sql(sql)

    def consultar_items_inbound(
        self,
        ids: list[int],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not ids:
            return [], ["articulo", "centro", "cantidad"]
        ids_in = ", ".join(str(int(i)) for i in ids)
        sql = self._query_validar_inbound.replace("{{id_inbounds_in}}", ids_in)
        return self.ejecutar_sql(sql)

    def consultar_eid_tienda(self, id_store: int) -> str | None:
        return self._consultar_campo_tienda("eid", id_store)

    def consultar_payments_account_tienda(self, id_store: int) -> str | None:
        return self._consultar_campo_tienda("payments_account", id_store)

    def ejecutar_validar_igv_docs(
        self,
        docentries: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not docentries:
            return [], ["id_document", "DocEntry"]
        doc_in = _render_in_list(docentries)
        sql = self._query_validar_igv_documentos.replace("{{docentries_in}}", doc_in)
        return self.ejecutar_sql(sql)

    def ejecutar_validar_igv_items(
        self,
        document_ids: list[str],
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        if not document_ids:
            return [], []
        doc_in = _render_in_list(document_ids)
        sql = self._query_validar_igv_items.replace("{{documents_in}}", doc_in)
        return self.ejecutar_sql(sql)

    def obtener_pendientes_venta_doble(
        self,
        cuid_inicio: int,
        cuid_fin: int,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        cols = ["Tipo", "UID", "Fecha"]
        rows: list[tuple[Any, ...]] = []
        for tipo, query in (
            ("ORDER", self._query_pendientes_orders),
            ("RMA", self._query_pendientes_rmas),
        ):
            sql = (
                query
                .replace("{{cuid_inicio}}", str(cuid_inicio))
                .replace("{{cuid_fin}}", str(cuid_fin))
            )
            pend_rows, _cols = self.ejecutar_sql(sql)
            for r in pend_rows:
                if not r or r[0] is None:
                    continue
                uid = str(r[0])
                fecha = r[1] if len(r) > 1 else None
                rows.append((tipo, uid, fecha))
        return rows, cols

    def ejecutar_sp_create_document_movement(self, uids: list[str], tipo: str) -> int:
        if not uids:
            return 0
        total_ok = 0
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = self._connect()
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
            "t1.id_documents_movements_types NOT IN (13,14,15,9,10)"
            " AND t1.id_documents_movements_statuses IN (1,2,3,4)"
            " AND (j.id_outbounds_statuses > 11 OR k.id_inbounds_statuses > 6)"
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

    def enviar_movimiento_por_enviar(self, id_movement: int) -> str:
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = self._connect(autocommit=True)
                with conn.cursor() as cur:
                    cur.execute(self._query_enviar_movimiento, (id_movement,))
                    row = cur.fetchone()
                    if row:
                        return str(row[0])
                    return ""
            except pymysql.MySQLError as exc:
                LOGGER.warning(
                    "SP sp_set_send_documents_movements_items fallo (intento %s/%s) id_movement %s: %s",
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

        raise RuntimeError("No se pudo enviar el movimiento en MySQL tras todos los reintentos.")

    def anular_movimiento_por_enviar(self, id_movement: int) -> int:
        for intento in range(1, self._settings.reintentos + 1):
            conn = None
            try:
                conn = self._connect(autocommit=True)
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

    def _connect(self, *, autocommit: bool = False):
        return pymysql.connect(
            host=self._mysql_host,
            user=self._mysql_user,
            password=self._mysql_password,
            database=self._mysql_name,
            port=self._mysql_port,
            connect_timeout=self._mysql_connect_timeout,
            autocommit=autocommit,
        )

    def _consultar_campo_tienda(self, campo: str, id_store: int) -> str | None:
        rows, _ = self.ejecutar_sql(
            f"SELECT {campo} FROM main.t_stores WHERE id_stores = %s",
            (id_store,),
        )
        if rows and rows[0][0] is not None:
            return str(rows[0][0])
        return None

