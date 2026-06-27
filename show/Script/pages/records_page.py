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
from datetime import datetime


class RecordsPage(QWidget):
    """记录查询页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        self.records = []  # 存储所有记录

        self._init_ui()
        self._init_connections()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

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
        self.filter_combo.setFixedWidth(120)
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

        # 导出按钮
        self.btn_export = QPushButton("导出 CSV")
        self.btn_export.setFixedSize(100, 40)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #C4612F;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                color: #FFFFFF;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #A94E22;
            }
        """)
        self.btn_export.clicked.connect(self._export_records)
        header_layout.addWidget(self.btn_export)

        layout.addLayout(header_layout)

        # 记录表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "内容", "级别"])

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
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        layout.addWidget(self.table)

        # 统计信息
        self.stats_label = QLabel("总记录: 0 条")
        self.stats_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.stats_label)

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.event_added.connect(self._on_event_added)

    @pyqtSlot(dict)
    def _on_event_added(self, event):
        """新事件添加"""
        # 添加到记录列表
        record = {
            "timestamp": event['timestamp'],
            "type": event['type'],
            "content": event['content'],
            "level": event['level']
        }
        self.records.append(record)

        # 刷新显示
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
            time_str = datetime.fromisoformat(record['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
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
            level_item = QTableWidgetItem(record['level'])
            level_item.setTextAlignment(Qt.AlignCenter)

            # 根据级别设置颜色
            if record['level'] == 'warning':
                level_item.setForeground(Qt.red)
            elif record['level'] == 'info':
                level_item.setForeground(Qt.darkGreen)

            self.table.setItem(row, 3, level_item)

        # 更新统计
        self.stats_label.setText(f"总记录: {len(self.records)} 条  |  当前显示: {len(filtered_records)} 条")

    def _filter_records(self):
        """筛选记录"""
        self._refresh_table()

    def _export_records(self):
        """导出记录为 CSV"""
        print("[RecordsPage] 导出记录")
        # TODO: 实现 CSV 导出功能
        # 可以使用 QFileDialog 选择保存路径，然后写入 CSV 文件
