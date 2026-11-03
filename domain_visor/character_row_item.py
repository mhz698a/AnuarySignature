# domain_visor/character_row_item.py

import os
from pathlib import Path
from PyQt6.QtCore import QRectF, Qt, QUrl
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPixmap, QDesktopServices, QAction
from PyQt6.QtWidgets import QGraphicsItem, QToolTip, QMenu, QMessageBox

from domain_visor.theme import Theme

# Caché global en memoria para las imágenes pre-cargadas en el hilo secundario
PIXMAP_CACHE = {}


def resolve_character_icon_path(char_data):
    """Resuelve el archivo de imagen tomando el JSON del personaje como referencia."""
    icon_path = str(char_data.get("icon_path", "")).strip()
    if not icon_path:
        return ""

    image_path = Path(icon_path).expanduser()
    if image_path.is_absolute():
        return str(image_path.resolve())

    json_path_str = char_data.get("character_json_path", "")
    if json_path_str:
        base_dir = Path(json_path_str).parent
    else:
        # Compatibilidad temporal con registros anteriores a character_json_path.
        legacy_dir = char_data.get("character_path", "")
        if not legacy_dir:
            return ""
        base_dir = Path(legacy_dir)

    return str((base_dir / image_path).resolve())

class CharacterIconItem(QGraphicsItem):
    """
    Representa un cuadrado individual de perfil de personaje de 20x20px.
    """
    def __init__(self, char_data, parent=None):
        super().__init__(parent)
        self.char_data = char_data
        self._size = 20.0

        # Cargar datos del personaje
        self.position = char_data.get("position", 1)
        self.name = char_data.get("name", "")
        self.alterego = char_data.get("alterego", "")
        self.icon_path = char_data.get("icon_path", "")
        self.character_json_path = char_data.get("character_json_path", "")

        # Formatear el Tooltip (requisito 5): "{name} - {alterego}"
        # Transformación nombre propio (Title Case) y sin guiones bajos
        self.update_tooltip_and_attributes(char_data)

        # Cargar pixmap de forma segura usando la caché global pre-cargada
        self.load_pixmap()

        # Configurar cursor apuntador para interacción (requisito clásico)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_tooltip_and_attributes(self, char_data):
        self.position = char_data.get("position", 1)
        self.name = char_data.get("name", "")
        self.alterego = char_data.get("alterego", "")
        self.icon_path = char_data.get("icon_path", "")
        self.character_json_path = char_data.get("character_json_path", "")

        formatted_name = self.name.replace("_", " ").strip().title()
        formatted_alterego = self.alterego.replace("_", " ").strip().title()

        if not formatted_name:
            formatted_name = "?"
        if not formatted_alterego:
            formatted_alterego = "?"

        tooltip_text = f"{formatted_name} - {formatted_alterego}"
        self.setToolTip(tooltip_text)

    def load_pixmap(self):
        self.pixmap = None
        full_img_path = resolve_character_icon_path(self.char_data)
        if full_img_path:
            if full_img_path in PIXMAP_CACHE:
                self.pixmap = PIXMAP_CACHE[full_img_path]
            elif Path(full_img_path).is_file():
                self.pixmap = QPixmap(full_img_path)
                PIXMAP_CACHE[full_img_path] = self.pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.view_profile_credential()
            event.accept()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        view = None
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                view = views[0]

        menu = QMenu(view)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #1e1e1e;
                color: {Theme.TEXT_WHITE};
                border: 1px solid #3e3e42;
                font-family: Arial;
                font-size: 11px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: #2d2d2d;
                color: #ffffff;
            }}
        """)

        open_folder_act = QAction("Abrir carpeta del perfil", menu)
        open_folder_act.triggered.connect(self.open_profile_folder)
        menu.addAction(open_folder_act)

        view_credential_act = QAction("Ver credencial del perfil", menu)
        view_credential_act.triggered.connect(self.view_profile_credential)
        menu.addAction(view_credential_act)

        galleryanuary_act = QAction("Abrir carpeta con GalleryAnuary", menu)
        galleryanuary_act.triggered.connect(
            self.open_profile_folder_with_galleryanuary
        )
        menu.addAction(galleryanuary_act)

        if event:
            menu.exec(event.screenPos())
            event.accept()

    def open_profile_folder_with_galleryanuary(self):
        """Envía la carpeta del perfil a GalleryAnuary a través de la señal principal."""
        json_path_str = self.character_json_path
        if not json_path_str:
            QMessageBox.warning(None, "GalleryAnuary", "El perfil no tiene una ruta de credencial.")
            return

        profile_dir = Path(json_path_str).parent
        if not profile_dir.is_dir():
            QMessageBox.warning(None, "GalleryAnuary", f"No se encontró la carpeta:\n{profile_dir}")
            return

        scene = self.scene()
        views = scene.views() if scene else []
        if not views:
            QMessageBox.warning(None, "GalleryAnuary", "No hay una ventana asociada al visor.")
            return

        from domain_visor.scene_view import VasculumApp
        main_window = views[0].window()
        if not isinstance(main_window, VasculumApp):
            QMessageBox.warning(
                views[0],
                "GalleryAnuary",
                "La ventana del visor no expone la señal de integración con GalleryAnuary."
            )
            return

        main_window.galleryanuary_requested.emit(str(profile_dir.resolve()))

    def open_profile_folder(self):
        json_path_str = self.character_json_path
        profile_dir = Path(json_path_str).parent if json_path_str else None
        if profile_dir and profile_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(profile_dir.resolve())))
            return

        view = None
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                view = views[0]
        msg = QMessageBox(view)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Advertencia")
        msg.setText(f"No se encontró la ubicación de la credencial:\n{json_path_str}")
        msg.setStyleSheet(f"""
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
        msg.exec()

    def view_profile_credential(self):
        from domain_visor.character_dialog import CharacterEditDialog
        view = None
        scene = self.scene()
        if scene:
            views = scene.views()
            if views:
                view = views[0]

        old_name = self.name
        old_character_json_path = self.character_json_path
        old_img_path = resolve_character_icon_path(self.char_data)

        dialog = CharacterEditDialog(self.char_data, parent=view)
        if view is not None:
            from domain_visor.scene_view import VasculumApp
            main_window = view.window()
            if isinstance(main_window, VasculumApp):
                dialog.galleryanuary_requested.connect(
                    main_window.galleryanuary_requested
                )

        if dialog.exec() == CharacterEditDialog.DialogCode.Accepted and dialog.saved:
            new_data = dialog.char_data

            self.char_data.clear()
            self.char_data.update(new_data)

            if old_img_path:
                PIXMAP_CACHE.pop(old_img_path, None)

            self.update_tooltip_and_attributes(new_data)
            self.load_pixmap()

            from domain_visor.year_item import YearItem
            mgr = YearItem.get_character_manager()
            year_str = str(new_data.get("year"))
            if year_str in mgr._cache:
                for idx, char in enumerate(mgr._cache[year_str]):
                    if char.get("character_json_path") == old_character_json_path or char.get("name") == old_name:
                        mgr._cache[year_str][idx] = new_data.copy()
                        break
                mgr.save_cache_file()

            self.update()

            main_window = None
            if view:
                parent_widget = view.parent()
                while parent_widget:
                    from domain_visor.scene_view import VasculumApp
                    if isinstance(parent_widget, VasculumApp):
                        main_window = parent_widget
                        break
                    parent_widget = parent_widget.parent()

            if main_window:
                main_window.trigger_render()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._size, self._size)

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(0, 0, self._size, self._size)

        # 1. Dibujar Imagen o "?" (requisito 4)
        if self.pixmap and not self.pixmap.isNull():
            # Obtener dimensiones originales de la imagen
            w = self.pixmap.width()
            h = self.pixmap.height()

            # Recortar en ratio 1:1, asegurando que el recorte sea en la parte superior (top)
            side = min(w, h)

            # Calcular origen del recorte
            # Si w > h (es landscape), centramos horizontalmente en x, pero y empieza en 0 (parte de arriba)
            # Si w < h (es portrait) o w == h, x empieza en 0, e y empieza en 0 (parte de arriba)
            x_src = int((w - side) / 2) if w > h else 0
            y_src = 0

            # Dibujar el fragmento recortado escalándolo a la caja de 20x20px
            painter.drawPixmap(rect.toRect(), self.pixmap, QRectF(x_src, y_src, side, side).toRect())
        else:
            # Mostrar icono de "?" con texto "{position}?"
            painter.setBrush(QBrush(QColor("#2d2d2d")))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)

            font = QFont("Arial", 8, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(Theme.TEXT_WHITE))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.position}?")

        # 2. El cuadrado tendrá un contorno delgado pero visible (requisito 6)
        border_pen = QPen(QColor(Theme.TEXT_WHITE))
        border_pen.setWidthF(1.0)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawRect(rect)

        painter.restore()


class CharacterRowItem(QGraphicsItem):
    """
    Contenedor de perfiles/personajes distribuidos en el centro de la fila.
    """
    def __init__(self, characters_data, width, parent=None):
        super().__init__(parent)
        self.characters_data = characters_data
        self._width = float(width)
        self._height = 20.0
        self.icons = []

        # Instanciar hasta 6 perfiles
        count = len(characters_data)
        if count > 0:
            total_icons_width = count * 20.0 + (count - 1) * 5.0
            # Distribuir centrado dentro del ancho total
            start_x = (self._width - total_icons_width) / 2.0

            for idx, char_data in enumerate(characters_data):
                icon_item = CharacterIconItem(char_data, parent=self)
                icon_x = start_x + idx * (20.0 + 5.0)
                icon_item.setPos(icon_x, 0)
                self.icons.append(icon_item)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def paint(self, painter, option, widget=None):
        # El contenedor en sí es invisible, solo dibuja sus hijos
        pass
