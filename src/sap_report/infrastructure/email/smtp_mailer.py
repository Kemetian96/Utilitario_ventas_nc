import logging
import smtplib
from email.message import EmailMessage

from sap_report.infrastructure.config import Settings


LOGGER = logging.getLogger(__name__)


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        html: str | None = None,
    ) -> None:
        s = self._settings
        if not s.smtp_user or not s.smtp_password:
            raise ValueError(
                "Falta configurar SMTP_USER y SMTP_PASSWORD en .env para enviar correos."
            )
        sender = s.smtp_from or s.smtp_user

        # Override de prueba: si está seteado, todo va a esa dirección.
        if s.smtp_override_to:
            to = [s.smtp_override_to]
            cc = []

        if not to:
            raise ValueError("El correo no tiene destinatarios.")

        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg["Subject"] = subject
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")

        recipients = list(to) + list(cc or [])
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg, from_addr=sender, to_addrs=recipients)
        LOGGER.info("Correo enviado: %s -> %s", subject, recipients)
