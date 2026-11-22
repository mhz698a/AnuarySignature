"""Settings dialog to synchronize folders.json with the physical year directories."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.year_structure_sync import YearStructureSyncService


class _YearStructureSyncWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service: YearStructureSyncService, operation: str):
        super().__init__()
        self.service = service
        self.operation = operation

    def run(self) -> None:
        try:
            if self.operation == "preview":
                result = self.service.preview()
            else:
                result = self.service.synchronize()
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.completed.emit(result)


class YearStructureSyncDialog(QDialog):
    """Preview the union of year directories before replacing folders.json."""

    def __init__(
        self,
        dependent_root: str | Path,
        folders_json_path: str | Path,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = YearStructureSyncService(
            dependent_root,
            folders_json_path,
        )
        self._worker: _YearStructureSyncWorker | None = None
        self._operation = ""
        self._preview_result: dict[str, Any] | None = None
        self.sync_result: dict[str, Any] | None = None

        self.setWindowTitle("Sincronizar folders.json")
        self.setModal(True)
        self.setMinimumSize(680, 560)
        self.resize(760, 640)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QPlainTextEdit {{
                background-color: #1e1e1e;
                color: {Theme.TEXT_WHITE};
                border: 1px solid #454545;
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas;
                font-size: 10px;
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
            QPushButton:disabled {{
                color: #777777;
                border-color: #333333;
            }}
            """
        )

        self._build_ui()
        self._start_worker("preview")

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        description = QLabel(
            "Reconstruye folders.json a partir de las carpetas físicas de todos "
            "los años. Una categoría o subcarpeta se conserva mientras exista "
            "en al menos un año; los prefijos numéricos se normalizan."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.summary_label = QLabel("Preparando el análisis de años…")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText(
            "La estructura reconstruida aparecerá aquí."
        )
        layout.addWidget(self.preview_edit, 1)

        self.status_label = QLabel("Analizando la unidad dependiente…")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.rescan_button = QPushButton("Volver a analizar")
        self.rescan_button.clicked.connect(
            lambda: self._start_worker("preview")
        )
        buttons.addWidget(self.rescan_button)

        self.apply_button = QPushButton("Aplicar a folders.json")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._confirm_and_apply)
        buttons.addWidget(self.apply_button)

        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button)

        layout.addLayout(buttons)

    def _start_worker(self, operation: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._operation = operation
        if operation == "preview":
            self.sync_result = None
        self._set_busy(True)
        self.status_label.setText(
            "Analizando todos los años…"
            if operation == "preview"
            else "Respaldando y actualizando folders.json…"
        )
        worker = _YearStructureSyncWorker(self.service, operation)
        self._worker = worker
        worker.completed.connect(self._on_worker_completed)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        worker.start()

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.rescan_button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        self.apply_button.setEnabled(
            not busy
            and self._preview_result is not None
            and bool(self._preview_result.get("changed"))
            and not bool(
                self.sync_result and self.sync_result.get("written")
            )
        )

    def _on_worker_completed(self, result: object) -> None:
        if not isinstance(result, dict):
            self._on_worker_failed("El servicio devolvió un resultado no válido.")
            return

        if self._operation == "preview":
            self._preview_result = result
            self._display_result(result)
            self.status_label.setText(
                "Análisis terminado. No se ha modificado folders.json."
            )
            return

        self.sync_result = result
        self._preview_result = result
        self._display_result(result)
        if result.get("written"):
            self.status_label.setText(
                "folders.json actualizado. El cambio queda local en Structure "
                "y todavía no se ha subido a GitHub."
            )
            backup_path = result.get("backup_path")
            self.status_label.setToolTip(
                f"Respaldo anterior: {backup_path}"
                if backup_path
                else "No existía un folders.json anterior que respaldar."
            )
        else:
            self.status_label.setText(str(result.get("message", "Sin cambios.")))
            self.status_label.setToolTip("")

    def _on_worker_failed(self, message: str) -> None:
        self._preview_result = None
        self.apply_button.setEnabled(False)
        self.summary_label.setText("No se pudo completar la sincronización.")
        self.preview_edit.setPlainText(message)
        self.status_label.setText("folders.json permanece sin cambios.")
        self.status_label.setToolTip(message)

    def _on_worker_finished(self) -> None:
        self._set_busy(False)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _display_result(self, result: dict[str, Any]) -> None:
        added_categories = result.get("added_categories", [])
        removed_categories = result.get("removed_categories", [])
        added_subfolders = result.get("added_subfolders", [])
        removed_subfolders = result.get("removed_subfolders", [])
        self.summary_label.setText(
            f"Años examinados: {result.get('year_count', 0)} "
            f"({', '.join(result.get('years', []))})   |   "
            f"Categorías: {result.get('category_count', 0)}   |   "
            f"Subcarpetas: {result.get('subfolder_count', 0)}\\n"
            f"Categorías nuevas: {len(added_categories)}   |   "
            f"Categorías retiradas: {len(removed_categories)}   |   "
            f"Subcarpetas nuevas: {len(added_subfolders)}   |   "
            f"Subcarpetas retiradas: {len(removed_subfolders)}"
        )

        diff_lines = ["CAMBIOS DETECTADOS"]
        diff_lines.append(
            "Categorías nuevas: "
            + (", ".join(added_categories) if added_categories else "ninguna")
        )
        diff_lines.append(
            "Categorías retiradas: "
            + (", ".join(removed_categories) if removed_categories else "ninguna")
        )
        diff_lines.append(
            "Subcarpetas nuevas: "
            + (
                ", ".join(
                    f"{item['category']}/{item['name']}"
                    for item in added_subfolders
                )
                if added_subfolders
                else "ninguna"
            )
        )
        diff_lines.append(
            "Subcarpetas retiradas: "
            + (
                ", ".join(
                    f"{item['category']}/{item['name']}"
                    for item in removed_subfolders
                )
                if removed_subfolders
                else "ninguna"
            )
        )
        diff_lines.extend(
            [
                "",
                "FOLDERS.JSON PROPUESTO",
                json.dumps(
                    result.get("folders_data", {}),
                    indent=2,
                    ensure_ascii=False,
                ),
            ]
        )
        self.preview_edit.setPlainText("\\n".join(diff_lines))

    def _confirm_and_apply(self) -> None:
        result = self._preview_result
        if result is None or not result.get("changed"):
            return

        removed_categories = result.get("removed_categories", [])
        removed_subfolders = result.get("removed_subfolders", [])
        details = [
            "Se reconstruirá folders.json con la unión de las carpetas "
            "encontradas en todos los años.",
            "",
            "Las categorías y subcarpetas que ya no existan en ningún año "
            "se retirarán del JSON. Las que sigan presentes al menos en un "
            "año se conservarán.",
        ]
        if removed_categories or removed_subfolders:
            details.extend(
                [
                    "",
                    f"Categorías que se retirarán: {len(removed_categories)}",
                    f"Subcarpetas que se retirarán: {len(removed_subfolders)}",
                ]
            )
        details.extend(
            [
                "",
                "El folders.json actual se respaldará antes de reemplazarlo. "
                "No se modificará ninguna carpeta de los años ni se hará "
                "push automático a GitHub.",
                "",
                "¿Aplicar los cambios?",
            ]
        )
        reply = QMessageBox.question(
            self,
            "Confirmar sincronización",
            "\n".join(details),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_worker("sync")

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
