#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主窗口模块

实现 QStackedWidget 多页面切换、底部导航栏、顶部状态栏
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QStackedWidget, QFrame)
from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtGui import QFont
from datetime import datetime

from state_machine import StateMachine, PageType, SystemState
from mock_backend import MockBackend
from pages.dashboard_page import DashboardPage
from pages.auth_page import AuthPage
from pages.tools_page import ToolsPage
from pages.charging_page import ChargingPage
from pages.environment_page import EnvironmentPage
from pages.records_page import RecordsPage
from pages.settings_page import SettingsPage
from pages.debug_page import DebugPage


class MainWindow(QMainWindow):
    """主窗口：全屏触摸屏界面"""

    def __init__(self, backend=None):
        super().__init__()

        # 状态机和后端
        self.state_machine = StateMachine()
        self.backend = backend if backend is not None else MockBackend()

        # 滑动手势相关
        self.drag_start_pos = None
        self.is_dragging = False

        # 初始化UI
        self._init_ui()
        self._init_connections()

        # 启动后端
        self.backend.start()

        # 定时更新时间显示
        self.time_timer = QTimer()
        self.time_timer.timeout.connect(self._update_time_display)
        self.time_timer.start(1000)

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle("智能安全工具柜")

        # 全屏显示
        # self.showFullScreen()  # 可以根据需要启用全屏
        self.resize(1024, 600)  # 默认10寸屏分辨率

        # 中心容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== 顶部状态栏 ==========
        self.top_bar = self._create_top_bar()
        main_layout.addWidget(self.top_bar)

        # ========== 页面堆栈 ==========
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("background-color: #F7F4EF;")
        main_layout.addWidget(self.stacked_widget, 1)

        # 创建各个页面
        self.pages = {}
        self._create_pages()

        # ========== 底部导航栏 ==========
        self.bottom_nav = self._create_bottom_nav()
        main_layout.addWidget(self.bottom_nav)

        # 初始化导航栏
        self._update_navigation()

    def _create_top_bar(self) -> QWidget:
        """创建顶部状态栏"""
        top_bar = QFrame()
        top_bar.setFixedHeight(56)
        top_bar.setStyleSheet("""
            QFrame {
                background-color: #1F2421;
                border: none;
            }
        """)

        layout = QHBoxLayout(top_bar)
        layout.setContentsMargins(20, 0, 20, 0)

        # 系统名称
        title_label = QLabel("智能安全工具柜")
        title_label.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        layout.addWidget(title_label)

        layout.addStretch()

        # 系统状态
        self.state_label = QLabel("未认证待机")
        self.state_label.setStyleSheet("""
            QLabel {
                color: #FFFFFF;
                font-size: 14px;
                background-color: #5C635D;
                padding: 6px 12px;
                border-radius: 12px;
            }
        """)
        layout.addWidget(self.state_label)

        # 当前用户
        self.user_label = QLabel("")
        self.user_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(self.user_label)

        # 时间显示
        self.time_label = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.time_label.setStyleSheet("color: #FFFFFF; font-size: 14px;")
        layout.addWidget(self.time_label)

        return top_bar

    def _create_bottom_nav(self) -> QWidget:
        """创建底部导航栏"""
        nav_bar = QFrame()
        nav_bar.setFixedHeight(68)
        nav_bar.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: none;
            }
        """)

        self.nav_layout = QHBoxLayout(nav_bar)
        self.nav_layout.setContentsMargins(10, 8, 10, 8)
        self.nav_layout.setSpacing(8)

        self.nav_buttons = {}

        return nav_bar

    def _create_pages(self):
        """创建所有页面"""
        # 总览页
        dashboard = DashboardPage(self.state_machine, self.backend)
        self.pages[PageType.DASHBOARD] = dashboard
        self.stacked_widget.addWidget(dashboard)

        # 认证页
        auth = AuthPage(self.state_machine, self.backend)
        self.pages[PageType.AUTH] = auth
        self.stacked_widget.addWidget(auth)

        # 工具页
        tools = ToolsPage(self.state_machine, self.backend)
        self.pages[PageType.TOOLS] = tools
        self.stacked_widget.addWidget(tools)

        # 充电页
        charging = ChargingPage(self.state_machine, self.backend)
        self.pages[PageType.CHARGING] = charging
        self.stacked_widget.addWidget(charging)

        # 环境页
        environment = EnvironmentPage(self.state_machine, self.backend)
        self.pages[PageType.ENVIRONMENT] = environment
        self.stacked_widget.addWidget(environment)

        # 记录页
        records = RecordsPage(self.state_machine, self.backend)
        self.pages[PageType.RECORDS] = records
        self.stacked_widget.addWidget(records)

        # 设置页
        settings = SettingsPage(self.state_machine, self.backend)
        self.pages[PageType.SETTINGS] = settings
        self.stacked_widget.addWidget(settings)

        # 调试页
        debug = DebugPage(self.state_machine, self.backend)
        self.pages[PageType.DEBUG] = debug
        self.stacked_widget.addWidget(debug)

    def _init_connections(self):
        """初始化信号连接"""
        # 状态机信号
        self.state_machine.state_changed.connect(self._on_state_changed)
        self.state_machine.page_should_change.connect(self._switch_to_page)
        if hasattr(self.backend, "summary_updated"):
            self.backend.summary_updated.connect(self._on_ros_summary_updated)

    def _update_navigation(self):
        """根据当前状态更新底部导航栏"""
        # 清空现有按钮
        for btn in self.nav_buttons.values():
            btn.deleteLater()
        self.nav_buttons.clear()

        # 获取当前状态允许的页面
        allowed_pages = self.state_machine.get_allowed_pages()

        # 创建导航按钮
        for page_type in allowed_pages:
            btn = QPushButton(page_type.value)
            btn.setFixedHeight(52)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #FBF9F5;
                    border: none;
                    border-radius: 8px;
                    font-size: 16px;
                    color: #1F2421;
                    padding: 0 16px;
                }
                QPushButton:hover {
                    background-color: #F2E3D6;
                }
                QPushButton:pressed {
                    background-color: #C4612F;
                    color: #FFFFFF;
                }
            """)
            btn.clicked.connect(lambda checked, pt=page_type: self._switch_to_page(pt))

            self.nav_layout.addWidget(btn)
            self.nav_buttons[page_type] = btn

        # 高亮当前页面
        self._highlight_current_page()

    def _highlight_current_page(self):
        """高亮当前页面的导航按钮"""
        current_widget = self.stacked_widget.currentWidget()
        current_page_type = None

        for page_type, widget in self.pages.items():
            if widget == current_widget:
                current_page_type = page_type
                break

        if current_page_type and current_page_type in self.nav_buttons:
            for page_type, btn in self.nav_buttons.items():
                if page_type == current_page_type:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #C4612F;
                            border: none;
                            border-radius: 8px;
                            font-size: 16px;
                            color: #FFFFFF;
                            padding: 0 16px;
                            font-weight: bold;
                        }
                    """)
                else:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #FBF9F5;
                            border: none;
                            border-radius: 8px;
                            font-size: 16px;
                            color: #1F2421;
                            padding: 0 16px;
                        }
                        QPushButton:hover {
                            background-color: #F2E3D6;
                        }
                        QPushButton:pressed {
                            background-color: #C4612F;
                            color: #FFFFFF;
                        }
                    """)

    def _switch_to_page(self, page_type: PageType):
        """切换到指定页面"""
        if not self.state_machine.is_page_allowed(page_type):
            print(f"[MainWindow] 当前状态不允许访问页面: {page_type.value}")
            return

        if page_type in self.pages:
            widget = self.pages[page_type]
            self.stacked_widget.setCurrentWidget(widget)
            self._highlight_current_page()
            print(f"[MainWindow] 切换到页面: {page_type.value}")

    def _on_state_changed(self, old_state: SystemState, new_state: SystemState):
        """状态变化处理"""
        print(f"[MainWindow] 状态变化: {old_state.value} -> {new_state.value}")

        # 更新顶部状态栏
        self.state_label.setText(self.state_machine.get_state_display_text())

        user = self.state_machine.current_user
        if user:
            role_text = "管理员" if user["role"] == "admin" else "用户"
            self.user_label.setText(f"{role_text}: {user['name']}")
        else:
            self.user_label.setText("")

        # 更新导航栏
        self._update_navigation()

    def _on_ros_summary_updated(self, summary: dict):
        """Follow cabinet_logic_node state and user as the single source of truth."""
        state_name = summary.get("state")
        try:
            new_state = SystemState(state_name)
        except Exception:
            return

        current_user = summary.get("current_user") or {}
        auth = summary.get("auth") or {}
        if current_user:
            self.state_machine._current_user = {
                "name": current_user.get("name") or current_user.get("user_name") or "",
                "role": current_user.get("role") or "user",
            }
        elif auth.get("success"):
            self.state_machine._current_user = {
                "name": auth.get("user_name") or auth.get("name") or "",
                "role": auth.get("role") or "user",
            }
        else:
            self.state_machine._current_user = None

        if self.state_machine.current_state != new_state:
            self.state_machine.transition_to(new_state)
        else:
            self._on_state_changed(new_state, new_state)
        self._update_navigation()

    def _update_time_display(self):
        """更新时间显示"""
        self.time_label.setText(datetime.now().strftime("%H:%M:%S"))

    # ========== 触摸滑动支持 ==========

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.is_dragging = False

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.drag_start_pos is not None:
            delta = event.pos() - self.drag_start_pos
            if abs(delta.x()) > 10:  # 触发滑动的最小距离
                self.is_dragging = True

    def mouseReleaseEvent(self, event):
        """鼠标释放事件"""
        if self.drag_start_pos is not None and self.is_dragging:
            delta = event.pos() - self.drag_start_pos

            # 水平滑动切换页面
            if abs(delta.x()) > 100:  # 滑动距离阈值
                if delta.x() > 0:
                    self._swipe_to_previous_page()
                else:
                    self._swipe_to_next_page()

        self.drag_start_pos = None
        self.is_dragging = False

    def _swipe_to_previous_page(self):
        """滑动到上一页"""
        allowed_pages = self.state_machine.get_allowed_pages()
        current_widget = self.stacked_widget.currentWidget()

        current_index = -1
        for i, page_type in enumerate(allowed_pages):
            if self.pages[page_type] == current_widget:
                current_index = i
                break

        if current_index > 0:
            prev_page = allowed_pages[current_index - 1]
            self._switch_to_page(prev_page)

    def _swipe_to_next_page(self):
        """滑动到下一页"""
        allowed_pages = self.state_machine.get_allowed_pages()
        current_widget = self.stacked_widget.currentWidget()

        current_index = -1
        for i, page_type in enumerate(allowed_pages):
            if self.pages[page_type] == current_widget:
                current_index = i
                break

        if 0 <= current_index < len(allowed_pages) - 1:
            next_page = allowed_pages[current_index + 1]
            self._switch_to_page(next_page)

    def closeEvent(self, event):
        """关闭事件"""
        self.backend.stop()
        event.accept()
