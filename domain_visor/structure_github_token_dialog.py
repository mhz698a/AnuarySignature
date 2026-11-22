"""Dialog for registering the GitHub token used by Structure synchronization."""

from __future__ import annotations

from PyQt6.QtCore import QDate, QThread, Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.structure_credentials import StructureGitHubCredentialStore


TOKEN_CREATION_URL = "https://github.com/settings/personal-access-tokens/new"


class _TokenValidationWorker(QThread):
    validated = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, token: str, parent=None):
        super().__init__(parent)
        self.token = token

    def run(self):
        try:
            username = StructureGitHubCredentialStore.validate_token(self.token)
            self.validated.emit(username)
        except Exception as error:
            self.failed.emit(str(error))


class StructureGitHubTokenDialog(QDialog):
    """Validate a GitHub PAT and store it in Windows Credential Manager."""

    def __init__(self, credential_store, parent=None):
        super().__init__(parent)
        self.credential_store = credential_store
        self.worker = None
        self.pending_token = ""
        self.pending_expiration = None

        self.setWindowTitle("Credenciales de GitHub · Structure")
        self.setModal(True)
        self.setMinimumWidth(590)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
            }}
            QLineEdit, QDateEdit {{
                background-color: #252526;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px;
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px 11px;
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
            QPushButton:disabled {{
                color: #777777;
                border-color: #383838;
            }}
            QCheckBox {{
                spacing: 7px;
                color: {Theme.TEXT_WHITE};
            }}
        """)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Token de acceso personal")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        instructions = QLabel(
            "Crea un token fine-grained en GitHub y limita su acceso al repositorio "
            "mhz698a/AnuarySignature-Structure. En Repository permissions configura "
            "Contents como Read and write; Metadata permanece en Read-only."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        open_github_button = QPushButton("Crear token en GitHub")
        open_github_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(TOKEN_CREATION_URL))
        )
        layout.addWidget(open_github_button)

        form = QFormLayout()
        form.setSpacing(10)

        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setPlaceholderText("Pega aquí el token generado por GitHub")
        form.addRow("Token:", self.token_edit)

        self.show_token_checkbox = QCheckBox("Mostrar token")
        self.show_token_checkbox.toggled.connect(self._toggle_token_visibility)
        form.addRow("", self.show_token_checkbox)

        self.expiration_edit = QDateEdit()
        self.expiration_edit.setCalendarPopup(True)
        self.expiration_edit.setDisplayFormat("dd/MM/yyyy")
        self.expiration_edit.setMinimumDate(QDate.currentDate())
        self.expiration_edit.setDate(QDate.currentDate().addDays(90))
        form.addRow("Fecha de expiración:", self.expiration_edit)

        self.no_expiration_checkbox = QCheckBox(
            "El token se creó sin fecha de expiración"
        )
        self.no_expiration_checkbox.toggled.connect(
            lambda checked: self.expiration_edit.setEnabled(not checked)
        )
        form.addRow("", self.no_expiration_checkbox)

        layout.addLayout(form)

        expiry_note = QLabel(
            "La fecha se registra según la opción que selecciones al crear el token. "
            "GitHub no proporciona la fecha de vencimiento de un PAT al validarlo; "
            "por eso debe coincidir con la fecha configurada en GitHub."
        )
        expiry_note.setWordWrap(True)
        expiry_note.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(expiry_note)

        storage_note = QLabel(
            "El token se valida antes de guardarse y se almacena en el "
            "Administrador de credenciales de Windows. No se escribe en archivos "
            "del proyecto ni en la configuración de Git."
        )
        storage_note.setWordWrap(True)
        storage_note.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(storage_note)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)

        self.save_button = QPushButton("Validar y guardar token")
        self.save_button.clicked.connect(self._validate_and_save)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

    def _toggle_token_visibility(self, visible: bool):
        self.token_edit.setEchoMode(
            QLineEdit.EchoMode.Normal
            if visible
            else QLineEdit.EchoMode.Password
        )

    def _set_busy(self, busy: bool):
        self.token_edit.setEnabled(not busy)
        self.show_token_checkbox.setEnabled(not busy)
        self.expiration_edit.setEnabled(
            not busy and not self.no_expiration_checkbox.isChecked()
        )
        self.no_expiration_checkbox.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.cancel_button.setEnabled(not busy)

    def _validate_and_save(self):
        token = self.token_edit.text().strip()
        if not token:
            QMessageBox.warning(
                self,
                "Token de GitHub",
                "Pega el token generado en GitHub.",
            )
            return

        self.pending_token = token
        self.pending_expiration = (
            None
            if self.no_expiration_checkbox.isChecked()
            else self.expiration_edit.date().toString("yyyy-MM-dd")
        )

        self.status_label.setText(
            "Validando la cuenta de GitHub y el acceso al repositorio privado…"
        )
        self._set_busy(True)
        self.worker = _TokenValidationWorker(token, self)
        self.worker.validated.connect(self._on_token_validated)
        self.worker.failed.connect(self._on_token_validation_failed)
        self.worker.start()

    def _finish_worker(self):
        if self.worker is not None:
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

    def _on_token_validated(self, username: str):
        self._finish_worker()
        try:
            self.credential_store.save_token(
                self.pending_token,
                username,
                self.pending_expiration,
            )
        except Exception as error:
            self._set_busy(False)
            self.status_label.setText("No se pudo guardar el token.")
            QMessageBox.warning(self, "Token de GitHub", str(error))
            return

        expiry_text = (
            f"Vencimiento registrado: {self.pending_expiration}."
            if self.pending_expiration
            else "El token se registró sin fecha de expiración."
        )
        QMessageBox.information(
            self,
            "Token de GitHub",
            f"Token validado y guardado para @{username}.\n{expiry_text}",
        )
        self.accept()

    def _on_token_validation_failed(self, message: str):
        self._finish_worker()
        self._set_busy(False)
        self.status_label.setText("No se pudo validar el token.")
        QMessageBox.warning(self, "Token de GitHub", message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
