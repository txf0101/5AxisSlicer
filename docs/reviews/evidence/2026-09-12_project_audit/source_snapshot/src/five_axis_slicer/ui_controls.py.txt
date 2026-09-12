"""Small Qt controls shared by the application shell."""

from collections.abc import Callable

from PyQt5.QtCore import QEvent, QObject, QTimer
from PyQt5.QtWidgets import QDoubleSpinBox, QPushButton


class OptionalDoubleSpinBox(QDoubleSpinBox):
    """Let direct typing replace the label shown for an unset minimum value."""

    def __init__(self) -> None:
        super().__init__()
        self.lineEdit().installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if (
            watched is self.lineEdit()
            and self.specialValueText()
            and self.value() == self.minimum()
        ):
            if event.type() == QEvent.FocusIn:
                QTimer.singleShot(0, self._select_unset_text)
            elif event.type() == QEvent.MouseButtonRelease:
                self._select_unset_text()
                return True
        return super().eventFilter(watched, event)

    def _select_unset_text(self) -> None:
        if self.value() == self.minimum():
            self.selectAll()


def action_button(
    callback: Callable[..., object], *args: object, primary: bool = False
) -> QPushButton:
    button = QPushButton()
    if primary:
        button.setObjectName("primaryButton")
    button.clicked.connect(lambda _checked=False: callback(*args))
    return button


__all__ = ["OptionalDoubleSpinBox", "action_button"]
