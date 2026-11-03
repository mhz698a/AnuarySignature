# render_domains.pyw
# first release: 2026-06-23 20:35:00

from pathlib import Path
import sys
import ctypes
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon

from domain_visor.scene_view import VasculumApp

APP_DIR = Path(__file__).resolve().parent.as_posix()
ICON_WIN = f"{APP_DIR}/assets/online.ico"
JSON_DOMAINS = f"{APP_DIR}/__structure__/infrastructure.json"
CONTAINER_DOMAINS = f"{APP_DIR}/__structure__/container.json"

myappid = 'etudetools.year_struct.render_domains.1.0'
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def show_unexpected_error(exc_type, exc_value, exc_traceback):
    traceback_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(traceback_text, file=sys.stderr)

    message = QMessageBox()
    message.setIcon(QMessageBox.Icon.Critical)
    message.setWindowTitle("Error inesperado")
    message.setText("El programa se cerrará por un error inesperado.")
    message.setInformativeText(traceback_text)
    message.setDetailedText(traceback_text)
    message.exec()

    QApplication.quit()
    sys.exit(1)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    sys.excepthook = show_unexpected_error
    
    # Soporte para exportación headless PNG de prueba (Commit 12.1)
    if "--png_export" in sys.argv:
        try:
            idx = sys.argv.index("--png_export")
            if idx + 1 < len(sys.argv):
                export_path = sys.argv[idx + 1]
                
                # Instanciar el visor sin iniciar hilos ni mostrar la ventana (Headless)
                window = VasculumApp(JSON_DOMAINS, CONTAINER_DOMAINS)
                
                # Detener el diálogo de progreso de forma limpia
                if hasattr(window, 'progress_dialog') and window.progress_dialog:
                    window.progress_dialog.thread.quit()
                    window.progress_dialog.thread.wait()
                    window.progress_dialog.reject()
                window.trigger_render()

                from PyQt6.QtGui import QImage, QPainter, QColor
                from domain_visor.theme import Theme # type: ignore
                
                rect = window.scene.sceneRect()
                image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
                image.fill(QColor(Theme.DOMAIN_VIEW_BACKGROUND))
                
                painter = QPainter(image)
                window.scene.render(painter)
                painter.end()
                
                # Guardar en la ruta indicada
                image.save(export_path)
                print(f"Headless PNG export completed successfully to: {export_path}")
                sys.exit(0)
        except Exception as e:
            print(f"Error during headless export: {str(e)}", file=sys.stderr)
            sys.exit(1)

    try:
        app.setWindowIcon(QIcon(ICON_WIN))
    except Exception:
        pass

    window = VasculumApp(JSON_DOMAINS, CONTAINER_DOMAINS)
    # Requisito: la ventana debe mostrarse maximizada al aparecer
    window.showMaximized()
    sys.exit(app.exec())