# domain_visor/json_editor.py

import json
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, pyqtSignal
from domain_visor.theme import Theme

class JSONTreeItem(QtWidgets.QTreeWidgetItem):
    TYPE_OBJECT = "object"
    TYPE_ARRAY = "array"
    TYPE_PRIMITIVE = "primitive"

    def __init__(self, key, value, node_type, parent=None):
        super().__init__(parent)
        self.node_type = node_type
        self.original_type = type(value)
        self.set_key(key)
        self.set_value(value)

    def set_key(self, key):
        self.setText(0, str(key))

    def get_key(self):
        val = self.text(0)
        try:
            return int(val)
        except ValueError:
            return val

    def set_value(self, value):
        if self.node_type == self.TYPE_PRIMITIVE:
            if value is None:
                self.setText(1, "null")
            elif isinstance(value, bool):
                self.setText(1, "true" if value else "false")
            else:
                self.setText(1, str(value))
        else:
            self.setText(1, "")
        self.original_type = type(value)

    def get_value(self):
        if self.node_type == self.TYPE_PRIMITIVE:
            txt = self.text(1)
            if txt == "null":
                return None
            if txt.lower() == "true":
                return True
            if txt.lower() == "false":
                return False
            if not txt:
                return ""
            try:
                if len(txt) > 1 and txt.startswith('0') and not txt.startswith('0.'):
                    return txt
                return int(txt)
            except ValueError:
                pass
            try:
                return float(txt)
            except ValueError:
                pass
            return txt
        else:
            return [] if self.node_type == self.TYPE_ARRAY else {}


