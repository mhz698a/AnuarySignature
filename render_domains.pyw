# render_domains.pyw
# first release: 2026-06-23 20:35:00

from pathlib import Path
import sys
import ctypes
import traceback

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon, QImage, QPainter, QColor

from engines.instance_mutex import SingleInstanceMutex
from engines.runtime_config import application_settings, get_dependent_path
from engines.scene_view import VasculumApp
from engines.system_tray import SystemTrayController
from domain_visor.theme import Theme


APP_DIR = Path(__file__).resolve().parent
ICON_WIN = APP_DIR / "assets" / "online.ico"
JSON_DOMAINS = APP_DIR / "__structure__" / "infrastructure.json"
CONTAINER_DOMAINS = APP_DIR / "__structure__" / "container.json"

myappid = "etudetools.year_struct.render_domains.1.0"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass


def show_unexpected_error(exc_type, exc_value, exc_traceback):
    traceback_text = "".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)
    )
    print(traceback_text, file=sys.stderr)

    message = QMessageBox()
    message.setIcon(QMessageBox.Icon.Critical)
    message.setWindowTitle("Error inesperado")
    message.setText("El programa se cerrará por un error inesperado.")
    message.setInformativeText(traceback_text)
    message.setDetailedText(traceback_text)
    message.exec()
    QApplication.quit()


def main():
    # El mutex se adquiere antes de crear ventanas o iniciar la indexación.
    instance_guard = SingleInstanceMutex()
    if not instance_guard.acquire():
        return 0

    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        app.aboutToQuit.connect(instance_guard.release)
        sys.excepthook = show_unexpected_error

        # La unidad dependiente se valida antes de cargar JSON, cachés o imágenes.
        settings = application_settings()
        dependent_path = get_dependent_path(settings)
        if not dependent_path.is_dir():
            QMessageBox.warning(
                None,
                "Unidad dependiente no detectada",
                "No se encontró la carpeta contenedora dependiente:\\n"
                f"{dependent_path}\\n\\n"
                "El programa se cerrará. Comprueba la unidad o configura una "
                "carpeta disponible en Ajustes.",
            )
            return 1

        try:
            app.setWindowIcon(QIcon(str(ICON_WIN)))
        except Exception:
            pass

        # Soporte para exportación headless PNG de prueba.
        if "--png_export" in sys.argv:
            try:
                idx = sys.argv.index("--png_export")
                if idx + 1 >= len(sys.argv):
                    raise ValueError("Falta la ruta de salida para --png_export.")

                export_path = Path(sys.argv[idx + 1]).expanduser()
                window = VasculumApp(
                    str(JSON_DOMAINS),
                    str(CONTAINER_DOMAINS),
                    dependent_path=dependent_path,
                )
                window.trigger_render()

                rect = window.scene.sceneRect()
                image = QImage(
                    int(rect.width()),
                    int(rect.height()),
                    QImage.Format.Format_ARGB32,
                )
                image.fill(QColor(Theme.DOMAIN_VIEW_BACKGROUND))

                painter = QPainter(image)
                window.scene.render(painter)
                painter.end()

                image.save(str(export_path))
                print(
                    "Headless PNG export completed successfully to: "
                    f"{export_path}"
                )
                return 0
            except Exception as error:
                print(
                    f"Error during headless export: {error}",
                    file=sys.stderr,
                )
                return 1

        window = VasculumApp(
            str(JSON_DOMAINS),
            str(CONTAINER_DOMAINS),
            dependent_path=dependent_path,
        )

        # La bandeja existe antes de comenzar el proceso de carga.
        tray_controller = SystemTrayController(str(ICON_WIN), parent=app)
        tray_controller.show_window_requested.connect(window.show_domain_viewer)
        tray_controller.restart_requested.connect(window.restart_service)
        tray_controller.exit_requested.connect(window.exit_from_tray)
        window.attach_tray_controller(tray_controller)

        # Solo se muestra el diálogo frameless durante la indexación.
        window.start_initial_loading()
        return app.exec()
    finally:
        instance_guard.release()


if __name__ == "__main__":
    sys.exit(main())
