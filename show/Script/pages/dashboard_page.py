#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
总览页 (DashboardPage)

展示系统整体状态：五区工具、环境、充电、认证、报警
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QFrame, QPushButton, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont


class DashboardPage(QWidget):
    """总览页"""

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

        # 标题
        title = QLabel("系统总览")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 主内容区域（使用网格布局）
        content_layout = QGridLayout()
        content_layout.setSpacing(16)

        # ========== 左侧：五区工具状态 ==========
        self.tools_card = self._create_tools_card()
        content_layout.addWidget(self.tools_card, 0, 0, 2, 1)

        # ========== 右上：环境状态 ==========
        self.env_card = self._create_env_card()
        content_layout.addWidget(self.env_card, 0, 1)

        # ========== 右中：充电状态 ==========
        self.charging_card = self._create_charging_card()
        content_layout.addWidget(self.charging_card, 1, 1)

        # ========== 底部：最近事件 ==========
        self.events_card = self._create_events_card()
        content_layout.addWidget(self.events_card, 2, 0, 1, 2)

        content_layout.setColumnStretch(0, 2)
        content_layout.setColumnStretch(1, 1)

        layout.addLayout(content_layout)

    def _create_tools_card(self) -> QFrame:
        """创建五区工具状态卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("五区工具状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 五区网格
        self.zone_labels = {}
        zones_layout = QGridLayout()
        zones_layout.setSpacing(12)

        zone_positions = [
            (0, 0), (0, 1), (0, 2),  # 1, 2, 3 区
            (1, 0), (1, 1)            # 4, 5 区
        ]

        for i in range(5):
            zone_frame = QFrame()
            zone_frame.setFixedSize(150, 100)
            zone_frame.setStyleSheet("""
                QFrame {
                    background-color: #FBF9F5;
                    border: none;
                    border-radius: 8px;
                }
            """)

            zone_layout = QVBoxLayout(zone_frame)
            zone_layout.setAlignment(Qt.AlignCenter)

            zone_name = QLabel(f"{i+1}区")
            zone_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2421;")
            zone_layout.addWidget(zone_name, alignment=Qt.AlignCenter)

            zone_status = QLabel("正常")
            zone_status.setStyleSheet("font-size: 14px; color: #5C635D;")
            zone_layout.addWidget(zone_status, alignment=Qt.AlignCenter)

            self.zone_labels[i+1] = {"frame": zone_frame, "status": zone_status}

            row, col = zone_positions[i]
            zones_layout.addWidget(zone_frame, row, col)

        layout.addLayout(zones_layout)

        return card

    def _create_env_card(self) -> QFrame:
        """创建环境状态卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("环境状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 温度
        self.temp_label = QLabel("25.0 ℃")
        self.temp_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #C4612F;")
        layout.addWidget(self.temp_label, alignment=Qt.AlignCenter)

        # 湿度
        self.humidity_label = QLabel("50.0 %RH")
        self.humidity_label.setStyleSheet("font-size: 24px; color: #5C635D;")
        layout.addWidget(self.humidity_label, alignment=Qt.AlignCenter)

        # 风扇状态
        self.fan_label = QLabel("风扇：关")
        self.fan_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.fan_label, alignment=Qt.AlignCenter)

        layout.addStretch()

        return card

    def _create_charging_card(self) -> QFrame:
        """创建充电状态卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("1区充电状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 电池盒状态
        self.box_label = QLabel("电池盒：在位")
        self.box_label.setStyleSheet("font-size: 16px; color: #5C635D;")
        layout.addWidget(self.box_label)

        # 充电状态
        self.charging_status_label = QLabel("充电电源：关闭")
        self.charging_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.charging_status_label)

        # 电池位
        self.slots_label = QLabel("电池位：3/4 在位")
        self.slots_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.slots_label)

        layout.addStretch()

        return card

    def _create_events_card(self) -> QFrame:
        """创建最近事件卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("最近事件")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 事件列表（滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")

        scroll_content = QWidget()
        self.events_layout = QVBoxLayout(scroll_content)
        self.events_layout.setAlignment(Qt.AlignTop)
        self.events_layout.setSpacing(8)

        # 初始提示
        empty_label = QLabel("暂无事件")
        empty_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        self.events_layout.addWidget(empty_label)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return card

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.env_updated.connect(self._on_env_updated)
        self.backend.tools_updated.connect(self._on_tools_updated)
        self.backend.charging_updated.connect(self._on_charging_updated)
        self.backend.event_added.connect(self._on_event_added)

    @pyqtSlot(dict)
    def _on_env_updated(self, data):
        """环境数据更新"""
        self.temp_label.setText(f"{data['temperature']} ℃")
        self.humidity_label.setText(f"{data['humidity']} %RH")

        fan_status = "开 / " + data['fan_purpose'] if data['fan_on'] else "关"
        self.fan_label.setText(f"风扇：{fan_status}")

    @pyqtSlot(dict)
    def _on_tools_updated(self, data):
        """工具数据更新"""
        for zone in data['zones']:
            zone_id = zone['zone_id']
            if zone_id in self.zone_labels:
                status_text = zone['status']
                self.zone_labels[zone_id]['status'].setText(status_text)

                # 根据状态更改边框颜色
                frame = self.zone_labels[zone_id]['frame']
                if status_text == "正常":
                    bg_color = "#FBF9F5"
                elif status_text == "缺失":
                    bg_color = "#FFE8E0"  # 浅红背景
                else:
                    bg_color = "#FFE8E0"  # 浅红背景

                frame.setStyleSheet(f"""
                    QFrame {{
                        background-color: {bg_color};
                        border: none;
                        border-radius: 8px;
                    }}
                """)

    @pyqtSlot(dict)
    def _on_charging_updated(self, data):
        """充电数据更新"""
        box_status = "在位" if data['box_present'] else "离位"
        self.box_label.setText(f"电池盒：{box_status}")

        charging_status = "开启" if data['relay_on'] else "关闭"
        self.charging_status_label.setText(f"充电电源：{charging_status}")

        slots_count = sum(data['slots'])
        self.slots_label.setText(f"电池位：{slots_count}/4 在位")

    @pyqtSlot(dict)
    def _on_event_added(self, event):
        """新事件添加"""
        # 清空"暂无事件"提示
        if self.events_layout.count() > 0:
            item = self.events_layout.itemAt(0)
            if item and item.widget():
                widget = item.widget()
                if isinstance(widget, QLabel) and widget.text() == "暂无事件":
                    widget.deleteLater()

        # 添加新事件
        event_label = QLabel(f"[{event['type']}] {event['content']}")
        event_label.setStyleSheet("font-size: 13px; color: #1F2421; padding: 4px;")
        event_label.setWordWrap(True)

        # 根据级别设置颜色
        if event['level'] == 'warning':
            event_label.setStyleSheet("font-size: 13px; color: #C4612F; padding: 4px;")

        self.events_layout.insertWidget(0, event_label)

        # 限制最多显示10条
        while self.events_layout.count() > 10:
            item = self.events_layout.takeAt(10)
            if item and item.widget():
                item.widget().deleteLater()
