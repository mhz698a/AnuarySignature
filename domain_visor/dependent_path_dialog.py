"""Dialog for selecting the dependent data folder."""

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class DependentPathDialog(QDialog):
    path_selected = pyqtSignal(str)

    def __init__(self, current_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar unidad dependientes")
        self.setMinimumWidth(540)
        self.selected_path = str(current_path)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Carpeta contenedora dependiente", self))

        self.path_edit = QLineEdit(self.selected_path, self)
        self.path_edit.setReadOnly(True)
        layout.addWidget(self.path_edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        self.choose_button = QPushButton("Elegir carpeta", self)
        self.cancel_button = QPushButton("Cancelar", self)
        buttons.addWidget(self.choose_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.choose_button.clicked.connect(self.choose_folder)
        self.cancel_button.clicked.connect(self.reject)

    def choose_folder(self):
        current = Path(self.selected_path).expanduser()
        start_directory = str(current if current.is_dir() else Path.home())
        selected = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta contenedora dependiente",
            start_directory,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected:
            return

        selected_path = str(Path(selected).expanduser().resolve())
        self.selected_path = selected_path
        self.path_edit.setText(selected_path)
        self.path_selected.emit(selected_path)
