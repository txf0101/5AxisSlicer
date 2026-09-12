from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Semantic colors and fonts shared by the Qt application shell."""

    window: str
    panel: str
    border: str
    text: str
    muted_text: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_subtle: str
    input_background: str
    hover_background: str
    selected_background: str
    disabled_background: str
    disabled_text: str
    success: str
    warning: str
    error: str
    code_background: str
    code_gutter: str
    ui_font_family: str
    code_font_family: str

    def qss_values(self) -> dict[str, str]:
        """Return explicit template values for building a Qt style sheet."""

        return {
            "WINDOW": self.window,
            "PANEL": self.panel,
            "BORDER": self.border,
            "TEXT": self.text,
            "MUTED_TEXT": self.muted_text,
            "PRIMARY": self.primary,
            "PRIMARY_HOVER": self.primary_hover,
            "PRIMARY_PRESSED": self.primary_pressed,
            "PRIMARY_SUBTLE": self.primary_subtle,
            "INPUT_BACKGROUND": self.input_background,
            "HOVER_BACKGROUND": self.hover_background,
            "SELECTED_BACKGROUND": self.selected_background,
            "DISABLED_BACKGROUND": self.disabled_background,
            "DISABLED_TEXT": self.disabled_text,
            "SUCCESS": self.success,
            "WARNING": self.warning,
            "ERROR": self.error,
            "CODE_BACKGROUND": self.code_background,
            "CODE_GUTTER": self.code_gutter,
            "UI_FONT_FAMILY": self.ui_font_family,
            "CODE_FONT_FAMILY": self.code_font_family,
        }


@dataclass(frozen=True, slots=True)
class TypographyTokens:
    """Application type ramp shared by the shell and result-preview page."""

    body_px: int
    secondary_px: int
    label_px: int
    code_px: int
    card_title_px: int
    section_title_px: int
    page_title_px: int
    badge_px: int

    def qss_values(self) -> dict[str, str]:
        return {
            "BODY_FONT_PX": str(self.body_px),
            "SECONDARY_FONT_PX": str(self.secondary_px),
            "CODE_FONT_PX": str(self.code_px),
        }


LIGHT_THEME = ThemeTokens(
    window="#F3F5F7",
    panel="#FFFFFF",
    border="#D7DEE8",
    text="#1F2937",
    muted_text="#667085",
    primary="#2563EB",
    primary_hover="#1D4ED8",
    primary_pressed="#1E40AF",
    primary_subtle="#EFF6FF",
    input_background="#FFFFFF",
    hover_background="#F8FAFC",
    selected_background="#E8F0FE",
    disabled_background="#EEF1F5",
    disabled_text="#98A2B3",
    success="#16845B",
    warning="#B54708",
    error="#C4320A",
    code_background="#F8FAFC",
    code_gutter="#EEF2F6",
    ui_font_family='"Segoe UI", "Microsoft YaHei UI"',
    code_font_family='"Cascadia Mono", "Consolas"',
)


UI_TYPOGRAPHY = TypographyTokens(
    body_px=15,
    secondary_px=13,
    label_px=13,
    code_px=14,
    card_title_px=15,
    section_title_px=16,
    page_title_px=22,
    badge_px=12,
)


__all__ = ["LIGHT_THEME", "ThemeTokens", "TypographyTokens", "UI_TYPOGRAPHY"]