class JSONTreeWidget(QtWidgets.QTreeWidget):
    json_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_is_array = False
        self.setColumnCount(2)
        self.setHeaderLabels(["Propiedad", "Valor"])
        self.setAlternatingRowColors(True)
        self.itemChanged.connect(self.on_item_changed)
        
        # Style tree widget to match the Theme
        self.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
                border: none;
                font-size: 13px;
                alternate-background-color: #252526;
            }}
            QHeaderView::section {{
                background-color: #2d2d2d;
                color: {Theme.TEXT_WHITE};
                padding: 4px;
                border: 1px solid #444444;
                font-weight: bold;
            }}
            QTreeWidget::item {{
                padding: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: #2a2d2e;
            }}
            QTreeWidget::item:selected {{
                background-color: #37373d;
                color: {Theme.TEXT_WHITE};
            }}
        """)
        self.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)

    def edit(self, index, trigger, event):
        item = self.itemFromIndex(index)
        if not item:
            return False
        col = index.column()
        
        # Col 0 (Key) editability
        if col == 0:
            parent = item.parent()
            if parent:
                if getattr(parent, 'node_type', None) == JSONTreeItem.TYPE_ARRAY:
                    return False
            else:
                if self.root_is_array:
                    return False
        # Col 1 (Value) editability
        elif col == 1:
            if getattr(item, 'node_type', None) != JSONTreeItem.TYPE_PRIMITIVE:
                return False
                
        return super().edit(index, trigger, event)

    def on_item_changed(self, item, column):
        self.json_changed.emit()

    def load_json(self, data):
        self.blockSignals(True)
        self.clear()
        self.root_is_array = isinstance(data, list)
        
        if isinstance(data, dict):
            for k, v in data.items():
                self.addTopLevelItem(self._create_item(k, v))
        elif isinstance(data, list):
            for idx, val in enumerate(data):
                self.addTopLevelItem(self._create_item(idx, val))
        else:
            self.addTopLevelItem(self._create_item("", data))
        
        self.expandAll()
        self.blockSignals(False)

    def _create_item(self, key, value, parent_item=None):
        if isinstance(value, dict):
            item = JSONTreeItem(key, value, JSONTreeItem.TYPE_OBJECT, parent_item)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            for k, v in value.items():
                self._create_item(k, v, item)
        elif isinstance(value, list):
            item = JSONTreeItem(key, value, JSONTreeItem.TYPE_ARRAY, parent_item)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            for idx, val in enumerate(value):
                self._create_item(idx, val, item)
        else:
            item = JSONTreeItem(key, value, JSONTreeItem.TYPE_PRIMITIVE, parent_item)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def get_json(self):
        if self.root_is_array:
            res = []
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                res.append(self._item_to_json(item))
            return res
        else:
            res = {}
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                res[item.get_key()] = self._item_to_json(item)
            return res

    def _item_to_json(self, item):
        if item.node_type == JSONTreeItem.TYPE_PRIMITIVE:
            return item.get_value()
        elif item.node_type == JSONTreeItem.TYPE_OBJECT:
            res = {}
            for i in range(item.childCount()):
                child = item.child(i)
                res[child.get_key()] = self._item_to_json(child)
            return res
        elif item.node_type == JSONTreeItem.TYPE_ARRAY:
            res = []
            for i in range(item.childCount()):
                child = item.child(i)
                res.append(self._item_to_json(child))
            return res

    def update_list_indices(self):
        self.blockSignals(True)
        if self.root_is_array:
            for i in range(self.topLevelItemCount()):
                self.topLevelItem(i).set_key(i)
        for i in range(self.topLevelItemCount()):
            self._recurse_update_list_indices(self.topLevelItem(i))
        self.blockSignals(False)

    def _recurse_update_list_indices(self, item):
        if item.node_type == JSONTreeItem.TYPE_ARRAY:
            for i in range(item.childCount()):
                child = item.child(i)
                child.set_key(i)
                self._recurse_update_list_indices(child)
        elif item.node_type == JSONTreeItem.TYPE_OBJECT:
            for i in range(item.childCount()):
                self._recurse_update_list_indices(item.child(i))

    def contextMenuEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #2d2d30;
                color: {Theme.TEXT_WHITE};
                border: 1px solid #444444;
            }}
            QMenu::item:selected {{
                background-color: #3e3e42;
            }}
        """)
        
        act_add_kv = None
        act_add_obj = None
        act_add_list = None
        act_insert_simple = None
        act_insert_obj = None
        act_insert_list = None
        act_delete = None

        if not item:
            if self.root_is_array:
                act_insert_simple = menu.addAction("Añadir Elemento simple a la raíz")
                act_insert_obj = menu.addAction("Añadir Objeto vacío a la raíz")
                act_insert_list = menu.addAction("Añadir Lista vacía a la raíz")
            else:
                act_add_kv = menu.addAction("Añadir Clave-Valor a la raíz")
                act_add_obj = menu.addAction("Añadir Objeto vacío a la raíz")
                act_add_list = menu.addAction("Añadir Lista vacía a la raíz")
        else:
            if item.node_type == JSONTreeItem.TYPE_OBJECT:
                act_add_kv = menu.addAction("Añadir Clave-Valor")
                act_add_obj = menu.addAction("Añadir Objeto vacío")
                act_add_list = menu.addAction("Añadir Lista vacía")
            elif item.node_type == JSONTreeItem.TYPE_ARRAY:
                act_insert_simple = menu.addAction("Insertar Elemento simple")
                act_insert_obj = menu.addAction("Insertar Objeto")
                act_insert_list = menu.addAction("Insertar Lista")
            else:
                parent = item.parent()
                if parent:
                    if parent.node_type == JSONTreeItem.TYPE_OBJECT:
                        act_add_kv = menu.addAction("Añadir Clave-Valor al padre")
                        act_add_obj = menu.addAction("Añadir Objeto al padre")
                        act_add_list = menu.addAction("Añadir Lista al padre")
                    elif parent.node_type == JSONTreeItem.TYPE_ARRAY:
                        act_insert_simple = menu.addAction("Insertar Elemento al padre")
                        act_insert_obj = menu.addAction("Insertar Objeto al padre")
                        act_insert_list = menu.addAction("Insertar Lista al padre")
                else:
                    if self.root_is_array:
                        act_insert_simple = menu.addAction("Insertar Elemento a la raíz")
                        act_insert_obj = menu.addAction("Insertar Objeto a la raíz")
                        act_insert_list = menu.addAction("Insertar Lista a la raíz")
                    else:
                        act_add_kv = menu.addAction("Añadir Clave-Valor a la raíz")
                        act_add_obj = menu.addAction("Añadir Objeto a la raíz")
                        act_add_list = menu.addAction("Añadir Lista a la raíz")

            menu.addSeparator()
            act_delete = menu.addAction("Eliminar")

        action = menu.exec(event.globalPosition().toPoint())
        if not action:
            return

        if action == act_delete:
            self.delete_item(item)
        elif action in [act_add_kv, act_add_obj, act_add_list]:
            target = item if (item and item.node_type == JSONTreeItem.TYPE_OBJECT) else (item.parent() if item else None)
            ntype = (JSONTreeItem.TYPE_PRIMITIVE if action == act_add_kv else
                     (JSONTreeItem.TYPE_OBJECT if action == act_add_obj else JSONTreeItem.TYPE_ARRAY))
            self.add_child_to_object(target, ntype)
        elif action in [act_insert_simple, act_insert_obj, act_insert_list]:
            target = item if (item and item.node_type == JSONTreeItem.TYPE_ARRAY) else (item.parent() if item else None)
            ntype = (JSONTreeItem.TYPE_PRIMITIVE if action == act_insert_simple else
                     (JSONTreeItem.TYPE_OBJECT if action == act_insert_obj else JSONTreeItem.TYPE_ARRAY))
            self.add_child_to_array(target, ntype)

    def add_to_root(self, node_type):
        self.blockSignals(True)
        if self.root_is_array:
            new_key = self.topLevelItemCount()
            new_val = self._default_value_for_type(node_type)
            new_item = JSONTreeItem(new_key, new_val, node_type)
            new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.addTopLevelItem(new_item)
            self.blockSignals(False)
            if node_type == JSONTreeItem.TYPE_PRIMITIVE:
                self.editItem(new_item, 1)
        else:
            existing_keys = [self.topLevelItem(i).get_key() for i in range(self.topLevelItemCount())]
            new_key = "nueva_clave"
            counter = 1
            while new_key in existing_keys:
                new_key = f"nueva_clave_{counter}"
                counter += 1
            new_val = self._default_value_for_type(node_type)
            new_item = JSONTreeItem(new_key, new_val, node_type)
            new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
            self.addTopLevelItem(new_item)
            self.blockSignals(False)
            self.editItem(new_item, 0)
            
        self.update_list_indices()
        self.json_changed.emit()

    def add_child_to_object(self, parent_item, node_type):
        if parent_item is None:
            self.add_to_root(node_type)
            return

        self.blockSignals(True)
        existing_keys = [parent_item.child(i).get_key() for i in range(parent_item.childCount())]
        new_key = "nueva_clave"
        counter = 1
        while new_key in existing_keys:
            new_key = f"nueva_clave_{counter}"
            counter += 1
        
        new_val = self._default_value_for_type(node_type)
        new_item = JSONTreeItem(new_key, new_val, node_type, parent_item)
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
        parent_item.addChild(new_item)
        parent_item.setExpanded(True)
        self.blockSignals(False)
        
        self.editItem(new_item, 0)
        self.update_list_indices()
        self.json_changed.emit()

    def add_child_to_array(self, parent_item, node_type):
        if parent_item is None:
            self.add_to_root(node_type)
            return

        self.blockSignals(True)
        new_key = parent_item.childCount()
        new_val = self._default_value_for_type(node_type)
        new_item = JSONTreeItem(new_key, new_val, node_type, parent_item)
        new_item.setFlags(new_item.flags() | Qt.ItemFlag.ItemIsEditable)
        parent_item.addChild(new_item)
        parent_item.setExpanded(True)
        self.blockSignals(False)
        
        if node_type == JSONTreeItem.TYPE_PRIMITIVE:
            self.editItem(new_item, 1)
            
        self.update_list_indices()
        self.json_changed.emit()

    def delete_item(self, item):
        if not item:
            return
        self.blockSignals(True)
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            index = self.indexOfTopLevelItem(item)
            if index != -1:
                self.takeTopLevelItem(index)
        self.blockSignals(False)
        self.update_list_indices()
        self.json_changed.emit()

    def _default_value_for_type(self, node_type):
        if node_type == JSONTreeItem.TYPE_PRIMITIVE:
            return ""
        elif node_type == JSONTreeItem.TYPE_OBJECT:
            return {}
        elif node_type == JSONTreeItem.TYPE_ARRAY:
            return []
        return None


class JSONEditorPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: #252526; color: {Theme.TEXT_WHITE};")
        
        # Layout principal
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Título
        self.title_label = QtWidgets.QLabel("Edicion de la Infrastructura")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px; color: #85c1e9;")
        layout.addWidget(self.title_label)
        
        # Árbol
        self.tree = JSONTreeWidget(self)
        layout.addWidget(self.tree)
        
        # Label de error
        self.error_label = QtWidgets.QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("""
            background-color: #a52a2a;
            color: white;
            border: 1px solid #ff4444;
            border-radius: 4px;
            padding: 8px;
            font-size: 12px;
            font-family: monospace;
        """)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
