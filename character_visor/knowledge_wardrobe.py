"""Knowledge wardrobe/reference browser embedded in the character editor."""

from __future__ import annotations

import ctypes
import json
import os
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QUrl, pyqtSignal, QThreadPool
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QIcon,
    QImage,
    QImageReader,
    QPixmap,
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QStackedWidget,
    QStyle,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


CATCH_ETUDE_SERVER = "CatchEtudeCommandServer"
IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"
}


def resolve_knowledge_directory(character_json_path, year=None) -> Path:
    """Return the matching character folder under the year's Knowledge container.

    A credential normally lives at:
        <root>/<year>/<prefix>. album/<character-folder>/__name__.json

    Its matching Knowledge folder is:
        <root>/<year>/<prefix>. knowledge/<character-folder>
    """
    credential_path = Path(character_json_path).expanduser()
    character_dir = credential_path.parent
    album_dir = character_dir.parent
    year_dir = album_dir.parent

    album_name = album_dir.name
    prefix = ""
    if ". " in album_name:
        possible_prefix = album_name.split(". ", 1)[0]
        if possible_prefix.isdigit():
            prefix = possible_prefix

    if not prefix:
        try:
            year_number = int(year if year is not None else year_dir.name)
            prefix = f"{max(0, year_number - 2003):02d}"
        except (TypeError, ValueError):
            prefix = "00"

    return year_dir / f"{prefix}. knowledge" / character_dir.name


def _volume_key(path: Path) -> str:
    """Return the volume identifier used to reject cross-drive imports."""
    resolved = Path(path).expanduser().resolve()
    if os.name == "nt":
        drive, _ = os.path.splitdrive(str(resolved))
        return drive.casefold()
    return str(resolved.anchor).casefold()


def _move_to_recycle_bin(path: Path) -> None:
    """Move a file to the Windows Recycle Bin without permanent deletion."""
    if os.name != "nt":
        raise OSError("La Papelera de reciclaje de Windows no está disponible.")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    source = str(path.resolve()) + "\0\0"
    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = source
    operation.pTo = None
    # FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
    operation.fFlags = 0x0004 | 0x0010 | 0x0040 | 0x0400
    operation.fAnyOperationsAborted = 0
    operation.hNameMappings = None
    operation.lpszProgressTitle = None

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(result or 1, f"No se pudo enviar a la Papelera de reciclaje: {path}")


