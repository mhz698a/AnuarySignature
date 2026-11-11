"""Independent system-tray controller for the Domain Viewer application."""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

APP_NAME = "DomainViewer"

class SystemTrayController(QObject):
    """System tray UI decoupled from the Domain Viewer main window."""

    show_window_requested = pyqtSignal()
    restart_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, icon_path, parent=None):
        super().__init__(parent)

        self.available = QSystemTrayIcon.isSystemTrayAvailable()
        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)), self)
        self.tray_icon.setToolTip(
            APP_NAME + "\n"
            "Infraestructura de años, dominios y superdominios\n"
            "Contenedor de Anuarios del Regimen Sobrescritor""
        )

        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #2d2d2d;
            }
        """)

        self.show_action = self.menu.addAction("Show Domain Viewer")
        self.show_action.triggered.connect(self._request_show_window)

        self.menu.addSeparator()
        self.restart_action = self.menu.addAction("Restart Service")
        self.restart_action.triggered.connect(self._request_restart)

        self.exit_action = self.menu.addAction("Exit")
        self.exit_action.triggered.connect(self._confirm_exit)

        self.tray_icon.setContextMenu(self.menu)
        self.tray_icon.activated.connect(self._on_activated)

        if self.available:
            self.tray_icon.show()

    def is_available(self):
        """Return whether the operating system exposes a notification area."""
        return self.available

    def hide(self):
        self.tray_icon.hide()

    def show(self):
        if self.available:
            self.tray_icon.show()

    def _request_show_window(self):
        self.show_window_requested.emit()

    def _request_restart(self):
        self.restart_requested.emit()

    def _on_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._request_show_window()

    def _confirm_exit(self):
        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle("Exit Domain Viewer")
        dialog.setText("¿Desea salir de este programa?")

        exit_button = dialog.addButton(
            "Cerrar la aplicacion",
            QMessageBox.ButtonRole.AcceptRole,
        )
        cancel_button = dialog.addButton(
            "Cancelar",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(cancel_button)
        dialog.exec()

        if dialog.clickedButton() is exit_button:
            self.exit_requested.emit()
