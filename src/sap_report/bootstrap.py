import os

from sap_report.application import ReportService
from sap_report.infrastructure import Settings, get_missing_env_fields, load_settings
from sap_report.infrastructure.db import MySQLRepository, PostgresRepository, SapHanaRepository, SapServiceLayerRepository
from sap_report.logging_config import configure_logging
from sap_report.ui import prompt_env_vars


def build_service() -> tuple[Settings, ReportService]:
    # Inicializa logging y completa credenciales faltantes.
    configure_logging()
    missing_fields = get_missing_env_fields()
    if missing_fields:
        values = prompt_env_vars(missing_fields)
        for key, value in values.items():
            os.environ[key] = value

    settings = load_settings()
    sap_repository = SapHanaRepository(settings)
    postgres_repository = PostgresRepository(settings)
    mysql_repository = MySQLRepository(settings)
    sl_repository = SapServiceLayerRepository(
        url=settings.sl_url,
        company_db=settings.sl_company_db,
        user=settings.sl_user,
        password=settings.sl_password,
    )
    service = ReportService(
        sap_repository=sap_repository,
        postgres_repository=postgres_repository,
        mysql_repository=mysql_repository,
        sl_repository=sl_repository,
        sap_output_path=settings.sap_output_path,
        postgres_output_path=settings.pg_output_path,
        comparacion_output_path=settings.comparacion_output_path,
    )
    return settings, service
