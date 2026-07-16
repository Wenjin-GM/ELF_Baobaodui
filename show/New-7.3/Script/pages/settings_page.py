#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设置页 (SettingsPage)

管理员使用，普通用户不可进入
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout, QLineEdit,
                             QCheckBox, QSpinBox, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QFont
from ui_theme import ACTION_BUTTON_HEIGHT, CARD_MARGIN, PAGE_MARGIN, PAGE_SPACING
import time


class SettingsPage(QWidget):
    """设置页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend
        self._syncing_thresholds = False
        self._last_sent_thresholds = None
        self._ignore_threshold_echo_until = 0.0

        self._init_ui()
        self._init_connections()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        # 标题
        title = QLabel("系统设置")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 权限提示
        auth_label = QLabel("⚠️ 此页面需要管理员权限")
        auth_label.setStyleSheet("font-size: 14px; color: #C4612F; font-weight: bold;")
        layout.addWidget(auth_label)

        # 环境阈值设置
        env_card = self._create_env_settings_card()
        layout.addWidget(env_card)

        # 系统控制
        control_card = self._create_control_card()
        layout.addWidget(control_card)

        # 危险操作区
        danger_card = self._create_danger_card()
        layout.addWidget(danger_card)

        layout.addStretch()

    def _create_env_settings_card(self) -> QFrame:
        """创建环境阈值设置卡片"""
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
        layout.setSpacing(10)

        # 标题
        title = QLabel("环境阈值设置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 阈值输入
        settings_layout = QGridLayout()
        settings_layout.setHorizontalSpacing(18)
        settings_layout.setVerticalSpacing(18)

        # 风扇开启温度  (temp_on)
        label = QLabel("风扇开启温度 (℃):")
        label.setStyleSheet("font-size: 17px; font-weight: bold; color: #1F2421;")
        settings_layout.addWidget(label, 0, 0)

        self.temp_on_spin = self._create_threshold_spin(0, 60, 35, " ℃")
        settings_layout.addLayout(self._create_threshold_control(self.temp_on_spin), 0, 1)

        # 风扇开启湿度  (humidity_on)
        label = QLabel("风扇开启湿度 (%RH):")
        label.setStyleSheet("font-size: 17px; font-weight: bold; color: #1F2421;")
        settings_layout.addWidget(label, 1, 0)

        self.humidity_on_spin = self._create_threshold_spin(0, 100, 55, " %RH")
        settings_layout.addLayout(self._create_threshold_control(self.humidity_on_spin), 1, 1)

        layout.addLayout(settings_layout)

        # 保存按钮
        btn_save = QPushButton("保存设置")
        btn_save.setFixedHeight(ACTION_BUTTON_HEIGHT)
        btn_save.setStyleSheet(self._get_button_style("#C4612F", "#FFFFFF"))
        btn_save.clicked.connect(self._save_env_settings)
        layout.addWidget(btn_save)

        return card

    def _create_threshold_spin(self, minimum, maximum, value, suffix):
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setAlignment(Qt.AlignCenter)
        spin.setMinimumHeight(ACTION_BUTTON_HEIGHT)
        spin.setMinimumWidth(180)
        spin.setStyleSheet("""
            QSpinBox {
                background-color: #FBF9F5;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
                color: #1F2421;
                padding: 6px 12px;
            }
        """)
        return spin

    def _create_threshold_control(self, spin):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(spin, 1)

        btn_minus = QPushButton("-")
        btn_plus = QPushButton("＋")
        for btn, color, pressed in (
            (btn_minus, "#D94B3D", "#B83D31"),
            (btn_plus, "#2E9B55", "#247D44"),
        ):
            btn.setFixedSize(72, ACTION_BUTTON_HEIGHT)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: none;
                    border-radius: 8px;
                    font-size: 26px;
                    color: #FFFFFF;
                    font-weight: bold;
                }}
                QPushButton:pressed {{
                    background-color: {pressed};
                }}
            """)

        btn_minus.clicked.connect(lambda: self._adjust_threshold(spin, -1))
        btn_plus.clicked.connect(lambda: self._adjust_threshold(spin, 1))
        row.addWidget(btn_minus)
        row.addWidget(btn_plus)
        return row

    def _adjust_threshold(self, spin, delta):
        spin.setValue(spin.value() + delta)

    def _init_connections(self):
        self.threshold_update_timer = QTimer(self)
        self.threshold_update_timer.setSingleShot(True)
        self.threshold_update_timer.setInterval(900)
        self.threshold_update_timer.timeout.connect(self._on_threshold_update_idle)

        for spin in (
            self.temp_on_spin,
            self.humidity_on_spin,
        ):
            spin.valueChanged.connect(self._schedule_env_threshold_update)

        if hasattr(self.backend, "env_updated"):
            self.backend.env_updated.connect(self._on_env_updated)

    def _create_control_card(self) -> QFrame:
        """创建系统控制卡片"""
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
        layout.setSpacing(10)

        # 标题
        title = QLabel("系统控制")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 自动控制开关
        self.auto_fan_checkbox = QCheckBox("自动风扇控制")
        self.auto_fan_checkbox.setChecked(True)
        self.auto_fan_checkbox.setStyleSheet("font-size: 14px; color: #1F2421;")
        layout.addWidget(self.auto_fan_checkbox)

        self.auto_charging_checkbox = QCheckBox("自动充电控制")
        self.auto_charging_checkbox.setChecked(True)
        self.auto_charging_checkbox.setStyleSheet("font-size: 14px; color: #1F2421;")
        layout.addWidget(self.auto_charging_checkbox)

        return card

    def _create_danger_card(self) -> QFrame:
        """创建危险操作卡片"""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFF5F5;
                border: none;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
        layout.setSpacing(10)

        # 标题
        title = QLabel("⚠️ 危险操作")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #C4612F;")
        layout.addWidget(title)

        warning_label = QLabel("以下操作需要二次确认，请谨慎执行")
        warning_label.setStyleSheet("font-size: 13px; color: #5C635D;")
        layout.addWidget(warning_label)

        # 危险按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        btn_clear_records = QPushButton("清空所有记录")
        btn_clear_records.setFixedHeight(ACTION_BUTTON_HEIGHT)
        btn_clear_records.setStyleSheet(self._get_danger_button_style())
        btn_clear_records.clicked.connect(self._clear_all_records)
        buttons_layout.addWidget(btn_clear_records)

        btn_reset_system = QPushButton("重置系统")
        btn_reset_system.setFixedHeight(ACTION_BUTTON_HEIGHT)
        btn_reset_system.setStyleSheet(self._get_danger_button_style())
        btn_reset_system.clicked.connect(self._reset_system)
        buttons_layout.addWidget(btn_reset_system)

        layout.addLayout(buttons_layout)

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

    def _get_danger_button_style(self):
        """获取危险按钮样式"""
        return """
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
        """

    def _current_thresholds(self):
        return {
            "humidity_on": self.humidity_on_spin.value(),
            "humidity_off": self.humidity_on_spin.value(),
            "temp_on": self.temp_on_spin.value(),
            "temp_off": self.temp_on_spin.value(),
        }

    def _schedule_env_threshold_update(self):
        if self._syncing_thresholds:
            return
        self._ignore_threshold_echo_until = time.monotonic() + 3.0
        self.threshold_update_timer.start()

    def _on_threshold_update_idle(self):
        self._ignore_threshold_echo_until = time.monotonic() + 3.0
        self._save_env_settings(show_message=False)

    @pyqtSlot(dict)
    def _on_env_updated(self, data):
        if not data:
            return
        keys = ("humidity_on", "humidity_off", "temp_on", "temp_off")
        if not any(key in data for key in keys):
            return
        if self.threshold_update_timer.isActive() or time.monotonic() < self._ignore_threshold_echo_until:
            return

        values = {
            "humidity_on": int(round(float(data.get("humidity_on", self.humidity_on_spin.value())))),
            "temp_on": int(round(float(data.get("temp_on", self.temp_on_spin.value())))),
        }
        current_visible = {
            "humidity_on": self.humidity_on_spin.value(),
            "temp_on": self.temp_on_spin.value(),
        }
        if values == current_visible:
            return

        self._syncing_thresholds = True
        try:
            self.humidity_on_spin.setValue(values["humidity_on"])
            self.temp_on_spin.setValue(values["temp_on"])
        finally:
            self._syncing_thresholds = False

    def _save_env_settings(self, show_message=True):
        """保存环境设置——调用 /cabinet/update_env_thresholds service"""
        thresholds = self._current_thresholds()
        if thresholds == self._last_sent_thresholds and not show_message:
            return

        h_on = thresholds["humidity_on"]
        h_off = thresholds["humidity_off"]
        t_on = thresholds["temp_on"]
        t_off = thresholds["temp_off"]
        if hasattr(self.backend, "update_env_thresholds"):
            self.backend.update_env_thresholds(
                humidity_on=h_on, humidity_off=h_off,
                temp_on=t_on, temp_off=t_off,
            )
            self._last_sent_thresholds = thresholds
            self._ignore_threshold_echo_until = time.monotonic() + 3.0
            if show_message:
                QMessageBox.information(self, "设置",
                    f"环境阈值已更新:\n风扇开启湿度 {h_on}%RH\n"
                    f"风扇开启温度 {t_on}℃")
        else:
            if show_message:
                QMessageBox.warning(self, "设置", "后端不支持在线更新阈值")

    def _clear_all_records(self):
        """清空所有记录"""
        records_page = None
        main_window = self.window()
        for page in getattr(main_window, "pages", {}).values():
            if hasattr(page, "clear_records"):
                records_page = page
                break

        if records_page is None:
            print("[SettingsPage] 未找到记录页，无法清空记录")
            return

        records_page.clear_records()
        print("[SettingsPage] 已清空所有记录")

    def _reset_system(self):
        """重置系统"""
        reply = QMessageBox.critical(self, "危险操作", "确定要重置系统吗？\n此操作将恢复出厂设置，不可恢复！",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            print("[SettingsPage] 重置系统")
