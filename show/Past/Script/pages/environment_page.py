#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境监控页 (EnvironmentPage)

展示 SHT30 温湿度、风扇状态和阈值
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont
from collections import deque
from datetime import datetime


class EnvironmentPage(QWidget):
    """环境监控页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        # 历史数据（用于显示趋势，最多保存100个点）
        self.temp_history = deque(maxlen=100)
        self.humidity_history = deque(maxlen=100)

        self._init_ui()
        self._init_connections()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("环境监控")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)

        # ========== 左侧：当前环境数据 ==========
        current_card = self._create_current_card()
        content_layout.addWidget(current_card, 1)

        # ========== 右侧：执行器状态和控制 ==========
        control_card = self._create_control_card()
        content_layout.addWidget(control_card, 1)

        layout.addLayout(content_layout)

        # 阈值设置
        threshold_card = self._create_threshold_card()
        layout.addWidget(threshold_card)

        # 历史趋势（简化版文字显示）
        trend_card = self._create_trend_card()
        layout.addWidget(trend_card)

        layout.addStretch()

    def _create_current_card(self) -> QFrame:
        """创建当前环境数据卡片"""
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
        title = QLabel("当前环境")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 温度显示
        temp_layout = QHBoxLayout()
        temp_icon = QLabel("🌡️")
        temp_icon.setStyleSheet("font-size: 32px;")
        temp_layout.addWidget(temp_icon)

        self.temp_value_label = QLabel("25.0 ℃")
        self.temp_value_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #C4612F;")
        temp_layout.addWidget(self.temp_value_label)
        temp_layout.addStretch()

        layout.addLayout(temp_layout)

        # 湿度显示
        humidity_layout = QHBoxLayout()
        humidity_icon = QLabel("💧")
        humidity_icon.setStyleSheet("font-size: 32px;")
        humidity_layout.addWidget(humidity_icon)

        self.humidity_value_label = QLabel("50.0 %RH")
        self.humidity_value_label.setStyleSheet("font-size: 36px; font-weight: bold; color: #5C635D;")
        humidity_layout.addWidget(self.humidity_value_label)
        humidity_layout.addStretch()

        layout.addLayout(humidity_layout)

        # 更新时间
        self.update_time_label = QLabel("更新时间: --")
        self.update_time_label.setStyleSheet("font-size: 13px; color: #5C635D;")
        layout.addWidget(self.update_time_label)

        layout.addStretch()

        return card

    def _create_control_card(self) -> QFrame:
        """创建执行器控制卡片"""
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
        title = QLabel("执行器状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 风扇状态
        fan_layout = QHBoxLayout()
        fan_label = QLabel("电风扇:")
        fan_label.setStyleSheet("font-size: 16px; color: #1F2421;")
        fan_layout.addWidget(fan_label)

        self.fan_status_label = QLabel("关闭")
        self.fan_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5C635D;")
        fan_layout.addWidget(self.fan_status_label)

        fan_layout.addStretch()
        layout.addLayout(fan_layout)

        # 风扇用途
        self.fan_purpose_label = QLabel("用途: 待机")
        self.fan_purpose_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.fan_purpose_label)

        # 报警器状态
        alarm_layout = QHBoxLayout()
        alarm_label = QLabel("声光报警:")
        alarm_label.setStyleSheet("font-size: 16px; color: #1F2421;")
        alarm_layout.addWidget(alarm_label)

        self.alarm_status_label = QLabel("关闭")
        self.alarm_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5C635D;")
        alarm_layout.addWidget(self.alarm_status_label)

        alarm_layout.addStretch()
        layout.addLayout(alarm_layout)

        # 手动控制按钮
        self.btn_fan_toggle = QPushButton("手动开启风扇")
        self.btn_fan_toggle.setFixedHeight(48)
        self.btn_fan_toggle.setStyleSheet(self._get_button_style())
        self.btn_fan_toggle.clicked.connect(self._toggle_fan)
        layout.addWidget(self.btn_fan_toggle)

        layout.addStretch()

        return card

    def _create_threshold_card(self) -> QFrame:
        """创建阈值设置卡片"""
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
        layout.setSpacing(12)

        # 标题
        title = QLabel("合规阈值")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 阈值信息
        info_layout = QGridLayout()
        info_layout.setSpacing(12)

        # 温度阈值
        temp_label = QLabel("温度范围:")
        temp_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        info_layout.addWidget(temp_label, 0, 0)

        self._temp_threshold_label = QLabel("5 - 40 ℃")
        self._temp_threshold_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #5C635D;")
        info_layout.addWidget(self._temp_threshold_label, 0, 1)

        # 湿度阈值
        humidity_label = QLabel("湿度范围:")
        humidity_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        info_layout.addWidget(humidity_label, 1, 0)

        self._humidity_threshold_label = QLabel("≤ 60 %RH")
        self._humidity_threshold_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #5C635D;")
        info_layout.addWidget(self._humidity_threshold_label, 1, 1)

        # 风扇启动条件
        fan_on_label = QLabel("风扇触发:")
        fan_on_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        info_layout.addWidget(fan_on_label, 2, 0)

        self._fan_trigger_label = QLabel("湿度 > 55% 或 温度 > 35℃")
        self._fan_trigger_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #5C635D;")
        info_layout.addWidget(self._fan_trigger_label, 2, 1)

        # 风扇关闭条件
        fan_off_label = QLabel("风扇关闭:")
        fan_off_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        info_layout.addWidget(fan_off_label, 3, 0)

        fan_off_value = QLabel("湿度 ≤ 50% 且 温度 ≤ 30℃")
        fan_off_value.setStyleSheet("font-size: 14px; font-weight: bold; color: #5C635D;")
        info_layout.addWidget(fan_off_value, 3, 1)

        layout.addLayout(info_layout)

        return card

    def _create_trend_card(self) -> QFrame:
        """创建趋势显示卡片（简化版）"""
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

        # 标题
        title = QLabel("最近趋势")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        self.trend_label = QLabel("温度: 稳定  |  湿度: 稳定")
        self.trend_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        layout.addWidget(self.trend_label)

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
        self.backend.env_updated.connect(self._on_env_updated)

    @pyqtSlot(dict)
    def _on_env_updated(self, data):
        """环境数据更新"""
        # 更新显示
        self.temp_value_label.setText(f"{data['temperature']} ℃")
        self.humidity_value_label.setText(f"{data['humidity']} %RH")

        # 更新时间
        self.update_time_label.setText(f"更新时间: {datetime.now().strftime('%H:%M:%S')}")

        # 动态阈值（来自 cabinet_logic_node）
        h_on = data.get("humidity_on", 55)
        h_off = data.get("humidity_off", 50)
        t_on = data.get("temp_on", 35)
        t_off = data.get("temp_off", 5)
        self._temp_threshold_label.setText(f"{t_off} - {t_on} ℃")
        self._humidity_threshold_label.setText(f"{h_off} - {h_on} %RH")
        self._fan_trigger_label.setText(f"湿度 > {h_on}% 或 温度 > {t_on}℃")

        # 风扇状态
        if data['fan_on']:
            self.fan_status_label.setText("开启")
            self.fan_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #C4612F;")
            self.fan_purpose_label.setText(f"用途: {data['fan_purpose']}")
            self.btn_fan_toggle.setText("手动关闭风扇")
        else:
            self.fan_status_label.setText("关闭")
            self.fan_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5C635D;")
            self.fan_purpose_label.setText("用途: 待机")
            self.btn_fan_toggle.setText("手动开启风扇")

        # 报警器状态
        if data['alarm_on']:
            self.alarm_status_label.setText("开启")
            self.alarm_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #C4612F;")
        else:
            self.alarm_status_label.setText("关闭")
            self.alarm_status_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5C635D;")

        # 记录历史数据
        self.temp_history.append(data['temperature'])
        self.humidity_history.append(data['humidity'])

        # 更新趋势（简化版：计算最近10个点的平均变化）
        if len(self.temp_history) >= 10:
            temp_trend = "上升" if self.temp_history[-1] > self.temp_history[-10] else \
                        "下降" if self.temp_history[-1] < self.temp_history[-10] else "稳定"
            humidity_trend = "上升" if self.humidity_history[-1] > self.humidity_history[-10] else \
                            "下降" if self.humidity_history[-1] < self.humidity_history[-10] else "稳定"
            self.trend_label.setText(f"温度: {temp_trend}  |  湿度: {humidity_trend}")

    def _toggle_fan(self):
        """手动切换风扇"""
        print("[EnvironmentPage] 手动切换风扇")
        if hasattr(self.backend, "request_manual_fan"):
            self.backend.request_manual_fan(not bool(getattr(self.backend, "fan_on", False)), "ui_button")
        # 这里应该调用后端接口
