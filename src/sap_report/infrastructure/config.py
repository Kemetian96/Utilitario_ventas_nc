import os
from datetime import date, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, dotenv_values


ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"

ENV_PROMPT_FIELDS = [
    {
        "keys": ["DB_HOST", "PG_HOST"],
        "label": "DB_HOST (PostgreSQL)",
        "secret": False,
    },
    {
        "keys": ["DB_NAME", "PG_NAME"],
        "label": "DB_NAME (PostgreSQL)",
        "secret": False,
    },
    {
        "keys": ["DB_USER", "PG_USER"],
        "label": "DB_USER (PostgreSQL)",
        "secret": False,
    },
    {
        "keys": ["DB_PASSWORD", "PG_PASSWORD"],
        "label": "DB_PASSWORD (PostgreSQL)",
        "secret": True,
    },
    {
        "keys": ["SAP_HANA_HOST"],
        "label": "SAP_HANA_HOST",
        "secret": False,
    },
    {
        "keys": ["SAP_HANA_USER"],
        "label": "SAP_HANA_USER",
        "secret": False,
    },
    {
        "keys": ["SAP_HANA_PASSWORD"],
        "label": "SAP_HANA_PASSWORD",
        "secret": True,
    },
    {
        "keys": ["MYSQL_HOST"],
        "label": "MYSQL_HOST",
        "secret": False,
    },
    {
        "keys": ["MYSQL_NAME"],
        "label": "MYSQL_NAME",
        "secret": False,
    },
    {
        "keys": ["MYSQL_USER"],
        "label": "MYSQL_USER",
        "secret": False,
    },
    {
        "keys": ["MYSQL_PASSWORD"],
        "label": "MYSQL_PASSWORD",
        "secret": True,
    },
]


def _is_placeholder(value: str) -> bool:
    # Detecta valores tipo "????".
    stripped = value.strip()
    return bool(stripped) and all(ch == "?" for ch in stripped)


def get_missing_env_fields() -> list[dict[str, object]]:
    # Devuelve campos a solicitar si faltan o son placeholders.
    env_file = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    missing: list[dict[str, object]] = []
    for field in ENV_PROMPT_FIELDS:
        keys = field["keys"]
        value = None
        for key in keys:
            if os.getenv(key):
                value = os.getenv(key)
                break
            if key in env_file and env_file[key] is not None:
                value = env_file[key]
                break
        if value is None or _is_placeholder(str(value)):
            missing.append(
                {
                    "key": keys[0],
                    "label": field["label"],
                    "secret": field["secret"],
                }
            )
    return missing


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
    # MySQL (opcional)
    mysql_host: Optional[str]
    mysql_name: Optional[str]
    mysql_user: Optional[str]
    mysql_password: Optional[str]
    mysql_port: Optional[int]
    mysql_connect_timeout: Optional[int]
    # Salidas
    sap_output_path: Path
    pg_output_path: Path
    comparacion_output_path: Path
    # SAP Service Layer
    sl_url: str
    sl_company_db: str
    sl_user: str
    sl_password: str
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
        sap_hana_host=_get_env("SAP_HANA_HOST", "172.31.28.162"),
        sap_hana_port=int(_get_env("SAP_HANA_PORT", "30015")),
        sap_hana_user=_get_env("SAP_HANA_USER"),
        sap_hana_password=_get_env("SAP_HANA_PASSWORD"),
        sap_hana_encrypt=_get_optional_bool("SAP_HANA_ENCRYPT"),
        sap_hana_ssl_validate_certificate=_get_optional_bool("SAP_HANA_SSL_VALIDATE_CERTIFICATE"),
        sap_hana_ssl_trust_store=os.getenv("SAP_HANA_SSL_TRUST_STORE"),
        sap_hana_ssl_key_store_password=os.getenv("SAP_HANA_SSL_KEY_STORE_PASSWORD"),
        sap_hana_connect_timeout=_get_optional_int("SAP_HANA_CONNECT_TIMEOUT"),
        mysql_host=_get_optional_env("MYSQL_HOST"),
        mysql_name=_get_optional_env("MYSQL_NAME"),
        mysql_user=_get_optional_env("MYSQL_USER"),
        mysql_password=_get_optional_env("MYSQL_PASSWORD"),
        mysql_port=_get_optional_int("MYSQL_PORT"),
        mysql_connect_timeout=_get_optional_int("MYSQL_CONNECT_TIMEOUT"),
        sap_output_path=Path(_get_env("SAP_OUTPUT_PATH", str(Path("OUTPUT") / "SAP.xlsx"))),
        pg_output_path=Path(_get_env("PG_OUTPUT_PATH", str(Path("OUTPUT") / "TUTATI.xlsx"))),
        comparacion_output_path=Path(_get_env("COMPARACION_OUTPUT_PATH", str(Path("OUTPUT") / "COMPARACION.xlsx"))),
        sl_url=_get_env("SL_URL", "https://54.210.79.151:50000/b1s/v1"),
        sl_company_db=_get_env("SL_COMPANY_DB", "B1H_COMERCIALMONT_PROD"),
        sl_user=_get_env("SL_USER", ""),
        sl_password=_get_env("SL_PASSWORD", ""),
        reintentos=int(_get_env("REINTENTOS_CONEXION", "5")),
        espera_segundos=int(_get_env("ESPERA_REINTENTO_SEGUNDOS", "10")),
        ui_width=int(_get_env("UI_WIDTH", "360")),
        ui_height=int(_get_env("UI_HEIGHT", "260")),
        fecha_inicio_default=_get_env("FECHA_INICIO", (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")),
        fecha_fin_default=_get_env("FECHA_FIN", (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")),
    )
