import dataclasses

from sap_report.application import ReportService
from sap_report.infrastructure import Settings, load_settings
from sap_report.infrastructure.db import MySQLRepository, PostgresRepository, SapHanaRepository, SapServiceLayerRepository
from sap_report.infrastructure.email import SmtpMailer
from sap_report.logging_config import configure_logging


def build_service() -> tuple[Settings, ReportService]:
    configure_logging()
    settings = load_settings()
    sap_repository = SapHanaRepository(settings)
    postgres_repository = PostgresRepository(settings)
    # Postgres Chile: solo si hay credenciales configuradas. Reusa la misma
    # clase apuntando pg_* a las variables *_CHILE.
    postgres_chile_repository = None
    if settings.pg_host_chile:
        settings_chile = dataclasses.replace(
            settings,
            pg_host=settings.pg_host_chile,
            pg_name=settings.pg_name_chile or "main",
            pg_user=settings.pg_user_chile,
            pg_password=settings.pg_password_chile,
            pg_port=settings.pg_port_chile or 5432,
            pg_sslmode=settings.pg_sslmode_chile or "require",
            pg_connect_timeout=settings.pg_connect_timeout_chile or 10,
        )
        postgres_chile_repository = PostgresRepository(settings_chile)
    mysql_repository = MySQLRepository(settings)
    sl_repository = SapServiceLayerRepository(
        url=settings.sl_url,
        company_db=settings.sl_company_db,
        user=settings.sl_user,
        password=settings.sl_password,
    )
    mailer = SmtpMailer(settings)
    service = ReportService(
        sap_repository=sap_repository,
        postgres_repository=postgres_repository,
        postgres_chile_repository=postgres_chile_repository,
        mysql_repository=mysql_repository,
        sl_repository=sl_repository,
        mailer=mailer,
        sap_output_path=settings.sap_output_path,
        postgres_output_path=settings.pg_output_path,
        comparacion_output_path=settings.comparacion_output_path,
    )
    return settings, service
