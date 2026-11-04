# domain_visor/progress_dialog.py

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import QThread, pyqtSignal, QObject, Qt
import pathlib
import threading
from domain_visor.theme import Theme
from domain_visor.character_row_item import (
    IMAGE_CACHE,
    load_icon_thumbnail,
    resolve_character_icon_path,
)

class ScanCancelled(Exception):
    """Internal signal used to stop a scan at a safe work boundary."""


class ScanWorker(QObject):
    """
    Worker que ejecuta el escaneo, verificación, precarga de imágenes y renderizado preparatorio
    en segundo plano.
    """
    progress = pyqtSignal(int)      # Emite el porcentaje de progreso (0-100)
    status_msg = pyqtSignal(str)   # Emite un mensaje de estado actual
    finished = pyqtSignal()         # Emite al terminar

    def __init__(self, character_manager):
        super().__init__()
        self.character_manager = character_manager
        self._cancel_event = threading.Event()

    def request_cancel(self):
        """Solicita cancelar el trabajo al finalizar la unidad de trabajo actual."""
        self._cancel_event.set()

    def _raise_if_cancelled(self):
        if self._cancel_event.is_set():
            raise ScanCancelled()

    def _report_scan_progress(self, completed, total, year):
        self._raise_if_cancelled()
        self.status_msg.emit(f"Indexando directorio del año {year}...")
        percentage = 10 + int(completed / max(total, 1) * 60)
        self.progress.emit(percentage)

    def run(self):
        try:
            self.status_msg.emit("Iniciando verificación de credenciales...")
            self.progress.emit(0)

            # Migra las cachés heredadas antes de escanear. La ubicación del JSON
            # será la única referencia persistente para resolver los recursos.
            self.character_manager.migrate_cached_characters()
            self._raise_if_cancelled()
            self.progress.emit(10)

            if self.character_manager.base_path.exists():
                self.character_manager.scan_all_years(
                    progress_callback=self._report_scan_progress,
                    cancel_check=self._cancel_event.is_set,
                )
                self._raise_if_cancelled()
            else:
                self.status_msg.emit(
                    f"Advertencia: No existe {self.character_manager.base_path}. "
                    "Se utilizarán las credenciales que ya estén en caché."
                )

            # Fase 3: precargar exactamente las mismas rutas que utilizará el visor.
            all_chars = []
            for characters in self.character_manager._cache.values():
                self._raise_if_cancelled()
                for char in characters:
                    self._raise_if_cancelled()
                    if char.get("icon_path") and char.get("character_json_path"):
                        all_chars.append(char)

            total_imgs = len(all_chars)
            for index, char in enumerate(all_chars, start=1):
                self._raise_if_cancelled()
                self.status_msg.emit(
                    f"Cargando imagen de {char.get('name', 'personaje')} "
                    f"({index}/{total_imgs})..."
                )
                full_img_path = resolve_character_icon_path(char)

                if full_img_path and full_img_path not in IMAGE_CACHE:
                    try:
                        if pathlib.Path(full_img_path).is_file():
                            thumbnail = load_icon_thumbnail(full_img_path)
                            if not thumbnail.isNull():
                                IMAGE_CACHE[full_img_path] = thumbnail
                    except Exception as exc:
                        print(
                            f"No se pudo precargar la imagen de "
                            f"{char.get('name', 'personaje')}: {exc}"
                        )

                self.progress.emit(70 + int(index / max(total_imgs, 1) * 30))

            self._raise_if_cancelled()
            self.progress.emit(100)
            self.status_msg.emit("¡Procesamiento e indexación completa!")
        except ScanCancelled:
            self.status_msg.emit("Indexación cancelada.")
        except Exception as exc:
            self.status_msg.emit(f"Error durante la indexación: {exc}")
            self.progress.emit(100)
            print(f"Error durante el escaneo de personajes: {exc}")
        finally:
            self.finished.emit()


class ProgressDialog(QDialog):
    """
    Ventana de progreso que muestra el estado de escaneo de los personajes en segundo plano.
    Diseñada de forma no modal con estilos adaptados al visor.
    """
    def __init__(self, character_manager, parent=None):
        super().__init__(parent)
        self.character_manager = character_manager
        self.setWindowTitle("Procesando indexación de personajes e imágenes...")
        self.setFixedSize(450, 150)

        # El diálogo es una ventana superior independiente, sin marco ni barra de título.
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        # Aplicar colores del tema
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
                border: 1px solid {Theme.SUPERDOMAIN_BORDER};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QProgressBar {{
                border: 1px solid {Theme.SUPERDOMAIN_BORDER};
                border-radius: 4px;
                text-align: center;
                background-color: #2d2d2d;
                color: {Theme.TEXT_WHITE};
                height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ROLE_EXODOMAIN_BG};
                width: 10px;
            }}
        """)

        # Configurar UI
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(12)

        self.info_label = QLabel("Iniciando indexación de personajes...", self)
        self.info_label.setWordWrap(True)
        self.layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.layout.addWidget(self.progress_bar)

        # Configurar Hilo de Procesamiento
        self.thread = QThread(self)
        self.worker = ScanWorker(character_manager)
        self.worker.moveToThread(self.thread)

        # Conectar señales del worker
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status_msg.connect(self.info_label.setText)
        self.worker.finished.connect(self.on_scan_finished)

        # Iniciar hilo al abrir la ventana
        self.thread.started.connect(self.worker.run)

    def _center_on_primary_screen(self):
        """Centra el diálogo en el área útil del monitor principal."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.move(
            geometry.center().x() - self.width() // 2,
            geometry.center().y() - self.height() // 2,
        )

    def start_loading(self):
        """Muestra el diálogo centrado e inicia el hilo de escaneo."""
        self._center_on_primary_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        self.thread.start()

    def cancel_loading(self):
        """Solicita una cancelación segura del escaneo/preload activo."""
        self.worker.request_cancel()
        if self.thread.isRunning():
            self.thread.quit()

    def on_scan_finished(self):
        """Maneja el fin de la indexación, deteniendo el hilo y cerrando el diálogo."""
        self.thread.quit()
        self.thread.wait()
        self.accept()
