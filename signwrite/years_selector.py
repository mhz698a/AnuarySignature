from math import ceil

from PyQt6 import QtCore
from PyQt6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem


class YearsTableWidget(QTableWidget):
    """Selector compacto de años en cuadrícula, inspirado en CatchEtude."""

    yearChanged = QtCore.pyqtSignal(int)

    def __init__(self, years, selected_year=None, parent=None):
        super().__init__(0, 0, parent)
        self._years = [int(year) for year in years]
        self._cell_width = 42
        self._cell_height = 28
        initial_year = int(selected_year) if selected_year is not None else None
        self._selected_year = (
            initial_year if initial_year in self._years
            else (self._years[0] if self._years else None)
        )

        self.setShowGrid(False)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            "QTableWidget { border: none; background: transparent; }"
            "QTableWidget::item { border-radius: 4px; padding: 4px; }"
            "QTableWidget::item:selected { background-color: #0078d7; color: white; }"
        )

        self.itemSelectionChanged.connect(self._on_selection_changed)
        self._rebuild()

    def current_year(self):
        item = self.currentItem()
        if item is not None:
            try:
                return int(item.text())
            except ValueError:
                pass
        return self._selected_year

    def set_current_year(self, year):
        """Selecciona un año existente sin emitir una señal de cambio de usuario."""
        try:
            year = int(year)
        except (TypeError, ValueError):
            return False

        if year not in self._years:
            return False

        self._selected_year = year
        self.blockSignals(True)
        self._select_year(year)
        self.blockSignals(False)
        return True

    def _on_selection_changed(self):
        item = self.currentItem()
        if item is None:
            return
        try:
            year = int(item.text())
        except ValueError:
            return
        if year == self._selected_year:
            return
        self._selected_year = year
        self.yearChanged.emit(year)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rebuild()

    def _rebuild(self):
        if not self._years:
            self.clearContents()
            self.setRowCount(0)
            self.setColumnCount(0)
            return

        selected_year = self.current_year() or self._selected_year
        viewport_width = max(1, self.viewport().width())
        columns = max(1, viewport_width // self._cell_width)
        columns = min(columns, len(self._years))
        rows = ceil(len(self._years) / columns)

        self.blockSignals(True)
        self.clearContents()
        self.setRowCount(rows)
        self.setColumnCount(columns)

        column_width = max(1, viewport_width // columns)
        for column in range(columns):
            self.setColumnWidth(column, column_width)
        for row in range(rows):
            self.setRowHeight(row, self._cell_height)

        for index, year in enumerate(self._years):
            row, column = divmod(index, columns)
            item = QTableWidgetItem(str(year))
            item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.setItem(row, column, item)

        self._select_year(selected_year)
        self.blockSignals(False)

    def _select_year(self, year):
        if year is None:
            return
        for row in range(self.rowCount()):
            for column in range(self.columnCount()):
                item = self.item(row, column)
                if item is not None and item.text() == str(year):
                    self.setCurrentItem(item)
                    return
