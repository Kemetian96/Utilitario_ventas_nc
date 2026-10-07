"""La pantalla de Validacion Nubefact quedaba casi vacia al empezar el mes:
el dia 1 no habia ningun dia del mes en curso. Debe mostrar siempre un mes."""
from datetime import date, timedelta

from sap_report.application.report_service import NUBEFACT_DIAS, ReportService


def test_primer_dia_del_mes_muestra_un_mes() -> None:
    fechas = ReportService._fechas_nubefact(date(2026, 10, 1))
    assert len(fechas) == NUBEFACT_DIAS
    assert fechas[0] == date(2026, 9, 30)
    assert fechas[-1] == date(2026, 9, 1)


def test_mitad_de_mes_tambien_muestra_un_mes() -> None:
    fechas = ReportService._fechas_nubefact(date(2026, 10, 15))
    assert len(fechas) == NUBEFACT_DIAS
    assert fechas[0] == date(2026, 10, 14)


def test_fin_de_mes_largo_respeta_el_mes_entero() -> None:
    # El 31 el mes en curso ya tiene 30 dias cerrados: se muestran todos.
    fechas = ReportService._fechas_nubefact(date(2026, 10, 31))
    assert len(fechas) == 30
    assert fechas[-1] == date(2026, 10, 1)


def test_orden_descendente_y_termina_en_ayer() -> None:
    hoy = date(2026, 3, 9)
    fechas = ReportService._fechas_nubefact(hoy)
    assert fechas[0] == hoy - timedelta(days=1)
    assert fechas == sorted(fechas, reverse=True)
    assert hoy not in fechas
