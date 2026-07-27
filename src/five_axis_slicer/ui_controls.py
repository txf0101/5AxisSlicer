"""Small Qt control factories shared by the application shell."""

from collections.abc import Callable

from PyQt5.QtWidgets import QPushButton


def action_button(
    callback: Callable[..., object], *args: object, primary: bool = False
) -> QPushButton:
    button = QPushButton()
    if primary:
        button.setObjectName("primaryButton")
    button.clicked.connect(lambda _checked=False: callback(*args))
    return button


__all__ = ["action_button"]
