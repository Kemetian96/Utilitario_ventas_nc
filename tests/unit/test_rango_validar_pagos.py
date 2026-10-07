"""Los botones de mes en Validar Pagos no dependen de la fecha del formulario:
el mes actual va del dia 1 a hoy y el pasado es el mes anterior completo."""
from datetime import date

from sap_report.web.app import _rango_validar_pagos


def test_mes_actual_va_del_uno_a_hoy() -> None:
    assert _rango_validar_pagos("mes_actual", date(2026, 10, 5), date(2026, 1, 1)) == (
        date(2026, 10, 1),
        date(2026, 10, 5),
    )


def test_mes_pasado_es_el_mes_anterior_completo() -> None:
    assert _rango_validar_pagos("mes_pasado", date(2026, 10, 5), date(2026, 1, 1)) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
    )


def test_mes_pasado_cruza_el_ano() -> None:
    assert _rango_validar_pagos("mes_pasado", date(2026, 1, 9), date(2026, 1, 1)) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
    )


def test_mes_pasado_toma_febrero_entero() -> None:
    assert _rango_validar_pagos("mes_pasado", date(2026, 3, 10), date(2026, 1, 1)) == (
        date(2026, 2, 1),
        date(2026, 2, 28),
    )


def test_mes_actual_el_dia_uno_es_un_solo_dia() -> None:
    assert _rango_validar_pagos("mes_actual", date(2026, 3, 1), date(2026, 1, 1)) == (
        date(2026, 3, 1),
        date(2026, 3, 1),
    )


def test_dia_usa_la_fecha_del_formulario() -> None:
    assert _rango_validar_pagos("dia", date(2026, 10, 5), date(2026, 10, 4)) == (
        date(2026, 10, 4),
        date(2026, 10, 4),
    )
