"""El trato con sudo es lo unico que no se puede ver desde la pantalla: se
prueba con un canal falso que responde como el servidor real."""
import pytest

from sap_report.infrastructure.remote.mattermost_ssh import MattermostSshRepository


class _CanalFalso:
    """Imita el canal de paramiko: entrega la salida por trozos y solo sigue
    despues de recibir la clave de sudo."""

    def __init__(self, guion: list[str], espera_clave_en: int) -> None:
        self._guion = guion
        self._espera = espera_clave_en
        self._i = 0
        self._bloqueado = False
        self.recibido: list[str] = []

    def get_pty(self): pass
    def settimeout(self, _v): pass
    def exec_command(self, _c): pass

    def recv_ready(self) -> bool:
        return not self._bloqueado and self._i < len(self._guion)

    def recv(self, _n: int) -> bytes:
        trozo = self._guion[self._i]
        self._i += 1
        if self._i == self._espera:
            self._bloqueado = True
        return trozo.encode("utf-8")

    def send(self, datos: str) -> None:
        self.recibido.append(datos)
        self._bloqueado = False

    def exit_status_ready(self) -> bool:
        return not self._bloqueado and self._i >= len(self._guion)

    def recv_exit_status(self) -> int:
        return 0

    def close(self): pass


class _ClienteFalso:
    def __init__(self, canal): self._canal = canal
    def get_transport(self): return self
    def open_session(self): return self._canal


def _repo() -> MattermostSshRepository:
    repo = MattermostSshRepository.__new__(MattermostSshRepository)
    repo._sudo_password = "clave-secreta"
    repo._timeout = 5
    repo._dir = "mattermost"
    repo._script = "./crear_usuario_individual.sh"
    return repo


def test_responde_al_prompt_de_sudo() -> None:
    canal = _CanalFalso(
        ["Creando usuario...\n", "[sudo] password for kemet: ", "\nUsuario creado.\n"],
        espera_clave_en=2,
    )
    salida, codigo = _repo()._ejecutar_con_pty(_ClienteFalso(canal), "irrelevante")

    assert canal.recibido == ["clave-secreta\n"]
    assert codigo == 0
    assert "Usuario creado." in salida
    # Ni el prompt ni la clave deben quedar a la vista.
    assert "sudo" not in salida
    assert "clave-secreta" not in salida


def test_no_manda_clave_si_no_la_piden() -> None:
    canal = _CanalFalso(["Usuario creado sin sudo.\n"], espera_clave_en=99)
    salida, _ = _repo()._ejecutar_con_pty(_ClienteFalso(canal), "irrelevante")

    assert canal.recibido == []
    assert salida == "Usuario creado sin sudo."


def test_corta_si_el_script_se_queda_esperando() -> None:
    repo = _repo()
    repo._timeout = 1
    # Pide algo que no es una clave: nadie va a responder.
    canal = _CanalFalso(["Ingrese el area del usuario: "], espera_clave_en=1)
    with pytest.raises(TimeoutError):
        repo._ejecutar_con_pty(_ClienteFalso(canal), "irrelevante")
