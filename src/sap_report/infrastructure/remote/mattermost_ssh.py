import logging
import re
import shlex
import time
from typing import Any

try:
    import paramiko
except ImportError:
    paramiko = None

from sap_report.infrastructure.config import Settings


LOGGER = logging.getLogger(__name__)

# El script llama a sudo por dentro. Sin terminal sudo no puede preguntar
# nada y falla con "no tty present", asi que se abre un pty y se le responde
# la clave igual que se hace a mano en PuTTY.
_PROMPT_CLAVE = re.compile(
    r"(?:\[sudo\][^\n]*|[^\n]*(?:assword|ontrase\w*a)[^\n]*):[ \t]*$",
    re.IGNORECASE,
)
# sudo vuelve a preguntar si la clave no entra. Con dos intentos basta; mas
# solo sirve para bloquear la cuenta.
_MAX_ENVIOS_CLAVE = 2
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")


class MattermostSshRepository:
    """Ejecuta los scripts de administracion de Mattermost por SSH."""

    def __init__(self, settings: Settings) -> None:
        if paramiko is None:
            raise RuntimeError("Falta dependencia paramiko. Instala con: pip install paramiko")
        if not settings.mattermost_ssh_host:
            raise ValueError("Falta MATTERMOST_SSH_HOST en .env")
        if not settings.mattermost_ssh_user:
            raise ValueError("Falta MATTERMOST_SSH_USER en .env")
        if not settings.mattermost_ssh_password:
            raise ValueError("Falta MATTERMOST_SSH_PASSWORD en .env")
        self._host = settings.mattermost_ssh_host
        self._port = settings.mattermost_ssh_port
        self._user = settings.mattermost_ssh_user
        self._password = settings.mattermost_ssh_password
        self._sudo_password = settings.mattermost_sudo_password or settings.mattermost_ssh_password
        self._dir = settings.mattermost_dir
        self._script = settings.mattermost_script
        self._timeout = settings.mattermost_timeout

    def crear_usuario(self, nombre: str, documento: str) -> dict[str, Any]:
        comando = (
            f"cd {shlex.quote(self._dir)} && "
            f"{shlex.quote(self._script)} {shlex.quote(nombre)} {shlex.quote(documento)}"
        )
        return self.ejecutar(comando)

    def probar_conexion(self) -> None:
        resultado = self.ejecutar("echo conexion-ok")
        if not resultado["ok"]:
            raise RuntimeError(resultado["salida"] or "El servidor no respondio")

    def ejecutar(self, comando: str) -> dict[str, Any]:
        LOGGER.info("SSH %s@%s: %s", self._user, self._host, comando)
        cliente = paramiko.SSHClient()
        cliente.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            cliente.connect(
                hostname=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                timeout=20,
                # La cuenta es de usuario y clave: sin esto paramiko prueba
                # primero las llaves del equipo y puede agotar los intentos.
                allow_agent=False,
                look_for_keys=False,
            )
            salida, codigo = self._ejecutar_con_pty(cliente, comando)
        finally:
            cliente.close()

        LOGGER.info("SSH termino con codigo %s", codigo)
        return {"ok": codigo == 0, "codigo": codigo, "salida": salida, "comando": comando}

    def _ejecutar_con_pty(self, cliente, comando: str) -> tuple[str, int]:
        canal = cliente.get_transport().open_session()
        canal.get_pty()
        canal.settimeout(1.0)
        canal.exec_command(comando)

        partes: list[str] = []
        cola = ""
        enviados = 0
        inicio = time.time()
        while True:
            if canal.recv_ready():
                trozo = canal.recv(65536).decode("utf-8", "replace")
                partes.append(trozo)
                # Solo importa el final: el prompt de sudo no trae salto de
                # linea, se queda esperando al final de lo recibido.
                cola = (cola + trozo)[-400:]
                if enviados < _MAX_ENVIOS_CLAVE and _PROMPT_CLAVE.search(cola):
                    canal.send(self._sudo_password + "\n")
                    enviados += 1
                    cola = ""
                continue
            if canal.exit_status_ready():
                while canal.recv_ready():
                    partes.append(canal.recv(65536).decode("utf-8", "replace"))
                break
            if time.time() - inicio > self._timeout:
                canal.close()
                raise TimeoutError(
                    f"El script no termino en {self._timeout}s. Puede haber quedado "
                    "esperando un dato que la pantalla no pide."
                )
            time.sleep(0.1)

        return self._limpiar("".join(partes)), canal.recv_exit_status()

    def _limpiar(self, salida: str) -> str:
        """Quita colores, el prompt de sudo y cualquier eco de la clave."""
        texto = _ANSI.sub("", salida)
        lineas = [l for l in texto.split("\n") if not _PROMPT_CLAVE.search(l + "")]
        limpio = "\n".join(lineas)
        if self._sudo_password:
            limpio = limpio.replace(self._sudo_password, "***")
        return limpio.strip()