def _enqueue_in_catch_etude(
    path: Path,
    notify_server: str,
    timeout_ms: int = 3000,
) -> None:
    """Enqueue a file and subscribe to CatchEtude's successful-move notification."""
    socket = QLocalSocket()
    socket.connectToServer(CATCH_ETUDE_SERVER)
    if not socket.waitForConnected(timeout_ms):
        error = socket.errorString()
        socket.abort()
        raise OSError(f"No se pudo conectar con CatchEtude: {error}")

    request = {
        "cmd": "enqueue_path",
        "path": str(path.resolve()),
        "hide_secure": True,
        "notify_server": notify_server,
    }
    payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")

    if socket.write(payload) != len(payload) or not socket.waitForBytesWritten(timeout_ms):
        error = socket.errorString()
        socket.abort()
        raise OSError(f"No se pudo enviar el archivo a CatchEtude: {error}")

    response_data = bytearray()
    while b"\n" not in response_data:
        if not socket.waitForReadyRead(timeout_ms):
            break
        response_data.extend(socket.readAll().data())

    socket.disconnectFromServer()
    if b"\n" not in response_data:
        raise OSError("CatchEtude no devolvió una confirmación del comando.")

    response_line = bytes(response_data).split(b"\n", 1)[0]
    try:
        response = json.loads(response_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OSError(f"CatchEtude devolvió una respuesta inválida: {exc}") from exc

    if not response.get("ok"):
        code = response.get("error", "unknown_error")
        message = response.get("message", "CatchEtude rechazó el archivo.")
        raise OSError(f"{code}: {message}")


class _ScanSignals(QObject):
    file_found = pyqtSignal(int, str, object)
    finished = pyqtSignal(int, bool, str)


class _DirectoryScanTask(QRunnable):
    """Enumerate files and decode image thumbnails outside the GUI thread."""

    def __init__(self, generation: int, directory: Path):
        super().__init__()
        self.generation = generation
        self.directory = directory
        self.signals = _ScanSignals()

    def run(self):
        try:
            if not self.directory.is_dir():
                self.signals.finished.emit(self.generation, False, "missing")
                return

            files = sorted(
                (entry for entry in self.directory.iterdir() if entry.is_file()),
                key=lambda entry: entry.name.casefold(),
            )
            for file_path in files:
                thumbnail = None
                if file_path.suffix.lower() in IMAGE_EXTENSIONS:
                    reader = QImageReader(str(file_path))
                    reader.setAutoTransform(True)
                    source_size = reader.size()
                    if source_size.isValid():
                        source_size.scale(
                            QSize(160, 120),
                            Qt.AspectRatioMode.KeepAspectRatio,
                        )
                        reader.setScaledSize(source_size)
                    image = reader.read()
                    if not image.isNull():
                        thumbnail = image.scaled(
                            QSize(112, 84),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )

                self.signals.file_found.emit(
                    self.generation, str(file_path), thumbnail
                )

            self.signals.finished.emit(self.generation, True, "")
        except Exception as exc:
            self.signals.finished.emit(self.generation, False, str(exc))


class _OperationSignals(QObject):
    finished = pyqtSignal(int, object)


class _FileOperationTask(QRunnable):
    """Run filesystem and CatchEtude operations without blocking the UI."""

    def __init__(
        self,
        generation: int,
        operation: str,
        paths: list[Path],
        destination: Path | None = None,
        new_name: str | None = None,
        notify_server: str | None = None,
    ):
        super().__init__()
        self.generation = generation
        self.operation = operation
        self.paths = paths
        self.destination = destination
        self.new_name = new_name
        self.notify_server = notify_server
        self.signals = _OperationSignals()

    def run(self):
        result = {
            "operation": self.operation,
            "successes": [],
            "errors": [],
        }

        if self.operation == "import":
            try:
                self.destination.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                result["errors"].append(str(exc))
                self.signals.finished.emit(self.generation, result)
                return

            target_volume = _volume_key(self.destination)
            for source in self.paths:
                try:
                    if not source.is_file():
                        raise OSError("El archivo de origen ya no existe.")
                    if _volume_key(source) != target_volume:
                        raise OSError("No se permiten movimientos entre unidades.")
                    target = self.destination / source.name
                    if source.resolve() == target.resolve():
                        raise OSError("El archivo ya está dentro de Knowledge.")
                    if target.exists():
                        raise FileExistsError(f"Ya existe un archivo con ese nombre: {target.name}")
                    source.rename(target)
                    result["successes"].append(str(target))
                except Exception as exc:
                    result["errors"].append(f"{source.name}: {exc}")

        elif self.operation == "rename":
            source = self.paths[0]
            try:
                if not self.new_name or self.new_name in {".", ".."}:
                    raise OSError("El nombre del archivo no es válido.")
                target = source.with_name(self.new_name)
                if target.exists() and target.resolve() != source.resolve():
                    raise FileExistsError(f"Ya existe un archivo llamado {target.name}.")
                source.rename(target)
                result["successes"].append(str(target))
            except Exception as exc:
                result["errors"].append(f"{source.name}: {exc}")

        elif self.operation == "delete":
            for source in self.paths:
                try:
                    if not source.is_file():
                        raise OSError("El archivo ya no existe.")
                    _move_to_recycle_bin(source)
                    result["successes"].append(str(source))
                except Exception as exc:
                    result["errors"].append(f"{source.name}: {exc}")

        elif self.operation == "send":
            for source in self.paths:
                try:
                    if not source.is_file():
                        raise OSError("El archivo ya no existe.")
                    _enqueue_in_catch_etude(
                        source,
                        notify_server=self.notify_server,
                    )
                    result["successes"].append(str(source))
                except Exception as exc:
                    result["errors"].append(f"{source.name}: {exc}")

        self.signals.finished.emit(self.generation, result)


class FileRenameDialog(QDialog):
    """Wide dialog for changing a Knowledge file name."""

    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Renombrar archivo")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.resize(760, 180)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Nombre del archivo:"))
        self.name_edit = QLineEdit(current_name, self)
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def new_name(self) -> str:
        return self.name_edit.text().strip()


