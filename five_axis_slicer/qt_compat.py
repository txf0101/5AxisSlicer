from __future__ import annotations

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QAbstractSpinBox,
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt6"
    QT_HORIZONTAL = Qt.Orientation.Horizontal
    PLAIN_TEXT_NO_WRAP = QPlainTextEdit.LineWrapMode.NoWrap

    def qt_exec(app: QApplication) -> int:
        return app.exec()

except ImportError:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QAbstractSpinBox,
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    QT_API = "PyQt5"
    QT_HORIZONTAL = Qt.Horizontal
    PLAIN_TEXT_NO_WRAP = QPlainTextEdit.NoWrap

    def qt_exec(app: QApplication) -> int:
        return app.exec_()

__all__ = [
    "QAbstractSpinBox",
    "QApplication",
    "QCheckBox",
    "QComboBox",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFormLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QLabel",
    "QMainWindow",
    "QMessageBox",
    "QPlainTextEdit",
    "QPushButton",
    "QScrollArea",
    "QSizePolicy",
    "QSpinBox",
    "QSplitter",
    "QVBoxLayout",
    "QWidget",
    "PLAIN_TEXT_NO_WRAP",
    "QT_API",
    "QT_HORIZONTAL",
    "qt_exec",
]
