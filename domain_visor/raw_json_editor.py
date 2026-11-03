"""Reusable PyQt6 dialog for editing and validating raw JSON documents."""

import json
import re

from PyQt6.QtCore import Qt, QRect, QSize, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
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
    QWidget,
)


class LineNumberArea(QWidget):
    """Vertical line-number header attached to a QPlainTextEdit."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class JSONCodeEditor(QPlainTextEdit):
    """QPlainTextEdit with a vertical line-number gutter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0,
                rect.y(),
                self.line_number_area.width(),
                rect.height(),
            )

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        contents_rect = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(
                contents_rect.left(),
                contents_rect.top(),
                self.line_number_area_width(),
                contents_rect.height(),
            )
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1B1B1B"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block)
            .translated(self.contentOffset())
            .top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#858585"))
                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 7,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(block_number + 1),
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())

            block_number += 1

    def highlight_current_line(self):
        # Se mantiene el gutter visible; el resaltado de sintaxis pertenece al highlighter.
        self.line_number_area.update()


class JSONSyntaxHighlighter(QSyntaxHighlighter):
    """Dark-theme JSON syntax highlighter with an error underline range."""

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
        self.error_block_number = None
        self.error_start = 0
        self.error_length = 1

    @staticmethod
    def _format(color, bold=False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def set_error_position(self, document, absolute_position, length=1):
        block = document.findBlock(max(0, absolute_position))
        if not block.isValid():
            self.clear_error_position()
            return

        new_block_number = block.blockNumber()
        new_start = max(0, absolute_position - block.position())
        new_length = max(1, length)

        if (
            self.error_block_number == new_block_number
            and self.error_start == new_start
            and self.error_length == new_length
        ):
            return

        previous_block = (
            document.findBlockByNumber(self.error_block_number)
            if self.error_block_number is not None
            else None
        )
        self.error_block_number = new_block_number
        self.error_start = new_start
        self.error_length = new_length

        if previous_block is not None and previous_block.isValid():
            if previous_block.blockNumber() != new_block_number:
                self.rehighlightBlock(previous_block)
        self.rehighlightBlock(block)

    def clear_error_position(self):
        if self.error_block_number is None:
            return

        previous_block = self.document().findBlockByNumber(
            self.error_block_number
        )
        self.error_block_number = None
        self.error_start = 0
        self.error_length = 1

        if previous_block.isValid():
            self.rehighlightBlock(previous_block)

    def highlightBlock(self, text):
        string_matches = list(self._STRING_PATTERN.finditer(text))
        key_spans = {match.span() for match in self._KEY_PATTERN.finditer(text)}
        string_ranges = [match.span() for match in string_matches]

        for start, end in key_spans:
            self.setFormat(start, end - start, self.key_format)

        for match in string_matches:
            start, end = match.span()
            if (start, end) not in key_spans:
                self.setFormat(start, end - start, self.string_format)

        token_rules = (
            (self._NUMBER_PATTERN, self.number_format),
            (self._LITERAL_PATTERN, self.literal_format),
            (self._PUNCTUATION_PATTERN, self.punctuation_format),
        )
        for pattern, fmt in token_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                if any(
                    start < string_end and end > string_start
                    for string_start, string_end in string_ranges
                ):
                    continue
                self.setFormat(start, end - start, fmt)

        if self.currentBlock().blockNumber() == self.error_block_number:
            start = min(self.error_start, max(0, len(text) - 1))
            end = min(len(text), start + self.error_length)
            if end > start:
                error_format = QTextCharFormat()
                error_format.setForeground(QColor("#FF7B72"))
                error_format.setBackground(QColor("#3B1717"))
                error_format.setUnderlineStyle(
                    QTextCharFormat.UnderlineStyle.WaveUnderline
                )
                error_format.setUnderlineColor(QColor("#FF4D4F"))
                self.setFormat(start, end - start, error_format)


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

        self.editor = JSONCodeEditor(self)
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

        # Validar cuando el usuario hace una pausa, no en cada pulsación.
        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.setInterval(250)
        self._validation_timer.timeout.connect(self.validate_json)
        self.editor.textChanged.connect(self._schedule_validation)
        self.validate_json()

    def _schedule_validation(self):
        self._validation_timer.start()

    def validate_json(self):
        """Validate current text and update only the affected syntax-highlight block."""
        text = self.editor.toPlainText()
        try:
            parsed_data = json.loads(text)
        except json.JSONDecodeError as error:
            self.json_data = None
            self.save_button.setEnabled(False)
            self.error_label.setStyleSheet("color: #F48771; padding: 2px 4px;")
            self.error_label.setText(
                f"JSONDecodeError: {error.msg} (línea {error.lineno}, columna {error.colno})"
            )
            position = min(error.pos, max(0, len(text) - 1))
            self.highlighter.set_error_position(
                self.editor.document(),
                position,
                1,
            )
            return False

        self.json_data = parsed_data
        self.error_label.setText("JSON válido")
        self.error_label.setStyleSheet("color: #89D185; padding: 2px 4px;")
        self.highlighter.clear_error_position()
        self.save_button.setEnabled(True)
        return True

    def _accept_json(self):
        self._validation_timer.stop()
        if not self.validate_json():
            self.editor.setFocus()
            return

        self.accept()

    def get_json_data(self):
        """Return the parsed JSON document after the dialog was accepted."""
        return self.json_data
