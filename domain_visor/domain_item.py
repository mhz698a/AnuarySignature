# domain_visor/domain_item.py

from pathlib import Path
from PyQt6.QtCore import QRectF, Qt, QLineF
from PyQt6.QtGui import QFont, QFontMetrics, QPen, QBrush, QColor, QPainter
from PyQt6.QtWidgets import QGraphicsItem, QDialog

from domain_visor.theme import Theme
from domain_visor.domain_management_dialog import DomainManagementDialog


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
    def __init__(
        self,
        x,
        y,
        width,
        height,
        title,
        background_color: str,
        border_color: str,
        domain_id: int = 0,
        infrastructure_path: str = None,
        domain_years=None,
    ):
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
        self._domain_years = sorted(
            {int(year) for year in (domain_years or [])}
        )
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

        base_path = (
            getattr(parent_widget, "dependent_path", None)
            if parent_widget is not None
            else None
        )
        dialog = DomainManagementDialog(
            domain_id=self._domain_id,
            current_name=self._title,
            infrastructure_path=infra_path,
            base_path=base_path or Path("E:/_Internal"),
            years=self._domain_years,
            parent=parent_widget,
        )
        dialog.exec()
        if dialog.saved:
            if parent_widget is not None:
                if callable(getattr(parent_widget, "load_initial_json", None)):
                    parent_widget.load_initial_json()
                if callable(getattr(parent_widget, "trigger_render", None)):
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
