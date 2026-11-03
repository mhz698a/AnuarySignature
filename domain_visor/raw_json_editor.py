"""Reusable PyQt6 dialog for editing and validating raw JSON documents."""

import json
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """Dark-theme JSON syntax highlighter that can be attached to any QTextDocument."""

    _STRING_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"')
    _KEY_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"(?=\s*:)')
    _NUMBER_PATTERN = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
    _LITERAL_PATTERN = re.compile(r"\b(?:true|false|null)\b")
    _PUNCTUATION_PATTERN = re.compile(r"[{}\[\],:]")

    def __init__(self, document):
        super().__init__(document)
        self.key_format = self._format("#9CDCFE", bold=True)
        self.string_format = self._format("#CE9178")
        self.number_format = self._format("#B5CEA8")
        self.literal_format = self._format("#569CD6", bold=True)
        self.punctuation_format = self._format("#D4D4D4")

    @staticmethod
    def _format(color, bold=False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def highlightBlock(self, text):
        string_matches = list(self._STRING_PATTERN.finditer(text))
        key_matches = list(self._KEY_PATTERN.finditer(text))
        string_ranges = [match.span() for match in string_matches]

        for match in key_matches:
            start, end = match.span()
            self.setFormat(start, end - start, self.key_format)

        for match in string_matches:
            start, end = match.span()
            if not any(start == key_start and end == key_end for key_start, key_end in [m.span() for m in key_matches]):
                self.setFormat(start, end - start, self.string_format)

        token_rules = (
            (self._NUMBER_PATTERN, self.number_format),
            (self._LITERAL_PATTERN, self.literal_format),
            (self._PUNCTUATION_PATTERN, self.punctuation_format),
        )
        for pattern, fmt in token_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(start < string_end and end > string_start for string_start, string_end in string_ranges):
                    continue
                self.setFormat(start, end - start, fmt)


class RawJSONEditorDialog(QDialog):
    """
    Standalone JSON editor.

    Usage:
        dialog = RawJSONEditorDialog(json_text, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            parsed_document = dialog.json_data
    """

    def __init__(self, initial_text="", parent=None, title="Editar JSON en Crudo"):
        super().__init__(parent)
        self.json_data = None

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(850, 650)
        self.setMinimumSize(560, 380)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet("""
            QDialog {
                background-color: #181818;
                color: #E6E6E6;
            }
            QLabel {
                color: #E6E6E6;
                font-family: Arial;
                font-size: 11px;
            }
            QPlainTextEdit {
                background-color: #101010;
                color: #D4D4D4;
                border: 1px solid #3F3F46;
                border-radius: 4px;
                padding: 8px;
                selection-background-color: #264F78;
                font-family: Consolas, "Cascadia Code", monospace;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #2D2D30;
                color: #E6E6E6;
                border: 1px solid #55555B;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3E3E42;
                border-color: #85C1E9;
            }
            QPushButton:disabled {
                color: #777777;
                border-color: #333333;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.editor = QPlainTextEdit(self)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setPlainText(str(initial_text))
        self.highlighter = JSONSyntaxHighlighter(self.editor.document())
        layout.addWidget(self.editor, 1)

        self.error_label = QLabel(self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #F48771; padding: 2px 4px;")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancelar", self)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button = QPushButton("Guardar", self)
        self.save_button.clicked.connect(self._accept_json)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self.editor.textChanged.connect(self.validate_json)
        self.validate_json()

    def validate_json(self):
        """Validate current text and mark the JSONDecodeError location."""
        try:
            json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as error:
            self.save_button.setEnabled(False)
            self.error_label.setStyleSheet("color: #F48771; padding: 2px 4px;")
            self.error_label.setText(
                f"JSONDecodeError: {error.msg} (línea {error.lineno}, columna {error.colno})"
            )
            self._mark_error_position(error.pos)
            return False

        self.error_label.setText("JSON válido")
        self.error_label.setStyleSheet("color: #89D185; padding: 2px 4px;")
        self.editor.setExtraSelections([])
        self.save_button.setEnabled(True)
        return True

    def _mark_error_position(self, position):
        text = self.editor.toPlainText()
        if not text:
            self.editor.setExtraSelections([])
            return

        position = min(max(position, 0), len(text))
        if position == len(text):
            position = max(0, position - 1)

        cursor = self.editor.textCursor()
        cursor.setPosition(position)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
        )

        error_format = QTextCharFormat()
        error_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.WaveUnderline
        )
        error_format.setUnderlineColor(QColor("#FF4D4F"))

        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = error_format
        self.editor.setExtraSelections([selection])

    def _accept_json(self):
        try:
            self.json_data = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError:
            self.validate_json()
            self.editor.setFocus()
            return
        self.accept()

    def get_json_data(self):
        """Return the parsed JSON document after the dialog was accepted."""
        return self.json_data
