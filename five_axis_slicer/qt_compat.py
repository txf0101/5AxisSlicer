from __future__ import annotations

# Support both PyQt6 and PyQt5 from one place so the rest of the GUI does not
# have to care about the binding in use.
# 把 PyQt6 和 PyQt5 的兼容处理收在这里，GUI 其他地方就不用到处判断版本了。
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
        QLineEdit,
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
    QT_VERTICAL = Qt.Orientation.Vertical
    PLAIN_TEXT_NO_WRAP = QPlainTextEdit.LineWrapMode.NoWrap

    def qt_exec(app: QApplication) -> int:
        """Run the Qt event loop with the API shape of the active binding.

        按当前 Qt 绑定的接口形式启动事件循环。
        """

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
        QLineEdit,
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
    QT_VERTICAL = Qt.Vertical
    PLAIN_TEXT_NO_WRAP = QPlainTextEdit.NoWrap

    def qt_exec(app: QApplication) -> int:
        """Run the Qt event loop with the API shape of the active binding.

        按当前 Qt 绑定的接口形式启动事件循环。
        """

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
    "QLineEdit",
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
    "QT_VERTICAL",
    "qt_exec",
]
