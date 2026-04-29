from sap_report.bootstrap import build_service
from sap_report.ui import run_ui


def main() -> None:
    settings, service = build_service()
    # Lanza la interfaz con rango inicial y tamano configurado.
    run_ui(
        service=service,
        fecha_inicio_default_raw=settings.fecha_inicio_default,
        fecha_fin_default_raw=settings.fecha_fin_default,
        ui_width=settings.ui_width,
        ui_height=settings.ui_height,
    )


# Permite ejecutar como script directo.
if __name__ == "__main__":
    main()
