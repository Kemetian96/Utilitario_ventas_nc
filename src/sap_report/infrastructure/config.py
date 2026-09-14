import os
from datetime import date, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"


def _get_env(name: str, default: str | None = None) -> str:
    # Lee variable obligatoria; falla si no existe.
    value = os.getenv(name, default)
    if value is None or value == "":
        raise ValueError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def _get_env_alias(primary: str, aliases: list[str], default: str | None = None) -> str:
    # Permite compatibilidad entre nombres nuevos y legacy.
    value = os.getenv(primary)
    if value:
        return value
    for alias in aliases:
        alias_value = os.getenv(alias)
        if alias_value:
            return alias_value
    if default is not None:
        return default
    raise ValueError(f"Falta la variable de entorno obligatoria: {primary}")


def _get_optional_bool(name: str) -> Optional[bool]:
    # Lee bool opcional: true/false.
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower() == "true"


def _get_optional_int(name: str) -> Optional[int]:
    # Lee entero opcional.
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return int(raw.strip())


def _get_optional_env(name: str) -> Optional[str]:
    # Lee string opcional.
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip()


@dataclass(frozen=True)
class Settings:
    # PostgreSQL
    pg_host: str
    pg_name: str
    pg_user: str
    pg_password: str
    pg_port: int
    pg_sslmode: str
    pg_connect_timeout: int
    # PostgreSQL Chile (opcional)
    pg_host_chile: Optional[str]
    pg_name_chile: Optional[str]
    pg_user_chile: Optional[str]
    pg_password_chile: Optional[str]
    pg_port_chile: Optional[int]
    pg_sslmode_chile: Optional[str]
    pg_connect_timeout_chile: Optional[int]
    # SAP HANA
    sap_hana_host: str
    sap_hana_port: int
    sap_hana_user: str
    sap_hana_password: str
    sap_hana_encrypt: Optional[bool]
    sap_hana_ssl_validate_certificate: Optional[bool]
    sap_hana_ssl_trust_store: Optional[str]
    sap_hana_ssl_key_store_password: Optional[str]
    sap_hana_connect_timeout: Optional[int]
    sap_hana_communication_timeout_ms: int
    # MySQL (opcional)
    mysql_host: Optional[str]
    mysql_name: Optional[str]
    mysql_user: Optional[str]
    mysql_password: Optional[str]
    mysql_port: Optional[int]
    mysql_connect_timeout: Optional[int]
    # Mattermost: el alta de usuarios es un script en un Linux, por SSH
    mattermost_ssh_host: Optional[str]
    mattermost_ssh_port: int
    mattermost_ssh_user: Optional[str]
    mattermost_ssh_password: Optional[str]
    mattermost_sudo_password: Optional[str]
    mattermost_dir: str
    mattermost_script: str
    mattermost_timeout: int
    # Salidas
    sap_output_path: Path
    pg_output_path: Path
    comparacion_output_path: Path
    # Base local (SQLite) con datos propios de la app
    local_db_path: Path
    # SAP Service Layer
    sl_url: str
    sl_company_db: str
    sl_user: str
    sl_password: str
    # Correo SMTP
    smtp_host: str
    smtp_port: int
    smtp_user: Optional[str]
    smtp_password: Optional[str]
    smtp_from: Optional[str]
    smtp_override_to: Optional[str]
    # Parametros generales
    reintentos: int
    espera_segundos: int
    ui_width: int
    ui_height: int
    fecha_inicio_default: str
    fecha_fin_default: str


