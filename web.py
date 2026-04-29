from pathlib import Path
import sys

try:
    from sap_report.web.app import main
except ModuleNotFoundError:
    # Fallback rapido para ejecutar sin instalar el paquete.
    root_dir = Path(__file__).resolve().parent
    src_dir = root_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    from sap_report.web.app import main


if __name__ == "__main__":
    main()