class KnowledgeWardrobeWidget(QWidget):
    """Grid-based file browser for the current character's Knowledge folder."""

    def __init__(self, knowledge_directory: Path, parent=None):
        super().__init__(parent)
        self.knowledge_directory = Path(knowledge_directory)
        self._scan_generation = 0
        self._operation_generation = 0
        self._scan_task = None
        self._operation_task = None
        self._busy = False
        self._scanning = False
        self._suppressed_paths = set()

        # CatchEtude envía los eventos file_moved a este servidor IPC local.
        self._move_notification_server = QLocalServer(self)
        self._move_notification_server_name = (
            f"DomainViewerKnowledge_{os.getpid()}_{uuid.uuid4().hex[:16]}"
        )
        self._move_notification_server.newConnection.connect(
            self._on_move_notification_connection
        )
        self._move_notification_server_error = ""
        if not self._move_notification_server.listen(
            self._move_notification_server_name
        ):
            self._move_notification_server_error = (
                self._move_notification_server.errorString()
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        self.toolbar = QToolBar(self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        layout.addWidget(self.toolbar)

        self.reload_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "Recargar",
            self,
        )
        self.reload_action.triggered.connect(self.reload)
        self.toolbar.addAction(self.reload_action)

        self.import_action = QAction("Importar Archivo", self)
        self.import_action.triggered.connect(self.import_files)
        self.toolbar.addAction(self.import_action)

        self.rename_action = QAction("Renombrar Archivo", self)
        self.rename_action.triggered.connect(self.rename_selected_file)
        self.toolbar.addAction(self.rename_action)

        self.send_action = QAction("Enviar a CatchEtude", self)
        self.send_action.triggered.connect(self.send_selected_to_catch_etude)
        self.toolbar.addAction(self.send_action)

        self.delete_action = QAction("Eliminar archivo", self)
        self.delete_action.triggered.connect(self.delete_selected_files)
        self.toolbar.addAction(self.delete_action)

        self.toolbar.addSeparator()

        self.selection_button = QToolButton(self.toolbar)
        self.selection_button.setText("Selección")
        self.selection_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        selection_menu = QMenu(self.selection_button)
        select_all_action = selection_menu.addAction("Seleccionar todo")
        select_all_action.triggered.connect(self.select_all)
        deselect_action = selection_menu.addAction("Deseleccionar")
        deselect_action.triggered.connect(self.deselect_all)
        invert_action = selection_menu.addAction("Invertir selección")
        invert_action.triggered.connect(self.invert_selection)
        self.selection_button.setMenu(selection_menu)
        self.toolbar.addWidget(self.selection_button)

        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, 1)

        self.files_list = QListWidget(self.stack)
        self.files_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.files_list.setFlow(QListWidget.Flow.LeftToRight)
        self.files_list.setWrapping(True)
        self.files_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.files_list.setMovement(QListWidget.Movement.Static)
        self.files_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.files_list.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )
        self.files_list.setIconSize(QSize(112, 84))
        self.files_list.setGridSize(QSize(156, 132))
        self.files_list.setUniformItemSizes(True)
        self.files_list.setWordWrap(True)
        self.files_list.itemSelectionChanged.connect(
            self._update_action_states
        )
        self.files_list.itemDoubleClicked.connect(self.open_file_item)
        self.files_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.files_list.customContextMenuRequested.connect(
            self.show_file_context_menu
        )
        self.stack.addWidget(self.files_list)

        self.placeholder = QLabel(self.stack)
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.stack.addWidget(self.placeholder)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._update_action_states()
        self.reload()

    def selected_paths(self) -> list[Path]:
        return [
            Path(item.data(Qt.ItemDataRole.UserRole))
            for item in self.files_list.selectedItems()
        ]

    def _set_placeholder(self, message: str):
        self.placeholder.setText(message)
        self.stack.setCurrentWidget(self.placeholder)

    @staticmethod
    def _path_key(path: str | Path) -> str:
        normalized = os.path.realpath(os.path.abspath(os.fspath(path)))
        return os.path.normcase(normalized)

    def reload(self):
        self._scan_generation += 1
        generation = self._scan_generation
        self._scanning = True
        self._suppressed_paths.clear()
        self.files_list.clear()
        self.status_label.clear()
        self._update_action_states()

        self._set_placeholder("Cargando archivos de Knowledge…")
        task = _DirectoryScanTask(generation, self.knowledge_directory)
        task.signals.file_found.connect(self._on_file_found)
        task.signals.finished.connect(self._on_scan_finished)
        self._scan_task = task
        QThreadPool.globalInstance().start(task)

    def _on_file_found(self, generation: int, file_path: str, thumbnail):
        if generation != self._scan_generation:
            return

        if self._path_key(file_path) in self._suppressed_paths:
            return

        path = Path(file_path)
        if thumbnail is not None and not thumbnail.isNull():
            icon = QIcon(QPixmap.fromImage(thumbnail))
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

        item = QListWidgetItem(icon, path.name)
        item.setToolTip(str(path))
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.files_list.addItem(item)
        self.stack.setCurrentWidget(self.files_list)

    def _on_scan_finished(self, generation: int, directory_exists: bool, error: str):
        if generation != self._scan_generation:
            return

        self._scan_task = None
        self._scanning = False
        if error and error != "missing":
            self._set_placeholder(f"No se pudo leer la carpeta Knowledge:\n{error}")
            self._suppressed_paths.clear()
            self._update_action_states()
            return

        if not directory_exists:
            self._set_placeholder(
                "No se encontró la carpeta correspondiente en Knowledge.\n\n"
                f"Ruta esperada:\n{self.knowledge_directory}\n\n"
                "Puedes importar archivos para crear esta ubicación."
            )
        elif self.files_list.count() == 0:
            self._set_placeholder("La carpeta Knowledge existe, pero no contiene archivos.")
        else:
            self.stack.setCurrentWidget(self.files_list)
            self.status_label.setText(
                f"{self.files_list.count()} archivo(s) en Knowledge."
            )

        self._suppressed_paths.clear()
        self._update_action_states()

    def _update_action_states(self):
        has_selection = bool(self.files_list.selectedItems())
        single_selection = len(self.files_list.selectedItems()) == 1
        enabled = not self._busy
        self.reload_action.setEnabled(enabled and not self._scanning)
        self.import_action.setEnabled(enabled)
        self.rename_action.setEnabled(enabled and single_selection)
        self.send_action.setEnabled(enabled and has_selection)
        self.delete_action.setEnabled(enabled and has_selection)
        self.selection_button.setEnabled(enabled and self.files_list.count() > 0)

    def open_file_item(self, item: QListWidgetItem):
        """Open a file with the Windows/default application association."""
        if item is None:
            return
        self.open_paths([Path(item.data(Qt.ItemDataRole.UserRole))])

    def open_paths(self, paths: list[Path]):
        for path in paths:
            try:
                if not path.is_file():
                    raise OSError("El archivo ya no existe.")
                if os.name == "nt":
                    # os.startfile sin verbo reproduce el doble clic de Explorer
                    # y delega la apertura en la asociación de archivos de Windows.
                    os.startfile(str(path.resolve()))
                else:
                    opened = QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(path.resolve()))
                    )
                    if not opened:
                        raise OSError(
                            "El sistema no pudo abrir el archivo con su aplicación asociada."
                        )
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Abrir archivo",
                    f"No se pudo abrir {path.name}:\n{exc}",
                )

    def open_selected_files(self):
        self.open_paths(self.selected_paths())

    def show_file_properties(self):
        selected = self.selected_paths()
        if len(selected) != 1:
            return

        path = selected[0]
        if os.name != "nt":
            QMessageBox.warning(
                self,
                "Propiedades del archivo",
                "El diálogo de propiedades solicitado está disponible en Windows.",
            )
            return

        try:
            if not path.is_file():
                raise OSError("El archivo ya no existe.")
            os.startfile(str(path.resolve()), "properties")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Propiedades del archivo",
                f"No se pudieron abrir las propiedades de {path.name}:\n{exc}",
            )

    def show_file_context_menu(self, position):
        item = self.files_list.itemAt(position)
        if item is None:
            return

        # Un clic derecho sobre un elemento no seleccionado sustituye la
        # selección; sobre uno ya seleccionado conserva la selección múltiple.
        if not item.isSelected():
            self.files_list.clearSelection()
            item.setSelected(True)

        selected_count = len(self.files_list.selectedItems())
        menu = QMenu(self.files_list)

        open_action = menu.addAction("Abrir")
        open_action.triggered.connect(self.open_selected_files)

        rename_action = menu.addAction("Renombrar Archivo")
        rename_action.setEnabled(selected_count == 1)
        rename_action.triggered.connect(self.rename_selected_file)

        send_action = menu.addAction("Enviar a CatchEtude")
        send_action.triggered.connect(self.send_selected_to_catch_etude)

        delete_action = menu.addAction("Eliminar Archivo")
        delete_action.triggered.connect(self.delete_selected_files)

        menu.addSeparator()

        properties_action = menu.addAction("Propiedades del archivo")
        properties_action.setEnabled(selected_count == 1)
        properties_action.triggered.connect(self.show_file_properties)

        menu.exec(self.files_list.viewport().mapToGlobal(position))

    def _on_move_notification_connection(self):
        while self._move_notification_server.hasPendingConnections():
            client_socket = self._move_notification_server.nextPendingConnection()
            client_socket.setProperty("move_event_buffer", b"")
            client_socket.readyRead.connect(
                lambda sock=client_socket: self._read_move_notification(sock)
            )
            client_socket.disconnected.connect(
                lambda sock=client_socket: self._read_move_notification(
                    sock, final=True
                )
            )
            client_socket.disconnected.connect(client_socket.deleteLater)
            # Drenar cualquier dato que ya estuviera disponible al aceptar
            # la conexión antes de que se conectara readyRead.
            self._read_move_notification(client_socket)

    def _read_move_notification(self, socket, final: bool = False):
        buffered = socket.property("move_event_buffer") or b""
        data = bytes(buffered) + socket.readAll().data()

        while b"\n" in data:
            line, data = data.split(b"\n", 1)
            if line.strip():
                self._process_move_notification(line)

        if final and data.strip():
            self._process_move_notification(data)
            data = b""

        socket.setProperty("move_event_buffer", data)

    def _process_move_notification(self, payload: bytes):
        try:
            event = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if not isinstance(event, dict) or event.get("event") != "file_moved":
            return

        source = event.get("src")
        if not isinstance(source, str) or not source.strip():
            return

        source_key = self._path_key(source)
        self._suppressed_paths.add(source_key)

        removed_name = Path(source).name
        removed = 0
        for index in range(self.files_list.count() - 1, -1, -1):
            item = self.files_list.item(index)
            item_path = item.data(Qt.ItemDataRole.UserRole)
            if item_path and self._path_key(item_path) == source_key:
                self.files_list.takeItem(index)
                removed += 1

        if removed:
            self.status_label.setText(
                f'CatchEtude movió "{removed_name}"; archivo retirado de la cuadrícula.'
            )
            if self.files_list.count() == 0:
                self._set_placeholder(
                    "La carpeta Knowledge existe, pero no contiene archivos."
                )
            else:
                self.stack.setCurrentWidget(self.files_list)
            self._update_action_states()

    def select_all(self):
        self.files_list.selectAll()
        self._update_action_states()

    def deselect_all(self):
        self.files_list.clearSelection()
        self._update_action_states()

    def invert_selection(self):
        for index in range(self.files_list.count()):
            item = self.files_list.item(index)
            item.setSelected(not item.isSelected())
        self._update_action_states()

    def import_files(self):
        start_directory = (
            self.knowledge_directory.parent.parent
            if self.knowledge_directory.parent.parent.is_dir()
            else str(Path.home())
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Importar archivos a Knowledge",
            str(start_directory),
            "Todos los archivos (*)",
        )
        if not paths:
            return

        target_volume = _volume_key(self.knowledge_directory)
        valid_paths = []
        rejected_paths = []
        for raw_path in paths:
            source = Path(raw_path).expanduser()
            if not source.is_file():
                rejected_paths.append(f"{source.name}: el archivo no existe.")
            elif _volume_key(source) != target_volume:
                rejected_paths.append(
                    f"{source.name}: pertenece a otra unidad."
                )
            else:
                valid_paths.append(source)

        if rejected_paths:
            QMessageBox.warning(
                self,
                "Archivos no admitidos",
                "Solo se pueden importar archivos de la misma unidad que "
                "la carpeta Knowledge.\n\n"
                + "\n".join(rejected_paths[:12]),
            )
        if valid_paths:
            self._start_operation("import", valid_paths)

    def rename_selected_file(self):
        selected = self.selected_paths()
        if len(selected) != 1:
            return

        source = selected[0]
        dialog = FileRenameDialog(source.name, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = dialog.new_name
        if not new_name or new_name == source.name:
            return
        if Path(new_name).name != new_name or new_name in {".", ".."}:
            QMessageBox.warning(
                self, "Nombre no válido",
                "Introduce un nombre de archivo válido, sin rutas ni carpetas."
            )
            return

        self._start_operation("rename", [source], new_name=new_name)

    def send_selected_to_catch_etude(self):
        selected = self.selected_paths()
        if selected:
            self._start_operation("send", selected)

    def delete_selected_files(self):
        selected = self.selected_paths()
        if not selected:
            return

        names = "\n".join(path.name for path in selected[:8])
        remaining = len(selected) - min(len(selected), 8)
        if remaining:
            names += f"\n… y {remaining} archivo(s) más"

        reply = QMessageBox.question(
            self,
            "Eliminar archivos",
            f"¿Enviar {len(selected)} archivo(s) a la Papelera de reciclaje?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_operation("delete", selected)

    def _start_operation(
        self,
        operation: str,
        paths: list[Path],
        new_name: str | None = None,
    ):
        if self._busy:
            return

        self._busy = True
        self.status_label.setText("Procesando archivos en segundo plano…")
        self._update_action_states()

        self._operation_generation += 1
        generation = self._operation_generation
        notify_server = None
        if operation == "send":
            if not self._move_notification_server.isListening():
                self._busy = False
                self._update_action_states()
                QMessageBox.warning(
                    self,
                    "CatchEtude",
                    "No está disponible el endpoint para recibir notificaciones "
                    "de movimientos de CatchEtude.\n\n"
                    f"{self._move_notification_server_error}",
                )
                return
            notify_server = self._move_notification_server.serverName()

        task = _FileOperationTask(
            generation,
            operation,
            paths,
            destination=self.knowledge_directory,
            new_name=new_name,
            notify_server=notify_server,
        )
        task.signals.finished.connect(self._on_operation_finished)
        self._operation_task = task
        QThreadPool.globalInstance().start(task)

    def _on_operation_finished(self, generation: int, result: dict):
        if generation != self._operation_generation:
            return

        self._operation_task = None
        self._busy = False

        successes = result.get("successes", [])
        errors = result.get("errors", [])
        if successes:
            self.status_label.setText(
                f"Operación completada: {len(successes)} archivo(s)."
            )
        elif errors:
            self.status_label.setText("No se pudo completar la operación.")

        if errors:
            QMessageBox.warning(
                self,
                "Resultado de la operación",
                "Algunos archivos no pudieron procesarse:\n\n"
                + "\n".join(errors[:12]),
            )

        operation = result.get("operation")
        if successes and operation in {"import", "rename", "delete"}:
            self.reload()
            self.status_label.setText(
                f"Operación completada: {len(successes)} archivo(s)."
            )
        else:
            self._update_action_states()
