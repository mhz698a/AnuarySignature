# domain_visor/superdomain_item.py

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetrics, QPen, QBrush, QColor, QPainter
from PyQt6.QtWidgets import QDialog, QGraphicsItem

from domain_visor.theme import Theme
from domain_visor.superdomain_rename_dialog import SuperDomainRenameDialog

class SuperDomainItem(QGraphicsItem):
    """
    Representa un contenedor de SuperDomain (Paso de Commit 3/11).
    Responsabilidades:
    - Dibujar un rectángulo redondeado con borde y fondo.
    - Dibujar el título del SuperDomain.
    - No usar sub-elementos de texto (dibujar todo en paint()).
    - Consumir todas las constantes de color desde la clase centralizada Theme.
    """
    def __init__(
        self,
        x,
        y,
        width,
        height,
        title,
        superdomain_name=None,
        superdomain_id: int = 0,
        infrastructure_path=None,
    ):
        super().__init__()
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._x = float(x)
        self._y = float(y)
        self._width = float(width)
        self._height = float(height)
        self._title = title
        self._superdomain_name = str(superdomain_name or title)
        self._superdomain_id = superdomain_id
        self._infrastructure_path = infrastructure_path
        self._hovered_title = False
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        # Retorna el área que cubre este ítem, incluyendo un pequeño margen para el borde
        return QRectF(self._x - 2.0, self._y - 2.0, self._width + 4.0, self._height + 4.0)

    def _get_title_rect(self) -> QRectF:
        font = QFont("Arial", 11, QFont.Weight.Bold)
        metrics = QFontMetrics(font)
        text_width = metrics.horizontalAdvance(self._title)
        text_height = metrics.height()
        text_x = self._x + (self._width - text_width) / 2.0
        text_y = self._y + 12.0 + (30.0 - text_height) / 2.0
        return QRectF(text_x, text_y, text_width, text_height)

    def hoverMoveEvent(self, event):
        hovered = self._get_title_rect().contains(event.pos())
        if hovered != self._hovered_title:
            self._hovered_title = hovered
            if hovered:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
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
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._get_title_rect().contains(event.pos())
        ):
            event.accept()
            self.open_rename_dialog()
            return
        super().mousePressEvent(event)

    def open_rename_dialog(self):
        parent_window = None
        if self.scene() and self.scene().views():
            parent_window = self.scene().views()[0].window()

        infrastructure_path = self._infrastructure_path
        if (
            not infrastructure_path
            and parent_window is not None
            and hasattr(parent_window, "json_path")
        ):
            infrastructure_path = parent_window.json_path

        dialog = SuperDomainRenameDialog(
            self._superdomain_id,
            self._superdomain_name,
            infrastructure_path,
            parent=parent_window,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved:
            if parent_window is not None:
                if callable(getattr(parent_window, "load_initial_json", None)):
                    parent_window.load_initial_json()
                if callable(getattr(parent_window, "trigger_render", None)):
                    parent_window.trigger_render()

    def paint(self, painter, option, widget=None):
        painter.save()

        # Activar suavizado para bordes y texto perfectos
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Definir el rectángulo principal
        rect = QRectF(self._x, self._y, self._width, self._height)

        # Configurar colores para el fondo y el borde desde Theme
        bg_color = QColor(Theme.SUPERDOMAIN_BG)
        border_color = QColor(Theme.SUPERDOMAIN_BORDER)

        painter.setBrush(QBrush(bg_color))
        pen = QPen(border_color)
        pen.setWidthF(1.5)
        painter.setPen(pen)

        # Dibujar el rectángulo redondeado
        painter.drawRoundedRect(rect, 5.0, 5.0)

        # Configurar la fuente para el título (Arial 11 Bold, color blanco del tema)
        font = QFont("Arial", 11, QFont.Weight.Bold)
        if self._hovered_title:
            font.setUnderline(True)
        painter.setFont(font)
        painter.setPen(QColor(Theme.TEXT_WHITE))

        # Dibujar el título centrado horizontalmente en la parte superior con un pequeño margen
        text_rect = QRectF(self._x, self._y + 12.0, self._width, 30.0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, self._title)

        painter.restore()
