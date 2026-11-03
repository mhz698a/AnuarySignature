# domain_visor/scene_view.py

import json
import subprocess
import sys
import traceback
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QSplitter, QPushButton,
    QMenuBar, QMenu, QSlider, QMessageBox, QFileDialog, QLabel
)
from PyQt6.QtCore import Qt, QSettings, QByteArray, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QShortcut, QKeySequence

from domain_visor.theme import Theme
from domain_visor.render_engine import RenderEngine
from domain_visor.json_editor import JSONEditorPanel
from domain_visor.character_manager import CharacterManager
from domain_visor.progress_dialog import ProgressDialog
from domain_visor.year_item import YearItem
from domain_visor.about_dialog import AboutDialog

class ZoomableGraphicsView(QGraphicsView):
    """
    Vista de QGraphics personalizada con zoom mediante Ctrl + rueda y navegación.
    """

    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.zoom_factor = 1.0
        self.min_zoom = 0.2
        self.max_zoom = 5.0
        self.zoom_slider = None

        # Anclar el zoom en el centro de la vista
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # Crear el botón flotante
        self.toggle_button = QPushButton("◀", self)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3e3e42;
                border-color: #85c1e9;
            }
            QPushButton:pressed {
                background-color: #1e1e1e;
            }
        """)
        self.toggle_button.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_controls_position()

    def update_controls_position(self):
        scrollbar_height = (
            self.horizontalScrollBar().height()
            if self.horizontalScrollBar().isVisible()
            else 0
        )
        x = 15
        y = self.height() - self.toggle_button.height() - 15 - scrollbar_height
        self.toggle_button.move(x, y)

    def update_button_position(self):
        self.update_controls_position()

    def _on_slider_value_changed(self, value):
        target_zoom = max(
            self.min_zoom,
            min(self.max_zoom, value / 100.0)
        )
        if self.zoom_factor != target_zoom:
            relative_factor = target_zoom / self.zoom_factor
            self.scale(relative_factor, relative_factor)
            self.zoom_factor = target_zoom
            self.zoom_changed.emit(self.zoom_factor)

    def _sync_slider(self):
        if self.zoom_slider is not None:
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(int(round(self.zoom_factor * 100)))
            self.zoom_slider.blockSignals(False)
        self.zoom_changed.emit(self.zoom_factor)

    def wheelEvent(self, event):
        # La rueda normal desplaza verticalmente la escena. Ctrl + rueda se
        # reserva exclusivamente al zoom y nunca se propaga al scroll del visor.
        modifiers = event.modifiers()
        if not (modifiers & Qt.KeyboardModifier.ControlModifier):
            super().wheelEvent(event)
            return

        angle_delta = event.angleDelta().y()
        if angle_delta == 0:
            event.accept()
            return

        zoom_step = 1.15
        new_zoom = (
            self.zoom_factor * zoom_step
            if angle_delta > 0
            else self.zoom_factor / zoom_step
        )
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))

        if new_zoom != self.zoom_factor:
            relative_factor = new_zoom / self.zoom_factor
            self.scale(relative_factor, relative_factor)
            self.zoom_factor = new_zoom
            self._sync_slider()

        event.accept()

    def zoom_in(self):
        new_zoom = self.zoom_factor * 1.15
        if new_zoom <= self.max_zoom:
            relative_factor = new_zoom / self.zoom_factor
            self.scale(relative_factor, relative_factor)
            self.zoom_factor = new_zoom
            self._sync_slider()

    def zoom_out(self):
        new_zoom = self.zoom_factor / 1.15
        if new_zoom >= self.min_zoom:
            relative_factor = new_zoom / self.zoom_factor
            self.scale(relative_factor, relative_factor)
            self.zoom_factor = new_zoom
            self._sync_slider()

    def zoom_reset(self):
        if self.zoom_factor != 1.0:
            relative_factor = 1.0 / self.zoom_factor
            self.scale(relative_factor, relative_factor)
            self.zoom_factor = 1.0
            self._sync_slider()


class VasculumApp(QMainWindow):
    """
    Ventana principal del visor de infraestructura.
    Responsable únicamente de configurar la ventana principal, la vista y la escena de QGraphics.
    Delega todo el renderizado y la lógica de creación de gráficos al RenderEngine.
    """

    galleryanuary_requested = pyqtSignal(str)

    def __init__(self, json_path, json_title):
        super().__init__()
        self.json_path = json_path
        self._json_title = json_title
        self._first_show = True
        self.setWindowTitle("Infraestructura de años, dominios y superdominios")
        self.setStyleSheet(f"background-color: {Theme.APP_BACKGROUND}; color: {Theme.TEXT_WHITE};")
        
        self.settings = QSettings("etudetools", "year_struct_vasculum")
        self._allow_application_exit = False
        self.tray_controller = None
        self.galleryanuary_requested.connect(
            self.open_credential_with_galleryanuary
        )
        self.init_ui()

    def init_ui(self):
        self.character_manager = CharacterManager()
        # Sincronizar el gestor de personajes a nivel de YearItem
        YearItem._char_manager = self.character_manager

        # 1. Crear el splitter central
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3e3e42;
                width: 4px;
            }
        """)

        # 2. Configurar JSONEditorPanel en la izquierda
        self.json_panel = JSONEditorPanel(self)
        self.splitter.addWidget(self.json_panel)

        # 3. Configurar ZoomableGraphicsView como panel derecho
        self.view = ZoomableGraphicsView()
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.view.setBackgroundBrush(QBrush(QColor(Theme.DOMAIN_VIEW_BACKGROUND)))
        
        # Soportar arrastre directo estilo mano además de las barras de desplazamiento (Paso 2)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.splitter.addWidget(self.view)

        # El control del zoom vive en la barra de estado, fuera del área de dibujo.
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.zoom_slider.setRange(
            int(self.view.min_zoom * 100),
            int(self.view.max_zoom * 100)
        )
        self.zoom_slider.setValue(int(self.view.zoom_factor * 100))
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #555555;
                height: 6px;
                background: #2d2d2d;
                margin: 2px 0;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #85c1e9;
                border: 1px solid #555555;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #aed6f1;
            }
        """)
        self.view.zoom_slider = self.zoom_slider
        self.zoom_slider.valueChanged.connect(self.view._on_slider_value_changed)

        self.zoom_percentage_label = QLabel("100%", self)
        self.zoom_percentage_label.setMinimumWidth(48)
        self.zoom_percentage_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.view.zoom_changed.connect(self.update_zoom_percentage)

        status_bar = self.statusBar()
        status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #1b1b1b;
                color: #d4d4d4;
                border-top: 1px solid #333333;
            }
            QStatusBar::item {
                border: none;
            }
        """)
        zoom_label = QLabel("Zoom", self)
        zoom_label.setStyleSheet("color: #bdbdbd; padding-left: 6px;")
        self.zoom_percentage_label.setStyleSheet("color: #ffffff; padding-right: 8px;")
        status_bar.addPermanentWidget(zoom_label)
        status_bar.addPermanentWidget(self.zoom_slider)
        status_bar.addPermanentWidget(self.zoom_percentage_label)
        status_bar.showMessage("Visor de dominios listo", 3000)

        # 4. Crear la escena y asignarla al View
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QBrush(QColor(Theme.DOMAIN_VIEW_BACKGROUND)))
        self.view.setScene(self.scene)

        # 5. Instanciar RenderEngine para delegar el renderizado
        self.render_engine = RenderEngine(self.character_manager)

        # Cargar archivo JSON e inicializar el tree view
        self.load_initial_json()

        # Conectar cambios del tree view para el guardado automático y renderizado
        self.json_panel.tree.json_changed.connect(self.on_json_data_changed)

        # 6. Configurar atajos de teclado para Zoom (Paso 2)
        self.setup_shortcuts()

        # 7. Configurar vista central y tamaño mínimo, y restaurar estado de splitter
        self.setCentralWidget(self.splitter)
        self.setMinimumSize(1400, 700)

        self.restore_splitter_state()

        # Restaurar estado visible de la edición del JSON
        self.restore_editor_visible_state()

        # Conectar el botón para mostrar/ocultar el editor
        self.view.toggle_button.clicked.connect(self.toggle_json_editor)

        # 7.5. Configurar barra de menú oscura "Archivo" y "Ayuda"
        self.menu_bar = self.menuBar()
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #1e1e1e;
                color: #ffffff;
                border-bottom: 1px solid #3e3e42;
                font-family: Arial;
                font-size: 12px;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 10px;
            }
            QMenuBar::item:selected {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QMenu {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                font-family: Arial;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 20px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #2d2d2d;
                color: #ffffff;
            }
        """)

        file_menu = self.menu_bar.addMenu("Archivo")
        self.refresh_action = file_menu.addAction("Refresh")
        self.refresh_action.setShortcut(QKeySequence("F5"))
        self.refresh_action.triggered.connect(self.refresh_data)

        self.regen_cache_action = file_menu.addAction("Regenerar caché y recargar renderizado")
        self.regen_cache_action.triggered.connect(self.confirm_and_regenerate_cache)

        settings_menu = self.menu_bar.addMenu("Ajustes")
        self.galleryanuary_access_action = settings_menu.addAction(
            "Definir Acceso a GalleryAnuary"
        )
        self.galleryanuary_access_action.triggered.connect(
            self.define_galleryanuary_access
        )

        help_menu = self.menu_bar.addMenu("Ayuda")
        self.about_action = help_menu.addAction("Acerca de...")
        self.about_action.triggered.connect(self.show_about_dialog)

        # 8. Mostrar Ventana de Progreso en Segundo Plano para Indexación de JSON/Personajes y carga de imágenes
        self.progress_dialog = ProgressDialog(self.character_manager, self)
        # Una vez que termine la indexación, realizamos el re-renderizado inicial de forma segura
        self.progress_dialog.finished.connect(self.trigger_render)
        self.progress_dialog.start_loading()

    def define_galleryanuary_access(self):
        """Selecciona y persiste el ejecutable o script de GalleryAnuary."""
        configured_path = str(
            self.settings.value("galleryanuary_executable", "") or ""
        )
        start_directory = (
            str(Path(configured_path).parent)
            if configured_path and Path(configured_path).is_file()
            else str(Path.home())
        )
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "Definir acceso a GalleryAnuary",
            start_directory,
            "GalleryAnuary (GalleryAnuary.exe app.py app.pyw);;"
            "Aplicaciones (*.exe);;Scripts Python (*.py *.pyw);;Todos los archivos (*)"
        )
        if not selected_path:
            return

        selected_file = Path(selected_path).expanduser().resolve()
        if not selected_file.is_file():
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                f"El archivo seleccionado no existe:\n{selected_file}"
            )
            return

        if selected_file.suffix.lower() not in {".exe", ".py", ".pyw"}:
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                "Selecciona el ejecutable de GalleryAnuary o su archivo app.py/app.pyw."
            )
            return

        self.settings.setValue("galleryanuary_executable", str(selected_file))
        QMessageBox.information(
            self,
            "GalleryAnuary",
            f"Acceso guardado:\n{selected_file}"
        )

    def open_credential_with_galleryanuary(self, credential_directory):
        """Inicia GalleryAnuary y le pasa la carpeta que contiene la credencial."""
        configured_path = str(
            self.settings.value("galleryanuary_executable", "") or ""
        ).strip()
        if not configured_path:
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                "Primero define el acceso desde Ajustes > Definir Acceso a GalleryAnuary."
            )
            return

        gallery_path = Path(configured_path).expanduser()
        if not gallery_path.is_file():
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                f"El ejecutable configurado no existe:\n{gallery_path}\n"
                "Vuelve a definir el acceso desde el menú Ajustes."
            )
            return

        credential_path = Path(credential_directory).expanduser()
        if not credential_path.is_dir():
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                f"No se encontró la carpeta de la credencial:\n{credential_path}"
            )
            return

        if gallery_path.suffix.lower() in {".py", ".pyw"}:
            python_executable = sys.executable
            if sys.platform == "win32" and Path(sys.executable).with_name("pythonw.exe").is_file():
                python_executable = str(Path(sys.executable).with_name("pythonw.exe"))
            command = [python_executable, str(gallery_path.resolve()), str(credential_path.resolve())]
        else:
            command = [str(gallery_path.resolve()), str(credential_path.resolve())]

        try:
            subprocess.Popen(
                command,
                cwd=str(gallery_path.resolve().parent),
                close_fds=True
            )
        except OSError as error:
            QMessageBox.critical(
                self,
                "GalleryAnuary",
                f"No se pudo iniciar GalleryAnuary:\n{error}"
            )

    def update_zoom_percentage(self, zoom_factor):
        self.zoom_percentage_label.setText(f"{zoom_factor:.0%}")

    def show_status_message(self, message, timeout_ms=5000):
        """Muestra mensajes temporales en la barra de estado."""
        self.statusBar().showMessage(str(message), max(0, int(timeout_ms)))

    def attach_tray_controller(self, tray_controller):
        """Asocia el controlador independiente de bandeja con la ventana."""
        self.tray_controller = tray_controller

    def show_domain_viewer(self):
        """Muestra y activa la ventana desde el icono de bandeja."""
        self.showMaximized()
        self.raise_()
        self.activateWindow()

    def exit_from_tray(self):
        """Acepta el cierre solicitado y confirmado desde el menú de bandeja."""
        self._allow_application_exit = True
        self.close()

    def confirm_and_regenerate_cache(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Regenerar caché")
        msg_box.setText("¿Desea continuar con la regeneración de la caché y recargar el renderizado?")
        msg_box.setIcon(QMessageBox.Icon.Question)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.No)
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 14px;
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
        """)
        reply = msg_box.exec()
        if reply == QMessageBox.StandardButton.Yes:
            self.refresh_data()

    def show_about_dialog(self):
        dlg = AboutDialog(parent=self)
        dlg.exec()

    def restore_editor_visible_state(self):
        editor_visible_setting = self.settings.value("json_editor_visible")
        if editor_visible_setting is None:
            self.editor_visible = True
        elif isinstance(editor_visible_setting, str):
            self.editor_visible = (editor_visible_setting.lower() == "true")
        else:
            self.editor_visible = bool(editor_visible_setting)

        self.json_panel.setVisible(self.editor_visible)
        btn_text = "◀" if self.editor_visible else "▶"
        self.view.toggle_button.setText(btn_text)
        self.view.update_button_position()

    def toggle_json_editor(self):
        self.editor_visible = not self.editor_visible
        self.json_panel.setVisible(self.editor_visible)
        self.settings.setValue("json_editor_visible", self.editor_visible)

        btn_text = "◀" if self.editor_visible else "▶"
        self.view.toggle_button.setText(btn_text)
        self.view.update_button_position()

    def load_initial_json(self):
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.json_panel.tree.load_json(data)
        except Exception as e:
            self.show_error(f"Error cargando JSON inicial:\n{str(e)}")

    def on_json_data_changed(self):
        # 1. Obtener datos actuales del árbol
        try:
            data = self.json_panel.tree.get_json()
        except Exception as e:
            self.show_error(f"Error generando estructura JSON:\n{str(e)}")
            return

        # 2. Guardar automáticamente a infrastructure.json
        try:
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.show_error(f"Error escribiendo en archivo de infraestructura:\n{str(e)}")
            return

        # 3. Re-renderizar escena
        self.trigger_render()
        self.show_status_message("Cambios guardados.", 2500)

    def trigger_render(self):
        try:
            # Intentar renderizar
            self.render_engine.render(self.scene, self._json_title, self.json_path)
            # Si fue exitoso, ocultamos el cartel de error
            self.json_panel.error_label.setVisible(False)
        except Exception as e:
            tb = traceback.format_exc()
            self.show_error(f"Error de dibujo o validación en el renderizado:\n{tb}")

    def setup_shortcuts(self):
        # Atajos para Zoom In (Ctrl + + y Ctrl + =)
        self.shortcut_zoom_in_plus = QShortcut(QKeySequence("Ctrl++"), self)
        self.shortcut_zoom_in_plus.activated.connect(self.view.zoom_in)
        
        self.shortcut_zoom_in_equal = QShortcut(QKeySequence("Ctrl+="), self)
        self.shortcut_zoom_in_equal.activated.connect(self.view.zoom_in)

        # Atajo para Zoom Out (Ctrl + -)
        self.shortcut_zoom_out = QShortcut(QKeySequence("Ctrl+-"), self)
        self.shortcut_zoom_out.activated.connect(self.view.zoom_out)

        # Atajo para Resetear Zoom (Ctrl + 0)
        self.shortcut_zoom_reset = QShortcut(QKeySequence("Ctrl+0"), self)
        self.shortcut_zoom_reset.activated.connect(self.view.zoom_reset)

    def restore_splitter_state(self):
        state = self.settings.value("splitter_state")
        if state is not None:
            if isinstance(state, QByteArray):
                self.splitter.restoreState(state)
            elif isinstance(state, bytes):
                self.splitter.restoreState(QByteArray(state))
        else:
            # Por defecto, dar el 35% del ancho total al JSON editor
            self.splitter.setSizes([350, 650])

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.center_domains_container()

    def center_domains_container(self):
        rect = self.scene.itemsBoundingRect()
        if not rect.isNull():
            self.view.centerOn(rect.center())

    def refresh_data(self):
        # Detener diálogo de progreso previo si existía
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            try:
                self.progress_dialog.thread.quit()
                self.progress_dialog.thread.wait()
            except Exception:
                pass

        # 1. Limpiar caché global de pixmaps para forzar la recarga de imágenes modificadas/nuevas
        from domain_visor.character_row_item import PIXMAP_CACHE
        PIXMAP_CACHE.clear()

        # 2. Limpiar el caché de personajes en memoria para obligar a reconstruirlo desde cero desde disco
        self.character_manager._cache.clear()

        # 3. Instanciar y mostrar de nuevo el ProgressDialog
        self.progress_dialog = ProgressDialog(self.character_manager, self)
        self.progress_dialog.finished.connect(self.trigger_render)
        self.progress_dialog.start_loading()

    def closeEvent(self, event):
        if not self._allow_application_exit:
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("Salir")
            dialog.setText("¿Desea salir de este programa?")

            close_button = dialog.addButton(
                "Cerrar la aplicacion",
                QMessageBox.ButtonRole.AcceptRole
            )
            minimize_button = dialog.addButton(
                "Minimizar en la bandeja",
                QMessageBox.ButtonRole.ActionRole
            )
            cancel_button = dialog.addButton(
                "Cancelar",
                QMessageBox.ButtonRole.RejectRole
            )
            dialog.setDefaultButton(cancel_button)
            dialog.exec()

            clicked_button = dialog.clickedButton()
            if clicked_button is minimize_button:
                if (
                    self.tray_controller is None
                    or not self.tray_controller.is_available()
                ):
                    QMessageBox.warning(
                        self,
                        "Bandeja del sistema no disponible",
                        "No se puede minimizar en la bandeja porque el sistema "
                        "no tiene un área de notificación disponible."
                    )
                    event.ignore()
                    return

                self.settings.setValue("splitter_state", self.splitter.saveState())
                self.hide()
                event.ignore()
                return

            if clicked_button is not close_button:
                event.ignore()
                return

            self._allow_application_exit = True

        self.settings.setValue("splitter_state", self.splitter.saveState())

        if hasattr(self, "progress_dialog") and self.progress_dialog:
            try:
                self.progress_dialog.thread.quit()
                self.progress_dialog.thread.wait()
            except Exception:
                pass

        if self.tray_controller is not None:
            self.tray_controller.hide()

        event.accept()
        app = QApplication.instance()
        if app is not None:
            app.quit()
