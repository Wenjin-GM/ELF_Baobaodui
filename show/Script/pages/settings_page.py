#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设置页 (SettingsPage)

管理员使用，普通用户不可进入
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout, QLineEdit,
                             QCheckBox, QSpinBox, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont


class SettingsPage(QWidget):
    """设置页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题
        title = QLabel("环境阈值设置")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 阈值输入
        settings_layout = QGridLayout()
        settings_layout.setSpacing(12)

        # 温度上限
        temp_max_label = QLabel("温度上限 (℃):")
        temp_max_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        settings_layout.addWidget(temp_max_label, 0, 0)

        self.temp_max_spin = QSpinBox()
        self.temp_max_spin.setRange(0, 60)
        self.temp_max_spin.setValue(40)
        self.temp_max_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        settings_layout.addWidget(self.temp_max_spin, 0, 1)

        # 温度下限
        temp_min_label = QLabel("温度下限 (℃):")
        temp_min_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        settings_layout.addWidget(temp_min_label, 1, 0)

        self.temp_min_spin = QSpinBox()
        self.temp_min_spin.setRange(-20, 40)
        self.temp_min_spin.setValue(5)
        self.temp_min_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        settings_layout.addWidget(self.temp_min_spin, 1, 1)

        # 湿度上限
        humidity_max_label = QLabel("湿度上限 (%RH):")
        humidity_max_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        settings_layout.addWidget(humidity_max_label, 2, 0)

        self.humidity_max_spin = QSpinBox()
        self.humidity_max_spin.setRange(0, 100)
        self.humidity_max_spin.setValue(60)
        self.humidity_max_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        settings_layout.addWidget(self.humidity_max_spin, 2, 1)

        # 风扇开启阈值
        fan_on_label = QLabel("风扇开启湿度 (%RH):")
        fan_on_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        settings_layout.addWidget(fan_on_label, 3, 0)

        self.fan_on_spin = QSpinBox()
        self.fan_on_spin.setRange(0, 100)
        self.fan_on_spin.setValue(55)
        self.fan_on_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        settings_layout.addWidget(self.fan_on_spin, 3, 1)

        # 风扇关闭阈值
        fan_off_label = QLabel("风扇关闭湿度 (%RH):")
        fan_off_label.setStyleSheet("font-size: 14px; color: #1F2421;")
        settings_layout.addWidget(fan_off_label, 4, 0)

        self.fan_off_spin = QSpinBox()
        self.fan_off_spin.setRange(0, 100)
        self.fan_off_spin.setValue(50)
        self.fan_off_spin.setStyleSheet("font-size: 14px; padding: 4px;")
        settings_layout.addWidget(self.fan_off_spin, 4, 1)

        layout.addLayout(settings_layout)

        # 保存按钮
        btn_save = QPushButton("保存设置")
        btn_save.setFixedHeight(44)
        btn_save.setStyleSheet(self._get_button_style("#C4612F", "#FFFFFF"))
        btn_save.clicked.connect(self._save_env_settings)
        layout.addWidget(btn_save)

        return card

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

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

        # 按钮组
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(12)

        btn_enter_debug = QPushButton("进入维护模式")
        btn_enter_debug.setFixedHeight(48)
        btn_enter_debug.setStyleSheet(self._get_button_style())
        btn_enter_debug.clicked.connect(self._enter_maintenance)
        buttons_layout.addWidget(btn_enter_debug)

        btn_export_data = QPushButton("导出所有数据")
        btn_export_data.setFixedHeight(48)
        btn_export_data.setStyleSheet(self._get_button_style())
        btn_export_data.clicked.connect(self._export_all_data)
        buttons_layout.addWidget(btn_export_data)

        layout.addLayout(buttons_layout)

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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

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

        btn_temp_unlock = QPushButton("临时开锁")
        btn_temp_unlock.setFixedHeight(48)
        btn_temp_unlock.setStyleSheet(self._get_danger_button_style())
        btn_temp_unlock.clicked.connect(self._temp_unlock)
        buttons_layout.addWidget(btn_temp_unlock)

        btn_clear_records = QPushButton("清空所有记录")
        btn_clear_records.setFixedHeight(48)
        btn_clear_records.setStyleSheet(self._get_danger_button_style())
        btn_clear_records.clicked.connect(self._clear_all_records)
        buttons_layout.addWidget(btn_clear_records)

        btn_reset_system = QPushButton("重置系统")
        btn_reset_system.setFixedHeight(48)
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

    def _save_env_settings(self):
        """保存环境设置"""
        print("[SettingsPage] 保存环境阈值设置")
        QMessageBox.information(self, "设置", "环境阈值设置已保存")

    def _enter_maintenance(self):
        """进入维护模式"""
        reply = QMessageBox.question(self, "确认", "确定进入维护模式吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.state_machine.on_enter_maintenance()

    def _export_all_data(self):
        """导出所有数据"""
        print("[SettingsPage] 导出所有数据")
        QMessageBox.information(self, "导出", "数据导出功能待实现")

    def _temp_unlock(self):
        """临时开锁"""
        reply = QMessageBox.warning(self, "危险操作", "确定要临时开锁吗？\n此操作将记录到日志。",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            print("[SettingsPage] 临时开锁")
            if hasattr(self.backend, "request_temp_unlock"):
                self.backend.request_temp_unlock()
            else:
                self.state_machine.on_cabinet_opened()
                self.backend.simulate_door_opened()

    def _clear_all_records(self):
        """清空所有记录"""
        reply = QMessageBox.critical(self, "危险操作", "确定要清空所有记录吗？\n此操作不可恢复！",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            print("[SettingsPage] 清空所有记录")

    def _reset_system(self):
        """重置系统"""
        reply = QMessageBox.critical(self, "危险操作", "确定要重置系统吗？\n此操作将恢复出厂设置，不可恢复！",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            print("[SettingsPage] 重置系统")
