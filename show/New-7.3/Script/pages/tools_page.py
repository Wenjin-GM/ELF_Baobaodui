#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具盘点页 (ToolsPage)

展示柜内五区工具识别结果
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout, QTableWidget,
                             QTableWidgetItem, QHeaderView)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap
from ui_theme import ACTION_BUTTON_HEIGHT, PAGE_MARGIN, PAGE_SPACING, TABLE_ROW_HEIGHT
from pathlib import Path


class ToolsPage(QWidget):
    """工具盘点页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        self._init_ui()
        self._init_connections()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        # 标题栏
        header_layout = QHBoxLayout()

        title = QLabel("工具盘点")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 刷新按钮
        self.btn_refresh = QPushButton("立即盘点")
        self.btn_refresh.setFixedSize(190, ACTION_BUTTON_HEIGHT)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #C4612F;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #A94E22;
            }
            QPushButton:pressed {
                background-color: #8B3E1C;
            }
        """)
        self.btn_refresh.clicked.connect(self._trigger_check)
        header_layout.addWidget(self.btn_refresh)

        layout.addLayout(header_layout)

        # 五区工具表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["区域", "工具名称", "工具示意图", "登记数量", "当前数量", "在借数量", "状态"])
        self.table.setRowCount(5)
        self.table.verticalHeader().setDefaultSectionSize(104)
        self.table.verticalHeader().setMinimumSectionSize(104)
        self.table.verticalHeader().setVisible(False)

        # 设置表格样式
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
                gridline-color: #E7E1D7;
                font-size: 15px;
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
        """)

        # 设置列宽
        header = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        # 初始化表格数据
        self._init_table_data()

        layout.addWidget(self.table)

        # 状态提示
        self.status_label = QLabel("最近盘点: 等待中")
        self.status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.status_label)

    _TOOL_IMAGE_FILES = {
        1: "tool_battery_box.png",
        2: "tool_pliers.png",
        3: "tool_thermometer.png",
        4: "tool_multimeter.png",
        5: "tool_gloves.png",
    }

    def _asset_path(self, filename: str) -> Path:
        return Path(__file__).resolve().parents[1] / "resources" / "ui_images" / filename

    def _tool_image_widget(self, zone_id: int):
        filename = self._TOOL_IMAGE_FILES.get(zone_id)
        pixmap = QPixmap(str(self._asset_path(filename))) if filename else QPixmap()
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(190, 96)
        label.setStyleSheet("background: transparent; padding: 2px;")
        if not pixmap.isNull():
            label.setPixmap(pixmap.scaled(184, 94, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        return label

    def _init_table_data(self):
        """初始化表格数据"""
        zones_info = [
            ("1区", "电池盒充电区", 1),
            ("2区", "钳子区", 2),
            ("3区", "测温枪区", 2),
            ("4区", "万用表区", 2),
            ("5区", "绝缘手套区", 2)
        ]

        for row, (zone_id, zone_name, registered) in enumerate(zones_info):
            self.table.setItem(row, 0, QTableWidgetItem(zone_id))
            name_item = QTableWidgetItem(zone_name)
            name_font = name_item.font()
            name_font.setPointSize(16)
            name_font.setBold(True)
            name_item.setFont(name_font)
            self.table.setItem(row, 1, name_item)
            self.table.setCellWidget(row, 2, self._tool_image_widget(row + 1))
            self.table.setItem(row, 3, QTableWidgetItem(str(registered)))
            self.table.setItem(row, 4, QTableWidgetItem("--"))
            self.table.setItem(row, 5, QTableWidgetItem("--"))
            self.table.setItem(row, 6, QTableWidgetItem("等待盘点"))
            self.table.setRowHeight(row, 104)

            # 居中对齐
            for col in [0, 1, 3, 4, 5, 6]:
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.tools_updated.connect(self._on_tools_updated)

    def _status_kind(self, status):
        text = str(status or "")
        if text in ("\u6b63\u5e38", "normal"):
            return "normal"
        if text in ("\u501f\u51fa", "borrowed", "\u7f3a\u5931", "missing"):
            return "borrowed"
        if text in ("\u9519\u653e", "misplaced"):
            return "misplaced"
        return "abnormal"

    @pyqtSlot(dict)
    def _on_tools_updated(self, data):
        """工具数据更新"""
        for zone in data.get('zones', []):
            row = int(zone.get('zone_id', 0) or 0) - 1
            if row < 0 or row >= self.table.rowCount():
                continue

            self.table.setItem(row, 4, QTableWidgetItem(str(zone.get('current', '--'))))
            self.table.setItem(row, 5, QTableWidgetItem(str(zone.get('borrowed', '--'))))
            status_new_item = QTableWidgetItem(str(zone.get('status', '异常')))
            status_font = status_new_item.font()
            status_font.setPointSize(17)
            status_font.setBold(True)
            status_new_item.setFont(status_font)
            self.table.setItem(row, 6, status_new_item)

            # 根据状态设置颜色
            status_item = self.table.item(row, 6)
            status_kind = self._status_kind(zone.get('status'))
            if status_kind == 'normal':
                status_item.setForeground(Qt.darkGreen)
            elif status_kind == 'borrowed':
                status_item.setForeground(Qt.red)
            elif status_kind == 'misplaced':
                status_item.setForeground(Qt.darkRed)
            else:
                status_item.setForeground(Qt.red)

            # 居中对齐
            for col in [4, 5, 6]:
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        # 更新状态提示
        from datetime import datetime
        self.status_label.setText(f"最近盘点: {datetime.now().strftime('%H:%M:%S')}")

    def _trigger_check(self):
        """触发盘点"""
        self.status_label.setText("盘点中...")
        window = self.window()
        if hasattr(window, "keep_tools_page_for_inventory"):
            window.keep_tools_page_for_inventory()
        if hasattr(self.backend, "request_inventory"):
            self.backend.request_inventory("ui_button")
        # 模拟后端会自动更新数据
        print("[ToolsPage] 触发盘点")