def load_settings() -> Settings:
    # Carga .env del proyecto.
    load_dotenv(ENV_PATH)

    # Construye objeto de configuracion tipado.
    return Settings(
        pg_host=_get_env_alias("PG_HOST", ["DB_HOST"]),
        pg_name=_get_env_alias("PG_NAME", ["DB_NAME"], "main"),
        pg_user=_get_env_alias("PG_USER", ["DB_USER"]),
        pg_password=_get_env_alias("PG_PASSWORD", ["DB_PASSWORD"]),
        pg_port=int(_get_env_alias("PG_PORT", ["DB_PORT"], "5432")),
        pg_sslmode=_get_env_alias("PG_SSLMODE", ["DB_SSLMODE"], "require"),
        pg_connect_timeout=int(_get_env_alias("PG_CONNECT_TIMEOUT", ["DB_CONNECT_TIMEOUT"], "10")),
        pg_host_chile=_get_optional_env("PG_HOST_CHILE"),
        pg_name_chile=_get_optional_env("PG_NAME_CHILE"),
        pg_user_chile=_get_optional_env("PG_USER_CHILE"),
        pg_password_chile=_get_optional_env("PG_PASSWORD_CHILE"),
        pg_port_chile=_get_optional_int("PG_PORT_CHILE"),
        pg_sslmode_chile=_get_optional_env("PG_SSLMODE_CHILE"),
        pg_connect_timeout_chile=_get_optional_int("PG_CONNECT_TIMEOUT_CHILE"),
        sap_hana_host=_get_env("SAP_HANA_HOST", "172.31.28.162"),
        sap_hana_port=int(_get_env("SAP_HANA_PORT", "30015")),
        sap_hana_user=_get_env("SAP_HANA_USER"),
        sap_hana_password=_get_env("SAP_HANA_PASSWORD"),
        sap_hana_encrypt=_get_optional_bool("SAP_HANA_ENCRYPT"),
        sap_hana_ssl_validate_certificate=_get_optional_bool("SAP_HANA_SSL_VALIDATE_CERTIFICATE"),
        sap_hana_ssl_trust_store=os.getenv("SAP_HANA_SSL_TRUST_STORE"),
        sap_hana_ssl_key_store_password=os.getenv("SAP_HANA_SSL_KEY_STORE_PASSWORD"),
        sap_hana_connect_timeout=_get_optional_int("SAP_HANA_CONNECT_TIMEOUT"),
        sap_hana_communication_timeout_ms=int(
            _get_env("SAP_HANA_COMMUNICATION_TIMEOUT_MS", "180000")
        ),
        mysql_host=_get_optional_env("MYSQL_HOST"),
        mysql_name=_get_optional_env("MYSQL_NAME"),
        mysql_user=_get_optional_env("MYSQL_USER"),
        mysql_password=_get_optional_env("MYSQL_PASSWORD"),
        mysql_port=_get_optional_int("MYSQL_PORT"),
        mysql_connect_timeout=_get_optional_int("MYSQL_CONNECT_TIMEOUT"),
        mattermost_ssh_host=_get_optional_env("MATTERMOST_SSH_HOST"),
        mattermost_ssh_port=_get_optional_int("MATTERMOST_SSH_PORT") or 22,
        mattermost_ssh_user=_get_optional_env("MATTERMOST_SSH_USER"),
        mattermost_ssh_password=_get_optional_env("MATTERMOST_SSH_PASSWORD"),
        # Vacia = sudo usa la misma clave con la que se entro por SSH, que es
        # lo normal cuando la cuenta de servicio es la del propio operador.
        mattermost_sudo_password=_get_optional_env("MATTERMOST_SUDO_PASSWORD"),
        mattermost_dir=_get_optional_env("MATTERMOST_DIR") or "mattermost",
        mattermost_script=_get_optional_env("MATTERMOST_SCRIPT") or "./crear_usuario_individual.sh",
        mattermost_timeout=_get_optional_int("MATTERMOST_TIMEOUT") or 180,
        sap_output_path=Path(_get_env("SAP_OUTPUT_PATH", str(Path("OUTPUT") / "SAP.xlsx"))),
        pg_output_path=Path(_get_env("PG_OUTPUT_PATH", str(Path("OUTPUT") / "TUTATI.xlsx"))),
        comparacion_output_path=Path(_get_env("COMPARACION_OUTPUT_PATH", str(Path("OUTPUT") / "COMPARACION.xlsx"))),
        # Absoluta por defecto: la base local no debe depender del directorio
        # desde el que se lanza la app. Vacia en el .env = usa el default.
        local_db_path=Path(_get_optional_env("LOCAL_DB_PATH") or (ROOT_DIR / "data" / "local.db")),
        sl_url=_get_env("SL_URL", "https://54.210.79.151:50000/b1s/v1"),
        sl_company_db=_get_env("SL_COMPANY_DB", "B1H_COMERCIALMONT_PROD"),
        sl_user=_get_env("SL_USER", ""),
        sl_password=_get_env("SL_PASSWORD", ""),
        smtp_host=_get_env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(_get_env("SMTP_PORT", "587")),
        smtp_user=_get_optional_env("SMTP_USER"),
        smtp_password=_get_optional_env("SMTP_PASSWORD"),
        smtp_from=_get_optional_env("SMTP_FROM"),
        smtp_override_to=_get_optional_env("SMTP_OVERRIDE_TO"),
        reintentos=int(_get_env("REINTENTOS_CONEXION", "5")),
        espera_segundos=int(_get_env("ESPERA_REINTENTO_SEGUNDOS", "10")),
        ui_width=int(_get_env("UI_WIDTH", "360")),
        ui_height=int(_get_env("UI_HEIGHT", "260")),
        fecha_inicio_default=_get_env("FECHA_INICIO", (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")),
        fecha_fin_default=_get_env("FECHA_FIN", (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")),
    )
