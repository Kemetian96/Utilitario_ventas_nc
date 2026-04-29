from sap_report.application.report_service import _comparar_pagos


def test_comparar_pagos_detecta_faltantes_y_montos() -> None:
    sap_rows = [
        ("ORD-1", 100.0),
        ("ORD-2", 50.0),
        ("ORD-3", 30.0),
    ]
    sap_cols = ["U_PLA_ORDENWEB", "DocTotal"]

    tutati_rows = [
        ("ORD-1", 100.0),
        ("ORD-2", 40.0),
        ("ORD-4", 25.0),
    ]
    tutati_cols = ["uid_orders", "Amount"]

    rows, resumen = _comparar_pagos(
        sap_rows,
        sap_cols,
        tutati_rows,
        tutati_cols,
        threshold=0.01,
    )

    assert resumen == {
        "faltan_en_sap": 1,
        "faltan_en_tutati": 1,
        "montos_diferentes": 1,
        "coinciden": 1,
    }
    assert rows == [
        ("MONTO_DIFERENTE", "ORD-2", 50.0, 40.0, 10.0),
        ("FALTA_EN_TUTATI", "ORD-3", 30.0, 0.0, 30.0),
        ("FALTA_EN_SAP", "ORD-4", 0.0, 25.0, -25.0),
    ]
