import logging
from typing import Any

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGGER = logging.getLogger(__name__)


class SapServiceLayerRepository:
    def __init__(self, url: str, company_db: str, user: str, password: str) -> None:
        self._url = url.rstrip("/")
        self._company_db = company_db
        self._user = user
        self._password = password

    def _make_session(self, company_db: str) -> requests.Session:
        session = requests.Session()
        session.verify = False
        res = session.post(
            f"{self._url}/Login",
            json={"CompanyDB": company_db, "UserName": self._user, "Password": self._password},
            timeout=15,
        )
        res.raise_for_status()
        return session

    def _logout(self, session: requests.Session) -> None:
        try:
            session.post(f"{self._url}/Logout", timeout=10)
        except Exception:
            pass

    def consultar_pago(self, orden: str, company_db: str) -> dict[str, Any]:
        session = self._make_session(company_db)
        try:
            params = {
                "$filter": f"U_PLA_ORDENWEB eq '{orden}' and Cancelled eq 'tNO'",
            }
            res = session.get(f"{self._url}/IncomingPayments", params=params, timeout=20)
            res.raise_for_status()
            return res.json()
        finally:
            self._logout(session)

    def anular_pago(self, doc_entry: int, company_db: str) -> None:
        session = self._make_session(company_db)
        try:
            res = session.post(f"{self._url}/IncomingPayments({doc_entry})/Cancel", timeout=20)
            res.raise_for_status()
        finally:
            self._logout(session)

    def crear_pago(self, payload: dict[str, Any], company_db: str) -> dict[str, Any]:
        session = self._make_session(company_db)
        try:
            res = session.post(f"{self._url}/IncomingPayments", json=payload, timeout=30)
            res.raise_for_status()
            return res.json()
        finally:
            self._logout(session)
