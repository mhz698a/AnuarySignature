# domain_visor/cable_item.py

from PyQt6.QtCore import QRectF, Qt, QPointF
from PyQt6.QtGui import QPen, QColor, QPainterPath, QPainter, QPainterPathStroker
from PyQt6.QtWidgets import QGraphicsPathItem

from domain_visor.theme import Theme
from year_visor.year_dialog import ConnectionRenameDialog


class CableItem(QGraphicsPathItem):
    """
    Representa un cable de conexión S-shaped entre dos puertos (Paso de Commit 9/11).
    Responsabilidades:
    - Heredar de QGraphicsPathItem.
    - Recibir dos PortItem (from_port, to_port) y el objeto Connection correspondiente.
    - Calcular el camino curvo (cúbico Bézier) entre los centros de ambos puertos.
    - Configurar un estilo de lápiz neutral obteniendo el color desde Theme.
    - Mostrar un tooltip interactivo y facilitar su selección con un área de colisión (hitbox) ensanchada (Paso 3).
    - Soporta brillo/highlight en hover.
    - Al hacer clic, abre un diálogo para cambiar el nombre, actualizando el JSON de infraestructura.
    """
    def __init__(self, from_port, to_port, connection, is_special=False, parent=None, json_path=None):
        super().__init__(parent)
        self.from_port = from_port
        self.to_port = to_port
        self.connection = connection
        self.is_special = is_special
        self.json_path = json_path
        self._hovered = False

        # Establecer un zValue alto para que los cables se rendericen por encima de los bloques
        self.setZValue(15.0)

        # Generar el camino inicial
        self.update_path()

        # Configurar Tooltip, Habilitar Hover y cursor de mano (Paso 3)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_tooltip()

    def update_tooltip(self):
        if self.connection.name:
            tooltip_text = f"{self.connection.name} ({self.connection.from_year} → {self.connection.to_year})"
        else:
            tooltip_text = f"{self.connection.from_year} → {self.connection.to_year}"
        self.setToolTip(tooltip_text)

    def update_path(self):
        """
        Calcula la curva Bézier cúbica basándose en la posición absoluta
        en la escena de los centros de los puertos.
        """
        if self.is_special:
            # Determine upper (right) port and lower (left) port
            if self.from_port._side == "right":
                p_right_upper = QPointF(self.from_port._x + 4.0, self.from_port._y + 4.0)
                p_left_lower = QPointF(self.to_port._x + 4.0, self.to_port._y + 4.0)
            else:
                p_right_upper = QPointF(self.to_port._x + 4.0, self.to_port._y + 4.0)
                p_left_lower = QPointF(self.from_port._x + 4.0, self.from_port._y + 4.0)

            # Calculate mid Y in the gap
            y_gap = (p_right_upper.y() + p_left_lower.y()) / 2.0 - 14.0

            # Build path from p_right_upper -> loop right -> cross left -> loop left -> p_left_lower
            path = QPainterPath()
            path.moveTo(p_right_upper)

            # Loop right and down to y_gap with horizontal tangents (perfectly rounded)
            # Bulges out to x + 35.0, then curves back to x + 15.0
            c1_a = QPointF(p_right_upper.x() + 40.0, p_right_upper.y())
            c1_b = QPointF(p_right_upper.x() + 40.0, y_gap)
            p_mid_right = QPointF(p_right_upper.x() + 3.0, y_gap)
            path.cubicTo(c1_a, c1_b, p_mid_right)

            # Cross horizontally to the left side
            p_mid_left = QPointF(p_left_lower.x() - 3.0, y_gap)
            path.lineTo(p_mid_left)

            # Loop down and right into p_left_lower with horizontal tangents (perfectly rounded)
            # Curves from x - 15.0 to x - 35.0, then into the left port
            c2_a = QPointF(p_left_lower.x() - 40.0, y_gap)
            c2_b = QPointF(p_left_lower.x() - 40.0, p_left_lower.y())
            path.cubicTo(c2_a, c2_b, p_left_lower)

            self.setPath(path)
        else:
            # 1. Calcular los centros de los círculos de puerto usando sus coordenadas absolutas
            p1 = QPointF(self.from_port._x + 4.0, self.from_port._y + 4.0)
            p2 = QPointF(self.to_port._x + 4.0, self.to_port._y + 4.0)

            # 2. Determinar los puntos de control para la curva Bézier horizontal (S-shaped)
            offset_from = 50.0 if self.from_port._side == "right" else -50.0
            offset_to = -50.0 if self.to_port._side == "left" else 50.0

            c1 = QPointF(p1.x() + offset_from, p1.y())
            c2 = QPointF(p2.x() + offset_to, p2.y())

            # 3. Construir el QPainterPath
            path = QPainterPath()
            path.moveTo(p1)
            path.cubicTo(c1, c2, p2)

            self.setPath(path)

        # 4. Configurar el estilo del cable usando el color centralizado de Theme
        width = 2.0
        if self.connection:
            if self.connection.type == "mesolazo_domain_to_domain":
                color = Theme.CABLE_SPECIAL_COLOR
            elif self.connection.type == "deuterolazo_de_andrea_cloe":
                color = Theme.CABLE_DEUTEROLAZO_COLOR
                width = 4.0
            elif self.connection.type == "exolazo":
                color = Theme.CABLE_EXOLAZO_COLOR
                width = 4.0
            elif self.connection.type in ("superlazo", "supercable"):
                color = Theme.CABLE_SUPERCABLE_COLOR
                width = 4.0
            else:
                color = Theme.CABLE_COLOR
        else:
            color = Theme.CABLE_COLOR

        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def shape(self) -> QPainterPath:
        """
        Retorna una forma de colisión más ancha para facilitar que el mouse
        pase por encima del cable (Paso 3).
        """
        stroker = QPainterPathStroker()
        stroker.setWidth(10.0)  # Genera un área de interacción invisible de 10px de ancho
        return stroker.createStroke(self.path())

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            parent_window = None
            if self.scene() and self.scene().views():
                parent_window = self.scene().views()[0].window()

            # Resolver ruta del JSON de infraestructura si no se ha asignado aún
            json_path = self.json_path
            if not json_path and parent_window and hasattr(parent_window, "json_path"):
                json_path = parent_window.json_path

            if json_path:
                dialog = ConnectionRenameDialog(self.connection, json_path, parent_window)
                dialog.exec()
                if dialog.saved:
                    # Forzar recarga de infraestructura en el árbol y re-renderizado de escena
                    if parent_window:
                        parent_window.load_initial_json()
                        parent_window.trigger_render()
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(self, painter, option, widget=None):
        if self._hovered:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Dibujar el brillo/glow de fondo
            glow_pen = QPen(self.pen())
            glow_pen.setWidthF(self.pen().widthF() + 6.0)
            
            color = self.pen().color()
            glow_color = QColor(color.red(), color.green(), color.blue(), 100) # Alfa semi-transparente
            glow_pen.setColor(glow_color)
            
            painter.setPen(glow_pen)
            painter.drawPath(self.path())
            painter.restore()

        super().paint(painter, option, widget)
