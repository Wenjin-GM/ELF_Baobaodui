#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frontend-only visual scaling helpers for the low-resolution touch display."""

from __future__ import annotations

import re

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QWidget
from PyQt5.QtWidgets import QApplication


UI_SCALE = 1.35
MAX_FONT_SIZE = 36
DISPLAY_FONT_FAMILY = "SimHei"

PAGE_MARGIN = 12
PAGE_SPACING = 10
CARD_MARGIN = 12
CARD_SPACING = 8

TOP_BAR_HEIGHT = 64
BOTTOM_NAV_HEIGHT = 76
NAV_BUTTON_HEIGHT = 56
ACTION_BUTTON_HEIGHT = 58
TABLE_ROW_HEIGHT = 48


_FONT_RE = re.compile(r"font-size\s*:\s*(\d+)px")
_ORIGINAL_SET_STYLE_SHEET = QWidget.setStyleSheet
_INSTALLED = False


def _scaled_font(match: re.Match) -> str:
    size = int(match.group(1))
    scaled = min(MAX_FONT_SIZE, max(size + 4, int(round(size * UI_SCALE))))
    return f"font-size: {scaled}px"


def scale_stylesheet(style: str) -> str:
    """Scale font-size declarations in existing inline Qt stylesheets."""
    if not style:
        return style
    return _FONT_RE.sub(_scaled_font, style)


def install_large_display_theme() -> None:
    """Patch QWidget stylesheet application once, without touching backend logic."""
    global _INSTALLED
    app = QApplication.instance()
    if app is not None:
        font = QFont(DISPLAY_FONT_FAMILY)
        font.setStyleStrategy(QFont.PreferAntialias)
        font.setWeight(QFont.DemiBold)
        app.setFont(font)
        app.setStyleSheet("""
            QWidget {
                font-family: "SimHei", "Microsoft YaHei", "Arial";
                font-weight: 600;
            }
            QLabel, QPushButton, QTableWidget, QHeaderView::section,
            QComboBox, QSpinBox, QTextEdit {
                font-weight: 600;
            }
        """)
    if _INSTALLED:
        return

    def set_style_sheet_scaled(widget: QWidget, style: str) -> None:
        _ORIGINAL_SET_STYLE_SHEET(widget, scale_stylesheet(style))

    QWidget.setStyleSheet = set_style_sheet_scaled
    _INSTALLED = True
