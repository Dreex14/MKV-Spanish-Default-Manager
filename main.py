"""Punto de entrada de MKV Spanish Default Manager."""
import logging
import sys

from mkvsd.paths import app_data_dir

APP_ID = "MKVSpanishDefaultManager.App"   # se conserva: los accesos anclados siguen funcionando


def main() -> int:
    logging.basicConfig(
        filename=str(app_data_dir() / "app.log"), level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8",
    )
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("Falta PySide6. Ejecuta install.bat o: pip install -r requirements.txt")
        return 1
    if sys.platform == "win32":
        # Identidad propia para que la barra de tareas muestre nuestro icono y se pueda anclar bien
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    # Escalado fraccionario nítido (125 %, 150 %, 175 %…) sin redondear a enteros
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    from mkvsd.ui import icons
    from mkvsd.ui.main_window import MainWindow
    from mkvsd.ui.styles import apply_dark_theme

    app = QApplication(sys.argv)
    app.setApplicationName("MKV Spanish Default Manager")
    app.setWindowIcon(icons.app_icon())
    apply_dark_theme(app)
    sys.excepthook = _log_exception
    window = MainWindow()
    window.show()
    return app.exec()


def _log_exception(exc_type, exc, tb):
    """Un error inesperado en la interfaz se anota en app.log en lugar de cerrar la aplicación en silencio."""
    logging.error("Error no controlado", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)


if __name__ == "__main__":
    sys.exit(main())
