# domain_visor/superdomain_item.py

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QFont, QPen, QBrush, QColor, QPainter
from PyQt6.QtWidgets import QGraphicsItem

from domain_visor.theme import Theme

class SuperDomainItem(QGraphicsItem):
    """
    Representa un contenedor de SuperDomain (Paso de Commit 3/11).
    Responsabilidades:
    - Dibujar un rectángulo redondeado con borde y fondo.
    - Dibujar el título del SuperDomain.
    - No usar sub-elementos de texto (dibujar todo en paint()).
    - Consumir todas las constantes de color desde la clase centralizada Theme.
    """
    def __init__(self, x, y, width, height, title):
        super().__init__()
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._x = float(x)
        self._y = float(y)
        self._width = float(width)
        self._height = float(height)
        self._title = title

    def boundingRect(self) -> QRectF:
        # Retorna el área que cubre este ítem, incluyendo un pequeño margen para el borde
        return QRectF(self._x - 2.0, self._y - 2.0, self._width + 4.0, self._height + 4.0)

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
        painter.setFont(font)
        painter.setPen(QColor(Theme.TEXT_WHITE))

        # Dibujar el título centrado horizontalmente en la parte superior con un pequeño margen
        text_rect = QRectF(self._x, self._y + 12.0, self._width, 30.0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter, self._title)

        painter.restore()
