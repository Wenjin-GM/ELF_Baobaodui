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
import os
import subprocess
from pathlib import Path
import re
from ui_theme import CARD_MARGIN, CARD_SPACING, PAGE_MARGIN, PAGE_SPACING


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
        layout.setContentsMargins(PAGE_MARGIN, 8, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(8)

        header_layout = self._create_header()
        layout.addLayout(header_layout)

        # 主内容区域（使用网格布局）
        content_layout = QGridLayout()
        content_layout.setSpacing(PAGE_SPACING)

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

        content_layout.setColumnStretch(0, 1)
        content_layout.setColumnStretch(1, 1)

        layout.addLayout(content_layout)


    def _create_header(self) -> QHBoxLayout:
        """创建总览页顶部操作栏"""
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.addStretch()

        self.shutdown_button = QPushButton("⏻")
        self.shutdown_button.setFixedSize(44, 36)
        self.shutdown_button.setToolTip("退出系统")
        self.shutdown_button.setStyleSheet("""
            QPushButton {
                background-color: #FBF9F5;
                border: none;
                border-radius: 8px;
                color: #C4612F;
                font-size: 22px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #F2E3D6;
            }
            QPushButton:pressed {
                background-color: #C4612F;
                color: #FFFFFF;
            }
        """)
        self.shutdown_button.clicked.connect(self._shutdown_system)
        header_layout.addWidget(self.shutdown_button)

        return header_layout

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
        layout.setContentsMargins(CARD_MARGIN, 22, CARD_MARGIN, 12)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignTop)

        # 标题
        title = QLabel("五区工具状态")
        title.setFixedHeight(56)
        title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1F2421; padding: 0px; margin: 0px;")
        layout.addWidget(title)

        # 五区网格
        self.zone_labels = {}
        zones_layout = QGridLayout()
        zones_layout.setSpacing(8)
        zones_layout.setColumnStretch(0, 1)
        zones_layout.setColumnStretch(1, 1)

        zone_positions = [
            (0, 0), (0, 1),  # 1, 2 区
            (1, 0), (1, 1),  # 3, 4 区
            (2, 0),          # 5 区
        ]

        for i in range(5):
            zone_frame = QFrame()
            zone_frame.setMinimumSize(184, 122)
            zone_frame.setStyleSheet("""
                QFrame {
                    background-color: #FBF9F5;
                    border: none;
                    border-radius: 8px;
                }
            """)

            zone_layout = QVBoxLayout(zone_frame)
            zone_layout.setAlignment(Qt.AlignCenter)
            zone_layout.setContentsMargins(6, 6, 6, 6)
            zone_layout.setSpacing(4)

            zone_name = QLabel(f"{i+1}区")
            zone_name.setStyleSheet("font-size: 21px; font-weight: bold; color: #1F2421;")
            zone_layout.addWidget(zone_name, alignment=Qt.AlignCenter)

            zone_status = QLabel("正常")
            zone_status.setStyleSheet("font-size: 20px; font-weight: bold; color: #5C635D;")
            zone_layout.addWidget(zone_status, alignment=Qt.AlignCenter)

            self.zone_labels[i+1] = {"frame": zone_frame, "status": zone_status}

            row, col = zone_positions[i]
            if i == 4:
                zones_layout.addWidget(zone_frame, row, col, 1, 2)
            else:
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
        layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        layout.setSpacing(CARD_SPACING)

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
        layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        layout.setSpacing(CARD_SPACING)

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
        layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        layout.setSpacing(8)

        # 标题
        title = QLabel("最近事件")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 事件列表（滚动区域）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(116)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
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
        scroll.verticalScrollBar().setFixedWidth(34)

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


    def _project_root(self) -> str:
        env_root = os.environ.get("SMART_CABINET_PROJECT_ROOT")
        if env_root:
            return env_root
        return str(Path(__file__).resolve().parents[4])

    def _shutdown_system(self):
        """Stop all cabinet nodes and return to the desktop."""
        project_root = self._project_root()
        script = os.path.join(project_root, "scripts", "stop_smart_cabinet_desktop.sh")
        if not os.path.exists(script):
            script = os.path.join(project_root, "stop_all_ros_nodes.sh")
        try:
            subprocess.Popen(["bash", script], start_new_session=True)
        except Exception as exc:
            print(f"[DashboardPage] failed to stop system: {exc}")

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.env_updated.connect(self._on_env_updated)
        self.backend.tools_updated.connect(self._on_tools_updated)
        self.backend.charging_updated.connect(self._on_charging_updated)
        self.backend.event_added.connect(self._on_event_added)

    _EVENT_TYPE_LABELS = {
        "ui": "界面",
        "inventory": "盘点",
        "auth": "认证",
        "system": "系统",
        "status": "状态",
        "environment": "环境",
        "charging": "充电",
        "warning": "告警",
        "info": "信息",
    }

    _EVENT_REASON_LABELS = {
        "ui_request": "界面触发",
        "ui_node_test": "界面测试",
        "door_closed": "关柜触发",
        "auto_after_auth": "认证后自动触发",
        "manual": "手动触发",
    }

    def _event_type_label(self, value):
        text = str(value or "事件")
        return self._EVENT_TYPE_LABELS.get(text, text)

    def _event_content_label(self, value):
        text = str(value or "")
        if not text:
            return text

        text = re.sub(
            r"request_inventory received:?\s*([^,]*)",
            lambda m: "收到盘点请求" + (f"（{self._EVENT_REASON_LABELS.get(m.group(1).strip(), m.group(1).strip())}）" if m.group(1).strip() else ""),
            text,
        )
        text = re.sub(
            r"request_open received, timeout=([0-9.]+)s",
            lambda m: f"收到开锁请求（超时 {m.group(1)} 秒）",
            text,
        )
        text = re.sub(
            r"request_manual_fan received: on \((.*?)\)",
            lambda m: f"收到手动开启风扇请求（{self._EVENT_REASON_LABELS.get(m.group(1), m.group(1))}）",
            text,
        )
        text = re.sub(
            r"request_manual_fan received: off \((.*?)\)",
            lambda m: f"收到手动关闭风扇请求（{self._EVENT_REASON_LABELS.get(m.group(1), m.group(1))}）",
            text,
        )

        replacements = {
            "auto inventory after first auth scheduled": "认证后自动盘点已触发",
            "vision_node offline; using mock inventory result": "视觉节点离线，使用模拟盘点结果",
            "fan control mode set to auto": "风扇已切换为自动控制",
            "auth failed requested from UI": "界面触发认证失败",
            "response: accepted=True": "响应：已接受",
            "response: accepted=False": "响应：未接受",
            "accepted=True": "已接受",
            "accepted=False": "未接受",
            "failed": "失败",
            "message=": "消息=",
            "request_inventory": "盘点请求",
            "request_open": "开锁请求",
            "request_manual_fan": "风扇控制请求",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def _status_kind(self, status):
        text = str(status or "")
        if text in ("正常", "normal"):
            return "normal"
        if text in ("借出", "borrowed", "missing"):
            return "borrowed"
        if text in ("错放", "misplaced"):
            return "misplaced"
        return "abnormal"

    @pyqtSlot(dict)
    def _on_env_updated(self, data):
        """环境数据更新"""
        self.temp_label.setText(f"{data.get('temperature', '--')} ℃")
        self.humidity_label.setText(f"{data.get('humidity', '--')} %RH")

        fan_status = "开 / " + str(data.get('fan_purpose', '')) if data.get('fan_on') else "关"
        self.fan_label.setText(f"风扇：{fan_status}")

    @pyqtSlot(dict)
    def _on_tools_updated(self, data):
        """工具数据更新"""
        for zone in data.get('zones', []):
            zone_id = zone.get('zone_id')
            if zone_id in self.zone_labels:
                status_text = str(zone.get('status', '异常'))
                self.zone_labels[zone_id]['status'].setText(status_text)

                # 根据状态更改边框颜色
                frame = self.zone_labels[zone_id]['frame']
                status_kind = self._status_kind(status_text)
                if status_kind == "normal":
                    bg_color = "#FBF9F5"
                elif status_kind == "borrowed":
                    bg_color = "#FFF0E5"
                elif status_kind == "misplaced":
                    bg_color = "#FFE8E0"
                else:
                    bg_color = "#FFE8E0"

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
        box_status = "在位" if data.get('box_present') else "离位"
        self.box_label.setText(f"电池盒：{box_status}")

        charging_status = "开启" if data.get('relay_on') else "关闭"
        self.charging_status_label.setText(f"充电电源：{charging_status}")

        slots_count = sum(bool(item) for item in data.get('slots', []))
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
        event_type = self._event_type_label(event.get('type', '事件'))
        event_content = self._event_content_label(event.get('content', ''))
        event_label = QLabel(f"[{event_type}] {event_content}")
        event_label.setStyleSheet("font-size: 13px; color: #1F2421; padding: 4px;")
        event_label.setWordWrap(True)

        # 根据级别设置颜色
        if event.get('level') == 'warning':
            event_label.setStyleSheet("font-size: 13px; color: #C4612F; padding: 4px;")

        self.events_layout.insertWidget(0, event_label)

        # 限制最多显示10条
        while self.events_layout.count() > 10:
            item = self.events_layout.takeAt(10)
            if item and item.widget():
                item.widget().deleteLater()
