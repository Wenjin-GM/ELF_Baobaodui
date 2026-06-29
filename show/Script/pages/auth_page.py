#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证页 (AuthPage)

展示 NFC 刷卡、人脸识别、开柜授权结果
"""

import os

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont, QPixmap


class AuthPage(QWidget):
    """认证页"""

    def __init__(self, state_machine, backend):
        super().__init__()
        self.state_machine = state_machine
        self.backend = backend
        self.camera_label = None

        self._init_ui()
        self._init_connections()

    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # ========== 左侧：摄像头预览区 ==========
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background-color: #1F2421;
                border: none;
                border-radius: 12px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignCenter)

        camera_placeholder = QLabel("摄像头预览区")
        camera_placeholder.setStyleSheet("font-size: 20px; color: #FFFFFF;")
        left_layout.addWidget(camera_placeholder, alignment=Qt.AlignCenter)

        self.camera_label = QLabel("camera preview")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumSize(420, 300)
        self.camera_label.setStyleSheet("font-size: 20px; color: #FFFFFF;")
        left_layout.addWidget(self.camera_label, alignment=Qt.AlignCenter)

        layout.addWidget(left_panel, 2)

        # ========== 右侧：认证信息和操作 ==========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(16)

        # 标题
        title = QLabel("身份认证")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #1F2421;")
        right_layout.addWidget(title)

        # 认证状态卡片
        auth_card = QFrame()
        auth_card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
                border-radius: 12px;
            }
        """)
        auth_layout = QVBoxLayout(auth_card)
        auth_layout.setContentsMargins(16, 16, 16, 16)
        auth_layout.setSpacing(12)

        # NFC 状态
        nfc_title = QLabel("NFC 刷卡")
        nfc_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2421;")
        auth_layout.addWidget(nfc_title)

        self.nfc_status_label = QLabel("等待刷卡")
        self.nfc_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        auth_layout.addWidget(self.nfc_status_label)

        self.card_uid_label = QLabel("卡 UID: --")
        self.card_uid_label.setStyleSheet("font-size: 13px; color: #5C635D;")
        auth_layout.addWidget(self.card_uid_label)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet("background-color: #E7E1D7;")
        auth_layout.addWidget(line1)

        # 人脸识别
        face_title = QLabel("人脸识别")
        face_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2421;")
        auth_layout.addWidget(face_title)

        self.face_status_label = QLabel("未识别")
        self.face_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        auth_layout.addWidget(self.face_status_label)

        self.confidence_label = QLabel("置信度: --")
        self.confidence_label.setStyleSheet("font-size: 13px; color: #5C635D;")
        auth_layout.addWidget(self.confidence_label)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet("background-color: #E7E1D7;")
        auth_layout.addWidget(line2)

        # 用户权限
        auth_result_title = QLabel("认证结果")
        auth_result_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #1F2421;")
        auth_layout.addWidget(auth_result_title)

        self.user_name_label = QLabel("用户: --")
        self.user_name_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        auth_layout.addWidget(self.user_name_label)

        self.role_label = QLabel("权限: --")
        self.role_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        auth_layout.addWidget(self.role_label)

        right_layout.addWidget(auth_card)

        # 操作按钮区
        buttons_layout = QGridLayout()
        buttons_layout.setSpacing(12)

        # 模拟认证成功按钮（演示用）
        self.btn_auth_user = QPushButton("模拟普通用户认证")
        self.btn_auth_user.setFixedHeight(56)
        self.btn_auth_user.setStyleSheet(self._get_button_style())
        self.btn_auth_user.clicked.connect(self._simulate_user_auth)
        buttons_layout.addWidget(self.btn_auth_user, 0, 0)

        self.btn_auth_admin = QPushButton("模拟管理员认证")
        self.btn_auth_admin.setFixedHeight(56)
        self.btn_auth_admin.setStyleSheet(self._get_button_style())
        self.btn_auth_admin.clicked.connect(self._simulate_admin_auth)
        buttons_layout.addWidget(self.btn_auth_admin, 0, 1)

        self.btn_open_cabinet = QPushButton("申请开柜")
        self.btn_open_cabinet.setFixedHeight(56)
        self.btn_open_cabinet.setStyleSheet(self._get_button_style("#C4612F", "#FFFFFF"))
        self.btn_open_cabinet.clicked.connect(self._request_open_cabinet)
        buttons_layout.addWidget(self.btn_open_cabinet, 1, 0)

        self.btn_logout = QPushButton("退出登录")
        self.btn_logout.setFixedHeight(56)
        self.btn_logout.setStyleSheet(self._get_button_style())
        self.btn_logout.clicked.connect(self._logout)
        buttons_layout.addWidget(self.btn_logout, 1, 1)

        right_layout.addLayout(buttons_layout)
        right_layout.addStretch()

        layout.addWidget(right_panel, 1)

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
        self.backend.auth_updated.connect(self._on_auth_updated)
        if hasattr(self.backend, "preview_frame"):
            self.backend.preview_frame.connect(self._on_preview_frame)

    @pyqtSlot(QPixmap)
    def _on_preview_frame(self, pixmap):
        """Receive frame from /face/preview topic."""
        if self.camera_label is not None:
            self.camera_label.setPixmap(pixmap.scaled(
                self.camera_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            ))

    def closeEvent(self, event):
        super().closeEvent(event)

    @pyqtSlot(dict)
    def _on_auth_updated(self, data):
        """认证数据更新"""
        if data['success']:
            self.nfc_status_label.setText("已授权")
            self.nfc_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")

            if data.get('card_uid'):
                self.card_uid_label.setText(f"卡 UID: {data['card_uid']}")

            self.user_name_label.setText(f"用户: {data['user_name']}")

            role_text = "管理员" if data['role'] == 'admin' else "普通用户"
            self.role_label.setText(f"权限: {role_text}")

            if data['method'] == '人脸识别':
                self.face_status_label.setText(f"已识别: {data['user_name']}")
                if data.get('confidence'):
                    self.confidence_label.setText(f"置信度: {data['confidence']:.2f}")
        else:
            self.nfc_status_label.setText("未授权")
            self.nfc_status_label.setStyleSheet("font-size: 14px; color: #C4612F;")

            if data.get('card_uid'):
                self.card_uid_label.setText(f"卡 UID: {data['card_uid']} (未授权)")

            self.user_name_label.setText("用户: --")
            self.role_label.setText("权限: --")

    def _simulate_user_auth(self):
        """模拟普通用户认证"""
        self.backend.simulate_auth_success("高硕", "user")
        if not hasattr(self.backend, "summary_updated"):
            self.state_machine.on_auth_success("高硕", "user")

    def _simulate_admin_auth(self):
        """模拟管理员认证"""
        self.backend.simulate_auth_success("赵增辉", "admin")
        if not hasattr(self.backend, "summary_updated"):
            self.state_machine.on_auth_success("赵增辉", "admin")

    def _request_open_cabinet(self):
        """申请开柜"""
        if hasattr(self.backend, "request_open_cabinet"):
            self.backend.request_open_cabinet()
            return
        from state_machine import SystemState

        current_state = self.state_machine.current_state
        if current_state in [SystemState.USER_AUTHED, SystemState.ADMIN_AUTHED]:
            self.state_machine.on_cabinet_opened()
            self.backend.simulate_door_opened()
        else:
            print("[AuthPage] 当前状态不允许开柜")

    def _logout(self):
        """退出登录"""
        if hasattr(self.backend, "request_logout"):
            self.backend.request_logout()
        else:
            self.state_machine.on_logout()

        # 重置显示
        self.nfc_status_label.setText("等待刷卡")
        self.nfc_status_label.setStyleSheet("font-size: 14px; color: #5C635D;")
        self.card_uid_label.setText("卡 UID: --")
        self.face_status_label.setText("未识别")
        self.confidence_label.setText("置信度: --")
        self.user_name_label.setText("用户: --")
        self.role_label.setText("权限: --")
