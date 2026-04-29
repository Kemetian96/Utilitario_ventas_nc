from datetime import datetime

from sap_report.domain.cuid import fecha_a_cuid


def test_fecha_a_cuid_formato() -> None:
    result = fecha_a_cuid(datetime(2026, 1, 1, 0, 0, 0))
    assert isinstance(result, int)
    assert len(str(result)) == 19
