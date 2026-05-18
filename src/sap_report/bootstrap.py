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
        mysql_repository=mysql_repository,
        sl_repository=sl_repository,
        mailer=mailer,
        sap_output_path=settings.sap_output_path,
        postgres_output_path=settings.pg_output_path,
        comparacion_output_path=settings.comparacion_output_path,
    )
    return settings, service
