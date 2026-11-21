"""Human-reviewed queue for commands delivered through the private Structure repo."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.structure_orders import StructureOrderError, StructureOrderService


class StructureOrdersDialog(QDialog):
    """Display pending GitHub orders and apply only the one the user approves."""

    def __init__(
        self,
        dependent_path: str | Path,
        character_manager,
        parent=None,
    ):
        super().__init__(parent)
        self.dependent_path = Path(dependent_path)
        self.character_manager = character_manager
        self.orders_applied = False
        self.service = StructureOrderService(
            dependent_path=self.dependent_path,
            character_manager=character_manager,
        )
        self.entries = []

        self.setWindowTitle("Órdenes de GitHub · Structure")
        self.setModal(True)
        self.resize(900, 590)
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
            QListWidget, QTextEdit {{
                background-color: #1e1e1e;
                border: 1px solid #444444;
                border-radius: 4px;
                color: {Theme.TEXT_WHITE};
                padding: 5px;
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px 12px;
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
        """)

        self._build_ui()
        self._reload_orders()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Órdenes recibidas desde el repositorio privado Structure")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        explanation = QLabel(
            "Las órdenes no se ejecutan automáticamente. Selecciona una, revisa "
            "su destino y los campos afectados y pulsa Aplicar solo después de "
            "aprobarla. Debes descargar primero los cambios de GitHub desde la "
            "ventana de sincronización para recibir órdenes nuevas."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        body = QHBoxLayout()
        self.order_list = QListWidget()
        self.order_list.setMinimumWidth(300)
        self.order_list.currentRowChanged.connect(self._show_selected_order)
        body.addWidget(self.order_list, 1)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Selecciona una orden para ver su contenido.")
        body.addWidget(self.preview, 2)
        layout.addLayout(body, 1)

        safety = QLabel(
            "Protección activa: no existen órdenes de eliminar, borrar, mover o "
            "renombrar. Los JSON existentes se respaldan localmente antes de "
            "actualizarse. Crear directorios no reemplaza contenido existente."
        )
        safety.setWordWrap(True)
        safety.setStyleSheet(
            "color: #bdbdbd; background-color: #252525; "
            "border: 1px solid #444444; border-radius: 4px; padding: 8px;"
        )
        layout.addWidget(safety)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        footer = QHBoxLayout()
        self.refresh_button = QPushButton("Actualizar lista")
        self.refresh_button.clicked.connect(self._reload_orders)
        footer.addWidget(self.refresh_button)

        footer.addStretch()
        self.apply_button = QPushButton("Aplicar orden aprobada")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self._apply_selected_order)
        footer.addWidget(self.apply_button)

        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

    def _reload_orders(self):
        self.entries = self.service.load_pending_orders()
        self.order_list.blockSignals(True)
        self.order_list.clear()

        for entry in self.entries:
            if entry["error"]:
                label = f"INVÁLIDA · {entry['path'].name}"
            else:
                order = entry["validated"]
                label = f"{order['title']}  [{order['id']}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry["path"].name)
            if entry["error"]:
                item.setForeground(Qt.GlobalColor.red)
            self.order_list.addItem(item)

        self.order_list.blockSignals(False)
        if self.entries:
            self.order_list.setCurrentRow(0)
        else:
            self.preview.setPlainText(
                "No hay órdenes pendientes en el checkout local de Structure.\n\n"
                "Comprueba el indicador de statusbar. Si muestra PULL, abre "
                "Sincronizar Structure con GitHub y descarga los cambios remotos. "
                "Después vuelve a abrir esta ventana."
            )
            self.apply_button.setEnabled(False)

        self.status_label.setText(
            f"Órdenes pendientes encontradas: {len(self.entries)}"
        )

    def _show_selected_order(self, row: int):
        if row < 0 or row >= len(self.entries):
            self.apply_button.setEnabled(False)
            return

        entry = self.entries[row]
        if entry["error"]:
            self.preview.setPlainText(
                f"Archivo: {entry['path']}\n\n"
                "La orden no se puede aplicar porque no superó la validación:\n"
                f"{entry['error']}"
            )
            self.apply_button.setEnabled(False)
            return

        validated = entry["validated"]
        order = entry["order"]
        self.preview.setPlainText(
            f"Título: {validated['title']}\n"
            f"ID: {validated['id']}\n"
            f"Descripción: {validated['description']}\n"
            f"Creada: {order.get('created_at', '')}\n\n"
            f"{self.service.describe_order(validated)}\n\n"
            "La operación requiere tu aprobación explícita."
        )
        self.apply_button.setEnabled(True)

    def _apply_selected_order(self):
        row = self.order_list.currentRow()
        if row < 0 or row >= len(self.entries):
            return
        entry = self.entries[row]
        if entry["error"] or not entry["validated"]:
            return

        validated = entry["validated"]
        confirmation = QMessageBox(self)
        confirmation.setIcon(QMessageBox.Icon.Warning)
        confirmation.setWindowTitle("Confirmar aplicación de orden")
        confirmation.setText(
            f"¿Aplicar la siguiente orden?\n\n"
            f"{validated['title']}\n"
            f"{self.service.describe_order(validated)}"
        )
        confirmation.setInformativeText(
            "Los archivos JSON existentes se respaldarán antes de modificarlos. "
            "No se ejecutarán acciones de eliminación."
        )
        apply_button = confirmation.addButton(
            "Aplicar orden",
            QMessageBox.ButtonRole.AcceptRole,
        )
        confirmation.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        confirmation.setDefaultButton(apply_button)
        confirmation.exec()
        if confirmation.clickedButton() is not apply_button:
            return

        self.apply_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        try:
            result = self.service.apply_order(entry["order"])
        except (StructureOrderError, OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                "No se pudo aplicar la orden",
                str(error),
            )
            self.status_label.setText("La orden no se aplicó.")
        except Exception as error:
            QMessageBox.critical(
                self,
                "Error al aplicar la orden",
                f"Se produjo un error inesperado:\n{error}",
            )
            self.status_label.setText("La orden pudo quedar parcialmente aplicada. Revisa el destino y el respaldo local.")
        else:
            self.orders_applied = True
            self.status_label.setText(
                f"Orden {result['order_id']} aplicada. "
                "Se guardó un resultado local en Structure."
            )
            QMessageBox.information(
                self,
                "Orden aplicada",
                "La orden se aplicó correctamente.\n\n"
                "El resultado quedó en el checkout local de Structure; "
                "usa Subir cambios para publicarlo en GitHub.",
            )
            self._reload_orders()
        finally:
            self.apply_button.setEnabled(
                0 <= self.order_list.currentRow() < len(self.entries)
                and not self.entries[self.order_list.currentRow()]["error"]
            )
            self.refresh_button.setEnabled(True)
