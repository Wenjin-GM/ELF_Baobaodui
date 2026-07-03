#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
充电管理页 (ChargingPage)

展示 1 区电池盒充电状态
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont


class ChargingPage(QWidget):
    """充电管理页"""

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
        title = QLabel("充电管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # ========== 左侧：充电状态卡片 ==========
        status_card = self._create_status_card()
        content_layout.addWidget(status_card, 2)

        # ========== 右侧：电池位表格 ==========
        slots_card = self._create_slots_card()
        content_layout.addWidget(slots_card, 1)

        layout.addLayout(content_layout)

        # 操作按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        self.btn_manual_on = QPushButton("手动开启充电")
        self.btn_manual_on.setFixedHeight(56)
        self.btn_manual_on.setStyleSheet(self._get_button_style())
        self.btn_manual_on.clicked.connect(self._manual_charging_on)
        buttons_layout.addWidget(self.btn_manual_on)

        self.btn_manual_off = QPushButton("手动关闭充电")
        self.btn_manual_off.setFixedHeight(56)
        self.btn_manual_off.setStyleSheet(self._get_button_style())
        self.btn_manual_off.clicked.connect(self._manual_charging_off)
        buttons_layout.addWidget(self.btn_manual_off)

        buttons_layout.addStretch()

        layout.addLayout(buttons_layout)

        layout.addStretch()

    def _create_status_card(self) -> QFrame:
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("1区电池盒状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 电池盒在位状态
        self.box_status_label = QLabel("电池盒：检测中")
        self.box_status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #5C635D;")
        layout.addWidget(self.box_status_label)

        # 充电电源状态
        self.relay_status_label = QLabel("充电电源：关闭")
        self.relay_status_label.setStyleSheet("font-size: 18px; color: #5C635D;")
        layout.addWidget(self.relay_status_label)

        # 模块状态
        self.module_status_label = QLabel("充电检测模块：在线")
        self.module_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.module_status_label)

        # 充电策略
        strategy_layout = QHBoxLayout()
        strategy_label = QLabel("充电策略:")
        strategy_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        strategy_layout.addWidget(strategy_label)

        self.strategy_value_label = QLabel("自动")
        self.strategy_value_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #C4612F;")
        strategy_layout.addWidget(self.strategy_value_label)
        strategy_layout.addStretch()

        layout.addLayout(strategy_layout)

        layout.addStretch()

        return card

    def _create_slots_card(self) -> QFrame:
        """创建电池位卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("电池位状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 电池位网格
        self.slot_labels = []
        slots_layout = QGridLayout()
        slots_layout.setSpacing(12)

        for i in range(4):
            slot_frame = QFrame()
            slot_frame.setFixedSize(100, 80)
            slot_frame.setStyleSheet("""
                QFrame {
                    background-color: #FBF9F5;
                    border: none;
                    border-radius: 8px;
                }
            """)

            slot_layout = QVBoxLayout(slot_frame)
            slot_layout.setAlignment(Qt.AlignCenter)

            slot_name = QLabel(f"位置 {i+1}")
            slot_name.setStyleSheet("font-size: 14px; font-weight: bold; color: #1F2421;")
            slot_layout.addWidget(slot_name, alignment=Qt.AlignCenter)

            slot_status = QLabel("--")
            slot_status.setStyleSheet("font-size: 14px; color: #5C635D;")
            slot_layout.addWidget(slot_status, alignment=Qt.AlignCenter)

            self.slot_labels.append({"frame": slot_frame, "status": slot_status})

            row, col = divmod(i, 2)
            slots_layout.addWidget(slot_frame, row, col)

        layout.addLayout(slots_layout)

        layout.addStretch()

        return card

    def _get_button_style(self, bg_color="#FBF9F5", text_color="#1F2421"):
        """获取按钮样式"""
        return f"""
            QPushButton {{
                background-color: {bg_color};
                border: none;
                border-radius: 8px;
                font-size: 16px;
                color: {text_color};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #F2E3D6;
            }}
            QPushButton:pressed {{
                background-color: #C4612F;
                color: #FFFFFF;
            }}
        """

    def _init_connections(self):
        """初始化信号连接"""
        self.backend.charging_updated.connect(self._on_charging_updated)

    @pyqtSlot(dict)
    def _on_charging_updated(self, data):
        """充电数据更新"""
        # 电池盒状态
        if data['box_present']:
            self.box_status_label.setText("电池盒：在位")
            self.box_status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #5C635D;")
        else:
            self.box_status_label.setText("电池盒：离位")
            self.box_status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #C4612F;")

        # 充电电源状态
        if data['relay_on']:
            self.relay_status_label.setText("充电电源：开启")
            self.relay_status_label.setStyleSheet("font-size: 18px; color: #5C635D; font-weight: bold;")
        else:
            self.relay_status_label.setText("充电电源：关闭")
            self.relay_status_label.setStyleSheet("font-size: 18px; color: #5C635D;")

        # 模块状态
        if data['module_online'] and data['status_valid']:
            self.module_status_label.setText("充电检测模块：在线")
            self.module_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        else:
            self.module_status_label.setText("充电检测模块：离线")
            self.module_status_label.setStyleSheet("font-size: 14px; color: #C4612F;")

        # 电池位状态
        if data['module_online'] and data['status_valid']:
            for i, present in enumerate(data['slots']):
                if present:
                    self.slot_labels[i]['status'].setText("在位")
                    self.slot_labels[i]['status'].setStyleSheet("font-size: 14px; color: #5C635D; font-weight: bold;")
                    self.slot_labels[i]['frame'].setStyleSheet("""
                        QFrame {
                            background-color: #E8F5E9;
                            border: none;
                            border-radius: 8px;
                        }
                    """)
                else:
                    self.slot_labels[i]['status'].setText("空位")
                    self.slot_labels[i]['status'].setStyleSheet("font-size: 14px; color: #5C635D;")
                    self.slot_labels[i]['frame'].setStyleSheet("""
                        QFrame {
                            background-color: #FBF9F5;
                            border: none;
                            border-radius: 8px;
                        }
                    """)
        else:
            for i in range(4):
                self.slot_labels[i]['status'].setText("--")
                self.slot_labels[i]['status'].setStyleSheet("font-size: 14px; color: #5C635D;")

    def _manual_charging_on(self):
        """手动开启充电"""
        print("[ChargingPage] 手动开启充电")
        # 这里应该调用后端接口
        self.strategy_value_label.setText("手动")

    def _manual_charging_off(self):
        """手动关闭充电"""
        print("[ChargingPage] 手动关闭充电")
        # 这里应该调用后端接口
        self.strategy_value_label.setText("手动")
