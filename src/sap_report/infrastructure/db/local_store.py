"""
Base de datos local (SQLite) para datos propios de la app: informacion que no
vive en TUTATI ni en SAP y que debe sobrevivir a los refrescos y al paso del
tiempo.

Primer uso: la marca de seguimiento de tickets (semaforo). La clave es el
`uid_tickets`, asi que un ticket conserva su marca aunque salga y vuelva a la
consulta semanas despues.

El archivo se ubica en `LOCAL_DB_PATH` (por defecto `data/local.db` en la raiz
del proyecto). Cada operacion abre y cierra su conexion: es barato en SQLite y
evita compartir conexiones entre los hilos del servidor web.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)

# Estados del semaforo de tickets.
TICKET_NO_ENVIADO = "no_enviado"  # rojo
TICKET_ENVIADO = "enviado"        # amarillo
TICKET_DEVUELTO = "devuelto"      # verde
TICKET_VALIDAR = "validar"        # blanco
TICKET_NO_APLICA = "no_aplica"    # negro

TICKET_ESTADOS = (
    TICKET_NO_ENVIADO,
    TICKET_ENVIADO,
    TICKET_DEVUELTO,
    TICKET_VALIDAR,
    TICKET_NO_APLICA,
)

# Nombres anteriores -> actuales. Se aplica al abrir la base, una sola vez:
# las marcas ya puestas conservan su color.
_RENOMBRES = {
    "sin_enviar": TICKET_NO_ENVIADO,
    "enviado_mio": TICKET_ENVIADO,
    "enviado_ellos": TICKET_DEVUELTO,
    "en_observacion": TICKET_VALIDAR,
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets_marcas (
    uid_tickets TEXT PRIMARY KEY,
    estado      TEXT NOT NULL,
    nota        TEXT,
    usuario     TEXT,
    actualizado TEXT NOT NULL
);
"""


class LocalStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._inicializar()

    @property
    def path(self) -> Path:
        return self._db_path

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _inicializar(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conectar() as conn:
            # WAL: varios lectores concurrentes (el servidor web es multihilo)
            # sin bloquear al que escribe.
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(_SCHEMA)
            for viejo, nuevo in _RENOMBRES.items():
                conn.execute(
                    "UPDATE tickets_marcas SET estado = ? WHERE estado = ?",
                    (nuevo, viejo),
                )

    # -- Marcas de tickets -------------------------------------------------

    def marcas_tickets(self, uids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Marcas indexadas por uid_tickets. Sin `uids` devuelve todas."""
        with self._conectar() as conn:
            if uids is None:
                filas = conn.execute("SELECT * FROM tickets_marcas").fetchall()
            elif not uids:
                return {}
            else:
                marcadores = ",".join("?" for _ in uids)
                filas = conn.execute(
                    f"SELECT * FROM tickets_marcas WHERE uid_tickets IN ({marcadores})",
                    [str(u) for u in uids],
                ).fetchall()
        return {fila["uid_tickets"]: dict(fila) for fila in filas}

    def guardar_marca_ticket(
        self,
        uid_tickets: str,
        estado: str,
        usuario: str | None = None,
        nota: str | None = None,
    ) -> dict[str, Any]:
        uid = str(uid_tickets).strip()
        if not uid:
            raise ValueError("uid_tickets vacio.")
        if estado not in TICKET_ESTADOS:
            raise ValueError(f"Estado invalido: {estado}")

        actualizado = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO tickets_marcas (uid_tickets, estado, nota, usuario, actualizado)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(uid_tickets) DO UPDATE SET
                    estado      = excluded.estado,
                    nota        = excluded.nota,
                    usuario     = excluded.usuario,
                    actualizado = excluded.actualizado
                """,
                (uid, estado, nota, usuario, actualizado),
            )
        return {
            "uid_tickets": uid,
            "estado": estado,
            "nota": nota,
            "usuario": usuario,
            "actualizado": actualizado,
        }
