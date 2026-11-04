# domain_visor/domain_item.py

import json
from pathlib import Path
from PyQt6.QtCore import QRectF, Qt, QLineF
from PyQt6.QtGui import QFont, QFontMetrics, QPen, QBrush, QColor, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox

from domain_visor.theme import Theme


class DomainNameDialog(QDialog):
    """
    Diálogo modal para modificar el nombre de un dominio en infrastructure.json.
    """
    def __init__(self, domain_id, current_name, infrastructure_path, parent=None):
        super().__init__(parent)
        self.domain_id = domain_id
        self.current_name = current_name
        self.infrastructure_path = Path(infrastructure_path) if infrastructure_path else None
        self.saved = False

        self.setWindowTitle("Modificar Nombre del Dominio")
        self.setModal(True)
        self.setMinimumWidth(400)

        # Quitar botón de ayuda
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Estilo coherente con el tema oscuro de la aplicación
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: #85c1e9;
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
            QPushButton:pressed {{
                background-color: #1e1e1e;
            }}
        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Nombre del dominio:"))

        # Formato inicial: minúsculas y con guiones bajos
        initial_text = self.current_name.lower().replace(" ", "_")
        self.txt_name = QLineEdit(initial_text)
        self.txt_name.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.txt_name)

        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_data)
        self.btn_discard = QPushButton("Descartar")
        self.btn_discard.clicked.connect(self.reject)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_discard)
        layout.addLayout(footer_layout)

    def _on_text_changed(self):
        text = self.txt_name.text()
        new_text = text.replace(" ", "_").lower()
        if text != new_text:
            cursor_pos = self.txt_name.cursorPosition()
            self.txt_name.blockSignals(True)
            self.txt_name.setText(new_text)
            self.txt_name.setCursorPosition(cursor_pos)
            self.txt_name.blockSignals(False)

    def save_data(self):
        new_name = self.txt_name.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Validación", "El nombre del dominio no puede estar vacío.")
            return

        if not self.infrastructure_path or not self.infrastructure_path.exists():
            QMessageBox.critical(self, "Error", "No se encontró la ruta del archivo de infraestructura.")
            return

        try:
            with open(self.infrastructure_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            updated = False
            for sd in data:
                for dom in sd.get("domains", []):
                    # Coincidir por id si id > 0, o por nombre actual
                    if (self.domain_id and dom.get("id") == self.domain_id) or (dom.get("domain") == self.current_name):
                        dom["domain"] = new_name
                        updated = True
                        break
                if updated:
                    break

            if updated:
                with open(self.infrastructure_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.saved = True
                self.accept()
            else:
                QMessageBox.warning(self, "Error", f"No se encontró el dominio '{self.current_name}' en el JSON.")
        except Exception as e:
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar infrastructure.json:\n{e}")


class DomainItem(QGraphicsItem):
    """
    Representa un elemento gráfico de dominio o bloque en el diagrama (Paso de Commit 9.1 y 11).
    Responsabilidades:
    - Dibujar un contenedor con fondo y borde recibidos de forma explícita.
    - Dibujar un encabezado con el título del dominio.
    - Dibujar una línea divisora horizontal a una altura fija de 28px.
    - Subrayar el texto del dominio al pasar el mouse por encima.
    - Abrir un diálogo para cambiar el nombre del dominio al hacer clic en el texto.
    """
    def __init__(self, x, y, width, height, title, background_color: str, border_color: str, domain_id: int = 0, infrastructure_path: str = None):
        super().__init__()
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._x = float(x)
        self._y = float(y)
        self._width = float(width)
        self._height = float(height)
        self._title = title
        self._background_color = QColor(background_color)
        self._border_color = QColor(border_color)
        self._domain_id = domain_id
        self._infrastructure_path = infrastructure_path
        self._hovered_title = False

        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        # Retorna el área que cubre este ítem, incluyendo un pequeño margen para el borde
        return QRectF(self._x - 2.0, self._y - 2.0, self._width + 4.0, self._height + 4.0)

    def _get_title_rect(self) -> QRectF:
        font = QFont("Arial", 10, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        formatted_title = self._title.replace("_", " ").title()
        text_width = fm.horizontalAdvance(formatted_title)
        text_height = fm.height()
        text_x = self._x + (self._width - text_width) / 2.0
        text_y = self._y + (28.0 - text_height) / 2.0
        return QRectF(text_x, text_y, text_width, text_height)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        title_rect = self._get_title_rect()
        if title_rect.contains(pos):
            if not self._hovered_title:
                self._hovered_title = True
                self.setCursor(Qt.CursorShape.PointingHandCursor)
                self.update()
        else:
            if self._hovered_title:
                self._hovered_title = False
                self.unsetCursor()
                self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        if self._hovered_title:
            self._hovered_title = False
            self.unsetCursor()
            self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._get_title_rect().contains(event.pos()):
            event.accept()
            self.open_rename_dialog()
        else:
            super().mousePressEvent(event)

    def open_rename_dialog(self):
        parent_widget = None
        if self.scene() and self.scene().views():
            parent_widget = self.scene().views()[0].window()

        infra_path = self._infrastructure_path
        if not infra_path and parent_widget and hasattr(parent_widget, "json_path"):
            infra_path = parent_widget.json_path

        dlg = DomainNameDialog(self._domain_id, self._title, infra_path, parent=parent_widget)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.saved:
            if parent_widget:
                if hasattr(parent_widget, "load_initial_json"):
                    parent_widget.load_initial_json()
                if hasattr(parent_widget, "trigger_render"):
                    parent_widget.trigger_render()

    def paint(self, painter, option, widget=None):
        painter.save()

        # Activar suavizado
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Dibujar el fondo y borde del bloque redondeado usando los colores recibidos
        rect = QRectF(self._x, self._y, self._width, self._height)
        painter.setBrush(QBrush(self._background_color))
        pen = QPen(self._border_color)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 4.0, 4.0)

        # 2. Dibujar la línea divisora horizontal del encabezado a 28px de altura
        divider_y = self._y + 28.0
        painter.drawLine(QLineF(self._x, divider_y, self._x + self._width, divider_y))

        # 3. Dibujar el título del dominio en el encabezado usando el tema centralizado
        font = QFont("Arial", 10, QFont.Weight.Bold)
        if self._hovered_title:
            font.setUnderline(True)
        painter.setFont(font)
        painter.setPen(QColor(Theme.TEXT_WHITE))

        header_rect = QRectF(self._x, self._y, self._width, 28.0)
        formatted_title = self._title.replace("_", " ").title()
        painter.drawText(header_rect, Qt.AlignmentFlag.AlignCenter, formatted_title)

        painter.restore()
