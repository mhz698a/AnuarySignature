# domain_visor/year_item.py
import datetime

from PyQt6.QtCore import QRectF, Qt, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QGraphicsItem

from year_visor.year_creator import trigger_year_creation
from year_visor.year_creator import validate_date_constraints
from year_visor.year_dialog import YearDialog
from domain_visor.port_item import PortItem
from domain_visor.theme import Theme
from character_visor.character_row_item import CharacterRowItem
from character_visor.character_manager import CharacterManager
from year_visor.year_dialog import find_season_name


class YearItem(QGraphicsItem):
    """
    Representa un año individual dentro de un dominio (Paso de Commit 5, 6 y 11).
    Responsabilidades:
    - Dibujar el número del año centrado en la mitad superior de su rectángulo.
    - Dibujar un borde punteado blanco con esquinas redondeadas y sin fondo.
    - Utilizar la fuente del visor actual (Arial 10) y texto del tema.
    - Heredar de QGraphicsItem y asociarse jerárquicamente a su DomainItem padre.
    - Instanciar e incorporar dos puertos (PortItem) de conexión centrado en la fila del año (top 15.0px).
    - Incorporar dinámicamente el CharacterRowItem abajo de la fila de puertos y año si existen personajes.
    - Soportar subrayado al pasar el mouse por encima del número del año y tooltip "{year} - {season_name}".
    - Al hacer clic en el número del año, abrir el diálogo YearDialog.
    """
    # Usar una instancia de CharacterManager estática para la carga en la vista
    _char_manager = None

    @classmethod
    def get_character_manager(cls) -> CharacterManager:
        if cls._char_manager is None:
            cls._char_manager = CharacterManager()
            # Realizar verificación básica al inicio de su uso
            cls._char_manager.verify_cache_at_startup()
        return cls._char_manager

    def __init__(self, x, y, width, height, year_value, parent=None):
        super().__init__(parent)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self._x = float(x)
        self._y = float(y)
        self._width = float(width)
        self._height = float(height)
        self._year_value = year_value

        self._year_hovered = False
        self.setAcceptHoverEvents(True)

        # 1. Instanciar puertos de conexión izquierdo y derecho (siempre en la primera fila de 15.0px)
        port_diameter = 8.0
        # Verticalmente centrados en los primeros 15.0px de altura
        port_y = self._y + (15.0 - port_diameter) / 2.0

        # El puerto izquierdo se ubica cerca del borde izquierdo
        left_port_x = self._x + 4.0
        self.left_port = PortItem(left_port_x, port_y, port_diameter, "left", parent=self)

        # El puerto derecho se ubica cerca del borde derecho
        right_port_x = self._x + self._width - 12.0
        self.right_port = PortItem(right_port_x, port_y, port_diameter, "right", parent=self)

        # 2. Obtener personajes para este año e instanciar CharacterRowItem si existen
        char_manager = self.get_character_manager()
        self._characters = char_manager.get_characters_for_year(self._year_value)

        self.row_item = None
        if self._characters:
            # Ubicación: abajo de la fila de los puertos y el año del year item
            # La fila del año mide 15.0px, sumamos un pequeño espacio/padding de 4px, y luego la fila de personajes
            self.row_item = CharacterRowItem(self._characters, self._width, parent=self)
            self.row_item.setPos(self._x, self._y + 15.0 + 4.0)

    def boundingRect(self) -> QRectF:
        # Retorna el área que cubre este ítem de año (coincide con la altura dinámica calculada en LayoutEngine)
        return QRectF(self._x, self._y, self._width, self._height)

    def is_over_year_number(self, pos: QPointF) -> bool:
        """
        Determina si las coordenadas dadas están dentro de la región del número del año (fila superior de 15.0px).
        """
        return self._x <= pos.x() <= (self._x + self._width) and self._y <= pos.y() <= (self._y + 15.0)

    def hoverEnterEvent(self, event):
        pos = event.pos()
        if self.is_over_year_number(pos):
            self._year_hovered = True
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            # Actualizar Tooltip dinámicamente
            char_mgr = self.get_character_manager()
            
            season_name = find_season_name(self._year_value, char_mgr.base_path)
            season_clean = season_name.replace("_", " ")
            self.setToolTip(f"{self._year_value} - {season_clean}")
        else:
            self._year_hovered = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
        self.update()
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        was_hovered = self._year_hovered
        if self.is_over_year_number(pos):
            self._year_hovered = True
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            # Actualizar Tooltip dinámicamente
            char_mgr = self.get_character_manager()
            season_name = find_season_name(self._year_value, char_mgr.base_path)
            season_clean = season_name.replace("_", " ")
            self.setToolTip(f"{self._year_value} - {season_clean}")
        else:
            self._year_hovered = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.setToolTip("")
        
        if was_hovered != self._year_hovered:
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self._year_hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip("")
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        pos = event.pos()
        if event.button() == Qt.MouseButton.LeftButton and self.is_over_year_number(pos):
            parent_window = None
            if self.scene() and self.scene().views():
                parent_window = self.scene().views()[0].window()
            
            char_mgr = self.get_character_manager()
            year_path = char_mgr.base_path / str(self._year_value)
            
            
            
            # Decidir si aplicamos validación de fecha según si la carpeta del año existe
            # Y si el archivo de credenciales ya existe
            
            temp_dialog = YearDialog(self._year_value, parent_window, base_path=char_mgr.base_path)
            json_exists = temp_dialog.json_filepath.exists()

            if year_path.exists():
                # Si la carpeta del año existe:
                # Solo bloqueamos si es un año en el futuro y NO tiene credenciales creadas todavía
                today = datetime.date.today()
                if self._year_value > today.year and not json_exists:
                    allowed, message = validate_date_constraints(self._year_value)
                else:
                    allowed, message = True, ""
            else:
                # Si no existe, aplicamos la validación estándar de creación
                allowed, message = validate_date_constraints(self._year_value)

            if not allowed:
                from PyQt6.QtWidgets import QMessageBox
                msg_box = QMessageBox(parent_window)
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setWindowTitle("Advertencia")
                msg_box.setText(message)
                msg_box.setStyleSheet(f"""
                    QMessageBox {{
                        background-color: {Theme.APP_BACKGROUND};
                        color: {Theme.TEXT_WHITE};
                    }}
                    QLabel {{
                        color: {Theme.TEXT_WHITE};
                    }}
                    QPushButton {{
                        background-color: #2d2d2d;
                        border: 1px solid #555555;
                        border-radius: 4px;
                        padding: 6px 12px;
                        color: {Theme.TEXT_WHITE};
                        font-weight: bold;
                    }}
                """)
                msg_box.exec()
                event.accept()
                return

            if not year_path.exists():
                success = trigger_year_creation(self._year_value, parent_window, base_path=char_mgr.base_path)
                if success:
                    if parent_window and hasattr(parent_window, "refresh_data"):
                        parent_window.refresh_data()
                    else:
                        self.update()
            else:
                dialog = YearDialog(self._year_value, parent_window)
                if parent_window is not None:
                    from domain_visor.scene_view import VasculumApp
                    if isinstance(parent_window, VasculumApp):
                        dialog.galleryanuary_requested.connect(
                            parent_window.galleryanuary_requested
                        )
                dialog.exec()
                if dialog.saved:
                    self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(self, painter, option, widget=None):
        painter.save()

        # Activar suavizado para texto perfecto y bordes redondeados
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. Dibujar el borde punteado con esquinas redondeadas alrededor de todo el YearItem
        border_pen = QPen(QColor(Theme.TEXT_WHITE))
        border_pen.setStyle(Qt.PenStyle.DotLine)
        border_pen.setWidthF(1.0)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        rect = QRectF(self._x, self._y, self._width, self._height)
        painter.drawRoundedRect(rect, 4.0, 4.0)

        # 2. Dibujar el año centrado horizontalmente en la primera fila de 15.0px
        year_rect = QRectF(self._x, self._y, self._width, 15.0)
        font = QFont("Arial", 10)
        if self._year_hovered:
            font.setUnderline(True)
        painter.setFont(font)
        painter.setPen(QColor(Theme.TEXT_WHITE))
        painter.drawText(year_rect, Qt.AlignmentFlag.AlignCenter, str(self._year_value))

        painter.restore()
