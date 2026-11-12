"""Lifecycle and tray integration for the non-modal SingEtude note editor."""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QObject, QSettings, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .const import APP_NAME, ORG_NAME, ICON_PATH
from .signature_wm import KnowledgeEtudeWindow


class KnowledgeEtudeService(QObject):
    """Own one reusable, non-modal note window for the DomainViewer process."""

    _instance = None

    def __init__(self, base_path, tray_controller, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path).expanduser()
        self.tray_controller = tray_controller
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self._migrate_legacy_settings()
        self.window = None
        type(self)._instance = self

    def _migrate_legacy_settings(self):
        """Preserve note-editor preferences written under the previous app name."""
        legacy_settings = QSettings(ORG_NAME, "DomainViewer")
        for key in legacy_settings.allKeys():
            if not self.settings.contains(key):
                self.settings.setValue(key, legacy_settings.value(key))
        self.settings.sync()

    @classmethod
    def instance(cls):
        return cls._instance

    def set_base_path(self, base_path):
        """Keep note destinations synchronized with DomainViewer's data root."""
        self.base_path = Path(base_path).expanduser()
        if self.window is not None:
            self.window.base_dir = os.fspath(self.base_path)
            self.window.populate_character_combo()

    def open_contacts_manager(self, parent=None):
        """Open the contacts manager without creating the note editor window."""
        from .signature_dlg import ContactsManagerDialog

        editor = self.window
        dialog = ContactsManagerDialog(parent)
        dialog.setWindowIcon(QIcon(ICON_PATH))
        if editor is not None:
            dialog.contacts_updated.connect(
                lambda: editor.populate_contact_combos(preserve_selection=True)
            )

        result = dialog.exec()
        if editor is not None:
            editor.populate_contact_combos(preserve_selection=True)
        return result

    def open_classifications_manager(self, parent=None):
        """Open the note classifications manager without creating the editor."""
        from .signature_dlg import ClassificationsManagerDialog

        editor = self.window
        dialog = ClassificationsManagerDialog(parent)
        dialog.setWindowIcon(QIcon(ICON_PATH))
        if editor is not None:
            dialog.classifications_updated.connect(
                lambda: editor.populate_class_combo(preserve_selection=True)
            )

        result = dialog.exec()
        if editor is not None:
            editor.populate_class_combo(preserve_selection=True)
        return result

    def open_note(self, paste=False, year=None):
        """Show or restore the shared note editor without entering a modal loop."""
        if self.window is None:
            self.window = KnowledgeEtudeWindow(
                self.settings,
                self,
                base_dir=self.base_path,
            )
        else:
            self.window.base_dir = os.fspath(self.base_path)

        if year is not None:
            try:
                selected_year = int(year)
            except (TypeError, ValueError):
                selected_year = None

            if (
                selected_year is not None
                and self.window.year_selector.set_current_year(selected_year)
            ):
                self.window.populate_character_combo()

        if paste:
            clipboard = QApplication.clipboard()
            text = clipboard.text() if clipboard is not None else ""
            if text:
                self.window.text_edit.setPlainText(text)

        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        return self.window

    def show_message(self, title, message):
        if self.tray_controller is not None:
            self.tray_controller.show_message(title, message)

    def _last_note_path(self):
        raw_path = self.settings.value("last_saved_path", "")
        if not raw_path:
            return None
        path = Path(str(raw_path)).expanduser()
        return path if path.is_file() else None

    def open_last_folder(self):
        path = self._last_note_path()
        if path is None:
            QMessageBox.information(
                None,
                "Last Note",
                "No saved note is registered, or the file no longer exists.",
            )
            return False

        folder = path.parent
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            QMessageBox.warning(
                None,
                "Last Note",
                f"Could not open the note folder:\n{folder}",
            )
            return False
        return True

    def open_last_note(self):
        path = self._last_note_path()
        if path is None:
            QMessageBox.information(
                None,
                "Last Note",
                "No saved note is registered, or the file no longer exists.",
            )
            return False

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                None,
                "Last Note",
                f"Could not open the note:\n{path}",
            )
            return False
        return True


def request_knowledge_note(parent=None, year=None):
    """Shared entry point used by the Tools menu and every Knowledge toolbar."""
    service = KnowledgeEtudeService.instance()
    if service is None:
        QMessageBox.warning(
            parent,
            "SingEtude",
            "The note-writing service has not been initialized.",
        )
        return None
    return service.open_note(year=year)
