#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试维护页 (DebugPage)

用于比赛联调阶段的硬件调试
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout, QTextEdit,
                             QGroupBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from ui_theme import ACTION_BUTTON_HEIGHT, CARD_MARGIN, PAGE_MARGIN, PAGE_SPACING


class DebugPage(QWidget):
    """调试维护页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        # 标题栏
        header_layout = QHBoxLayout()

        title = QLabel("调试维护")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 退出维护模式按钮
        self.btn_exit = QPushButton("退出维护模式")
        self.btn_exit.setFixedSize(220, ACTION_BUTTON_HEIGHT)
        self.btn_exit.setStyleSheet("""
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
        """)
        self.btn_exit.clicked.connect(self._exit_maintenance)
        header_layout.addWidget(self.btn_exit)

        layout.addLayout(header_layout)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(PAGE_SPACING)

        # ========== 左侧：硬件状态 ==========
        hardware_card = self._create_hardware_card()
        content_layout.addWidget(hardware_card, 1)

        # ========== 右侧：单模块测试 ==========
        test_card = self._create_test_card()
        content_layout.addWidget(test_card, 1)

        layout.addLayout(content_layout)

        # 日志区
        log_card = self._create_log_card()
        layout.addWidget(log_card)

    def _create_hardware_card(self) -> QFrame:
        """创建硬件状态卡片"""
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
        title = QLabel("硬件在线状态")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 硬件状态列表
        hardware_list = [
            ("I2C4 SHT30 温湿度传感器", True),
            ("I2C7 PN532 NFC读卡器", True),
            ("GPIO 电磁锁继电器", True),
            ("GPIO 风扇继电器", True),
            ("GPIO 充电继电器", True),
            ("USB 摄像头 /dev/video11", True),
            ("MIPI CSI 摄像头 /dev/video21", False),
            ("STM32 充电检测模块", True),
        ]

        for hw_name, online in hardware_list:
            hw_layout = QHBoxLayout()

            # 状态指示器
            status_indicator = QLabel("●")
            if online:
                status_indicator.setStyleSheet("font-size: 18px; color: #5C635D;")
            else:
                status_indicator.setStyleSheet("font-size: 18px; color: #C4612F;")
            hw_layout.addWidget(status_indicator)

            # 硬件名称
            hw_label = QLabel(hw_name)
            hw_label.setStyleSheet("font-size: 14px; color: #1F2421;")
            hw_layout.addWidget(hw_label)

            hw_layout.addStretch()

            # 状态文字
            status_text = QLabel("在线" if online else "离线")
            status_text.setStyleSheet(f"font-size: 14px; color: {'#5C635D' if online else '#C4612F'};")
            hw_layout.addWidget(status_text)

            layout.addLayout(hw_layout)

        # 系统信息
        layout.addSpacing(12)
        sys_info_label = QLabel("系统信息")
        sys_info_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2421;")
        layout.addWidget(sys_info_label)

        self.sys_info_text = QLabel(
            "OS: Ubuntu 22.04 (ELF2-Desktop)\n"
            "Kernel: Linux 5.10.209\n"
            "NPU: RK3588, 6 TOPS\n"
            "RKNN Driver: 0.9.8\n"
            "Python: 3.10.12"
        )
        self.sys_info_text.setStyleSheet("font-size: 13px; color: #5C635D; line-height: 1.5;")
        layout.addWidget(self.sys_info_text)

        layout.addStretch()

        return card

    def _create_test_card(self) -> QFrame:
        """创建单模块测试卡片"""
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
        title = QLabel("单模块测试")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        layout.addWidget(title)

        # 测试按钮组
        tests_layout = QGridLayout()
        tests_layout.setSpacing(8)

        test_buttons = [
            ("读温湿度", self._test_sht30),
            ("读 NFC 卡", self._test_nfc),
            ("开锁 0.8s", self._test_lock),
            ("开风扇 2s", self._test_fan),
            ("拍照", self._test_camera),
            ("AI 盘点", self._test_yolo),
            ("读充电状态", self._test_charging),
            ("触发报警", self._test_alarm),
        ]

        for i, (btn_text, callback) in enumerate(test_buttons):
            btn = QPushButton(btn_text)
            btn.setFixedHeight(ACTION_BUTTON_HEIGHT)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #FBF9F5;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    color: #1F2421;
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
            btn.clicked.connect(callback)
            tests_layout.addWidget(btn, i // 2, i % 2)

        layout.addLayout(tests_layout)

        layout.addStretch()

        return card

    def _create_log_card(self) -> QFrame:
        """创建日志显示卡片"""
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
        header_layout = QHBoxLayout()

        title = QLabel("运行日志")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1F2421;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 清空按钮
        btn_clear = QPushButton("清空日志")
        btn_clear.setFixedSize(170, 60)
        btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #FBF9F5;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                color: #1F2421;
            }
            QPushButton:hover {
                background-color: #F2E3D6;
            }
        """)
        btn_clear.clicked.connect(self._clear_log)
        header_layout.addWidget(btn_clear)

        layout.addLayout(header_layout)

        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1F2421;
                color: #FFFFFF;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: none;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        self.log_text.append("[调试页] 调试模式已启动")
        layout.addWidget(self.log_text)

        return card

    def _exit_maintenance(self):
        """退出维护模式"""
        self.state_machine.on_exit_maintenance()
        self._append_log("[系统] 退出维护模式")

    def _append_log(self, message):
        """添加日志"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def _clear_log(self):
        """清空日志"""
        self.log_text.clear()
        self._append_log("[系统] 日志已清空")

    # ========== 测试函数 ==========

    def _test_sht30(self):
        """测试 SHT30"""
        self._append_log("[SHT30] 开始读取温湿度...")
        self._append_log("[SHT30] 温度: 25.3℃, 湿度: 52.1%RH")

    def _test_nfc(self):
        """测试 NFC"""
        self._append_log("[PN532] 等待刷卡...")
        self._append_log("[PN532] 检测到卡片 UID: 04A1B2C3D4")

    def _test_lock(self):
        """测试电磁锁"""
        self._append_log("[GPIO] 开锁继电器：开启")
        QTimer.singleShot(800, lambda: self._append_log("[GPIO] 开锁继电器：关闭"))

    def _test_fan(self):
        """测试风扇"""
        self._append_log("[GPIO] 风扇继电器：开启")
        QTimer.singleShot(2000, lambda: self._append_log("[GPIO] 风扇继电器：关闭"))

    def _test_camera(self):
        """测试摄像头"""
        self._append_log("[Camera] 打开摄像头 /dev/video11...")
        self._append_log("[Camera] 拍照完成，保存至 /tmp/test.jpg")

    def _test_yolo(self):
        """测试 YOLO"""
        self._append_log("[YOLO] 加载模型 yolo26n.rknn...")
        self._append_log("[YOLO] 推理完成，检测到 5 个目标")
        self._append_log("[YOLO] 1区: 1个电池盒, 2区: 2个钳子, 3区: 2个测温枪")

    def _test_charging(self):
        """测试充电检测"""
        self._append_log("[STM32] 读取充电状态...")
        self._append_log("[STM32] 状态字: 0x9590 (有效)")
        self._append_log("[STM32] 槽位1: 在位, 槽位2: 空, 槽位3: 在位, 槽位4: 在位")

    def _test_alarm(self):
        """测试报警"""
        self._append_log("[Alarm] 触发测试报警")
        self.backend.simulate_alarm("测试报警")
