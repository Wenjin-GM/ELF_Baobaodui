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
from PyQt5.QtGui import QFont


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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题栏
        header_layout = QHBoxLayout()

        title = QLabel("工具盘点")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 刷新按钮
        self.btn_refresh = QPushButton("立即盘点")
        self.btn_refresh.setFixedSize(120, 44)
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["区域", "工具名称", "登记数量", "当前数量", "再借数量", "状态"])
        self.table.setRowCount(5)

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
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #FBF9F5;
                border: none;
                padding: 8px;
                font-weight: bold;
                font-size: 14px;
            }
        """)

        # 设置列宽
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in [0, 2, 3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

        # 初始化表格数据
        self._init_table_data()

        layout.addWidget(self.table)

        # 状态提示
        self.status_label = QLabel("最近盘点: 等待中")
        self.status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.status_label)

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
            self.table.setItem(row, 1, QTableWidgetItem(zone_name))
            self.table.setItem(row, 2, QTableWidgetItem(str(registered)))
            self.table.setItem(row, 3, QTableWidgetItem("--"))
            self.table.setItem(row, 4, QTableWidgetItem("--"))
            self.table.setItem(row, 5, QTableWidgetItem("等待盘点"))

            # 居中对齐
            for col in range(6):
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.tools_updated.connect(self._on_tools_updated)

    @pyqtSlot(dict)
    def _on_tools_updated(self, data):
        """工具数据更新"""
        for zone in data['zones']:
            row = zone['zone_id'] - 1

            self.table.setItem(row, 3, QTableWidgetItem(str(zone['current'])))
            self.table.setItem(row, 4, QTableWidgetItem(str(zone['borrowed'])))
            self.table.setItem(row, 5, QTableWidgetItem(zone['status']))

            # 根据状态设置颜色
            status_item = self.table.item(row, 5)
            if zone['status'] == '正常':
                status_item.setForeground(Qt.darkGreen)
            elif zone['status'] == '缺失':
                status_item.setForeground(Qt.red)
            elif zone['status'] == '错放':
                status_item.setForeground(Qt.darkRed)

            # 居中对齐
            for col in [3, 4, 5]:
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        # 更新状态提示
        from datetime import datetime
        self.status_label.setText(f"最近盘点: {datetime.now().strftime('%H:%M:%S')}")

    def _trigger_check(self):
        """触发盘点"""
        self.status_label.setText("盘点中...")
        if hasattr(self.backend, "request_inventory"):
            self.backend.request_inventory("ui_button")
        # 模拟后端会自动更新数据
        print("[ToolsPage] 触发盘点")
