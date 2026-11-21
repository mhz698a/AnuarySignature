"""Review dialog for applying Structure character-cache values to local credentials."""

from __future__ import annotations

import json

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)

from domain_visor.theme import Theme
from engines.character_cache_sync import CharacterCacheSyncService


class _CharacterCacheSyncWorker(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, operation: str, callback, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.operation, self.callback())
        except Exception as error:
            self.failed.emit(self.operation, str(error))


class CharacterCacheSyncDialog(QDialog):
    """Show per-field differences and require explicit selection before writing local JSONs."""

    def __init__(self, service: CharacterCacheSyncService, parent=None):
        super().__init__(parent)
        self.service = service
        self.worker = None
        self.applied = False
        self.apply_result = None
        self._has_selectable_rows = False
        self._close_after_worker = False

        self.setWindowTitle("Aplicar caché Structure a credenciales locales")
        self.setModal(True)
        self.resize(1040, 620)
        self.setMinimumSize(850, 480)
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
            QLabel {{ color: {Theme.TEXT_WHITE}; }}
            QPushButton, QTableWidget {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton {{ padding: 7px 10px; }}
            QPushButton:hover {{ background-color: #3e3e42; border-color: #85c1e9; }}
            QPushButton:disabled {{ color: #777777; border-color: #383838; }}
            QHeaderView::section {{
                background-color: #252525;
                color: #ffffff;
                padding: 6px;
                border: 1px solid #444444;
                font-weight: bold;
            }}
            QTableWidget {{
                gridline-color: #444444;
                selection-background-color: #3e3e42;
                alternate-background-color: #252525;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.description_label = QLabel(
            "Se comparan los campos guardados en characters_cache.json con cada "
            "credencial encontrada en esta unidad. Solo se escribirán los campos "
            "seleccionados. Cada credencial tendrá un respaldo previo fuera del repositorio."
        )
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self.status_label = QLabel("Comparando caché y credenciales locales…")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 8px; font-weight: bold;"
        )
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels([
            "Aplicar", "Año", "Personaje", "Campo", "Valor local",
            "Valor Structure", "Estado",
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.refresh_button = QPushButton("Volver a comparar")
        self.refresh_button.clicked.connect(self._start_preview)
        footer.addWidget(self.refresh_button)
        footer.addStretch()
        self.apply_button = QPushButton("Aplicar seleccionados")
        self.apply_button.clicked.connect(self._confirm_apply)
        footer.addWidget(self.apply_button)
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self._start_preview()

    @staticmethod
    def _display_value(value) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return "null"
        return str(value)

    @staticmethod
    def _has_value(value) -> bool:
        return value not in ("", None, [], {})

    def _set_busy(self, busy: bool):
        self.refresh_button.setEnabled(not busy)
        self.apply_button.setEnabled(not busy and self._has_selectable_rows)
        self.close_button.setEnabled(not busy)
        self.table.setEnabled(not busy)

    def _start_worker(self, operation: str, callback):
        if self.worker is not None and self.worker.isRunning():
            return
        self._set_busy(True)
        worker = _CharacterCacheSyncWorker(operation, callback, self)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _start_preview(self):
        self.status_label.setText("Comparando caché y credenciales locales…")
        self._start_worker("preview", self.service.preview_changes)

    def _populate_rows(self, rows: list[dict]):
        self.table.setRowCount(0)
        selectable_count = 0
        issue_count = 0

        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            is_issue = bool(row_data.get("error"))
            if is_issue:
                issue_count += 1
            else:
                selectable_count += 1

            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked
                if not is_issue and self._has_value(row_data.get("structure_value"))
                else Qt.CheckState.Unchecked
            )
            check_item.setData(Qt.ItemDataRole.UserRole, row_data)
            if is_issue:
                check_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
            self.table.setItem(row, 0, check_item)

            character = str(row_data.get("name") or "")
            alterego = str(row_data.get("alterego") or "")
            character_label = character
            if alterego and alterego.casefold() != character.casefold():
                character_label = f"{character} · {alterego}"

            values = [
                str(row_data.get("year", "")),
                character_label,
                str(row_data.get("field") or "No se pudo comparar"),
                self._display_value(row_data.get("local_value", "")),
                self._display_value(row_data.get("structure_value", "")),
                row_data.get("error", "Diferencia detectada"),
            ]
            for column, value in enumerate(values, start=1):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                self.table.setItem(row, column, item)

        self._has_selectable_rows = selectable_count > 0
        self.status_label.setText(
            f"Diferencias detectadas: {selectable_count}. "
            f"Registros que requieren revisión: {issue_count}. "
            "Los valores vacíos no se seleccionan automáticamente."
        )
        self.apply_button.setEnabled(selectable_count > 0)

    def _selected_rows(self) -> list[dict]:
        selected = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                row_data = item.data(Qt.ItemDataRole.UserRole)
                if row_data and not row_data.get("error"):
                    selected.append(row_data)
        return selected

    def _confirm_apply(self):
        selected = self._selected_rows()
        if not selected:
            QMessageBox.information(
                self,
                "Sin campos seleccionados",
                "Selecciona al menos un cambio válido para aplicarlo.",
            )
            return

        character_count = len({
            (
                int(row["year"]),
                str(row["name"]).casefold(),
                str(row["alterego"]).casefold(),
            )
            for row in selected
        })
        reply = QMessageBox.question(
            self,
            "Confirmar cambios en credenciales locales",
            f"Se modificarán {len(selected)} campo(s) de {character_count} personaje(s). "
            "Antes de escribir cada credencial se guardará una copia íntegra en "
            "%LOCALAPPDATA%\\AnuarySignature\\CharacterCacheSync\\Backups. "
            "Los archivos de imagen no se reemplazan ni eliminan. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.status_label.setText("Aplicando cambios seleccionados y creando respaldos…")
        self._start_worker(
            "apply",
            lambda: self.service.apply_selected(selected),
        )

    def _on_completed(self, operation: str, result):
        if operation == "preview":
            self._populate_rows(result)
            if not result:
                self.status_label.setText(
                    "No hay diferencias entre el caché de Structure y las credenciales locales."
                )
        elif operation == "apply":
            self.apply_result = result
            self.applied = result.get("applied_fields", 0) > 0
            message = (
                f"Personajes modificados: {result.get('applied_characters', 0)}\n"
                f"Campos aplicados: {result.get('applied_fields', 0)}\n"
                f"Cambios restantes: {result.get('remaining_changes', 0)}\n"
                f"Respaldo: {result.get('backup_root', '')}"
            )
            if result.get("issues"):
                message += "\n\nIncidencias:\n" + "\n".join(result["issues"][:8])
                QMessageBox.warning(self, "Aplicación parcial", message)
            else:
                QMessageBox.information(self, "Cambios aplicados", message)
            self._close_after_worker = True

    def _on_failed(self, operation: str, message: str):
        self.status_label.setText(
            "No se pudo completar la operación. No se confirmó ningún cambio."
        )
        QMessageBox.critical(
            self,
            "Sincronización de credenciales",
            message,
        )

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self.worker = None
        self._set_busy(False)
        if self._close_after_worker:
            self._close_after_worker = False
            self.accept()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
