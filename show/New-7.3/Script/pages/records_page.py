#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
记录查询页 (RecordsPage)

查询本地 log 或数据库记录
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QTableWidget, QTableWidgetItem,
                             QComboBox, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from ui_theme import ACTION_BUTTON_HEIGHT, PAGE_MARGIN, PAGE_SPACING, TABLE_ROW_HEIGHT


class RecordsPage(QWidget):
    """记录查询页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        self.records = []

        self._init_ui()
        self._init_connections()
        self._load_historical_records()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        # 标题栏和筛选
        header_layout = QHBoxLayout()

        title = QLabel("操作记录")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 记录类型筛选
        filter_label = QLabel("类型:")
        filter_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        header_layout.addWidget(filter_label)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "认证", "开柜", "关柜", "盘点", "充电", "环境", "报警"])
        self.filter_combo.setFixedSize(160, ACTION_BUTTON_HEIGHT)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-size: 14px;
            }
        """)
        self.filter_combo.currentTextChanged.connect(self._filter_records)
        header_layout.addWidget(self.filter_combo)

        layout.addLayout(header_layout)

        # 记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "内容", "级别"])
        self.table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT)
        self.table.verticalHeader().setMinimumSectionSize(TABLE_ROW_HEIGHT)
        self.table.verticalHeader().setVisible(False)

        # 设置表格样式
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
                gridline-color: #E7E1D7;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 10px;
            }
            QHeaderView::section {
                background-color: #FBF9F5;
                border: none;
                padding: 10px;
                font-weight: bold;
                font-size: 14px;
            }
            QScrollBar:vertical {
                background: #F1EDE6;
                width: 34px;
                margin: 0px;
                border-radius: 12px;
            }
            QScrollBar::handle:vertical {
                background: #C4612F;
                min-height: 52px;
                border-radius: 12px;
            }
            QScrollBar::handle:vertical:pressed {
                background: #A94F25;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }
        """)
        self.table.verticalScrollBar().setFixedWidth(34)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        layout.addWidget(self.table)

        # 统计信息
        self.stats_label = QLabel("总记录: 0 条")
        self.stats_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.stats_label)

    @staticmethod
    def _parse_ts(ts_str: str) -> str:
        """Parse ISO timestamp, return formatted string or raw if unparseable."""
        try:
            s = ts_str.replace(" ", "T")
            if s[-5] in "+-" and ":" not in s[-5:]:
                s = s[:-2] + ":" + s[-2:]
            dt = datetime.fromisoformat(s)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts_str

    _DISPLAY_TYPES = {"认证", "盘点", "inventory", "开柜"}

    def _load_historical_records(self):
        """Load auth + inventory events from data/events/."""
        for candidate in (
            Path.home() / "smart_tool_cabinet" / "data" / "events",
            Path(__file__).resolve().parents[3] / "data" / "events",
        ):
            if candidate.is_dir():
                files = sorted(candidate.glob("*_event.json"), reverse=True)
                for f in files[:200]:
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        if d.get("type", "") not in self._DISPLAY_TYPES:
                            continue
                        self.records.append({
                            "timestamp": d.get("timestamp", ""),
                            "type": d.get("type", ""),
                            "content": d.get("content", ""),
                            "level": d.get("level", "info"),
                        })
                    except Exception:
                        pass
                break
        self._refresh_table()

    def clear_records(self):
        """Clear records from the page and persisted event files."""
        self.records.clear()

        for candidate in (
            Path.home() / "smart_tool_cabinet" / "data" / "events",
            Path(__file__).resolve().parents[3] / "data" / "events",
        ):
            if not candidate.is_dir():
                continue
            for event_file in candidate.glob("*_event.json"):
                try:
                    d = json.loads(event_file.read_text(encoding="utf-8"))
                    if d.get("type", "") in self._DISPLAY_TYPES:
                        event_file.unlink()
                except Exception:
                    pass

        self._refresh_table()

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.event_added.connect(self._on_event_added)

    @pyqtSlot(dict)
    def _on_event_added(self, event):
        """新事件——只收录认证/盘点/开柜"""
        etype = event.get("type", event.get("event_type", ""))
        if etype not in self._DISPLAY_TYPES:
            return
        record = {
            "timestamp": event.get("timestamp", ""),
            "type": etype,
            "content": event.get("content", ""),
            "level": event.get("level", "info"),
        }
        self.records.append(record)
        self._refresh_table()

    def _refresh_table(self):
        """刷新表格显示"""
        # 根据筛选条件过滤记录
        filter_type = self.filter_combo.currentText()
        if filter_type == "全部":
            filtered_records = self.records
        else:
            filtered_records = [r for r in self.records if r['type'] == filter_type]

        # 清空表格
        self.table.setRowCount(0)

        # 按时间倒序显示（最新的在前面）
        for record in reversed(filtered_records):
            row = self.table.rowCount()
            self.table.insertRow(row)

            # 时间
            time_str = self._parse_ts(record.get('timestamp', ''))
            time_item = QTableWidgetItem(time_str)
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, time_item)

            # 类型
            type_item = QTableWidgetItem(record['type'])
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, type_item)

            # 内容
            content_item = QTableWidgetItem(record['content'])
            self.table.setItem(row, 2, content_item)

            # 级别
            level = str(record.get('level', 'info'))
            level_text = {
                "info": "信息",
                "warning": "警告",
            }.get(level, level)
            level_item = QTableWidgetItem(level_text)
            level_item.setTextAlignment(Qt.AlignCenter)

            # 根据级别设置颜色
            if level == 'warning':
                level_item.setForeground(Qt.red)
            elif level == 'info':
                level_item.setForeground(Qt.darkGreen)

            self.table.setItem(row, 3, level_item)

        # 更新统计
        self.stats_label.setText(f"总记录: {len(self.records)} 条  |  当前显示: {len(filtered_records)} 条")

    def _filter_records(self):
        """筛选记录"""
        self._refresh_table()
