#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统状态机模块

定义工具柜系统的所有状态、状态转换逻辑和每个状态下的页面显示规则
"""

from enum import Enum
from PyQt5.QtCore import QObject, pyqtSignal


class SystemState(Enum):
    """系统状态枚举"""
    STANDBY = "STANDBY"                      # 未认证待机
    AUTH_PENDING = "AUTH_PENDING"            # 正在认证
    USER_AUTHED = "USER_AUTHED"              # 普通用户已认证
    ADMIN_AUTHED = "ADMIN_AUTHED"            # 管理员已认证
    CABINET_OPEN = "CABINET_OPEN"            # 已开锁或柜门打开
    CHECKING_AFTER_CLOSE = "CHECKING_AFTER_CLOSE"  # 关门后盘点中
    ALARM_ACTIVE = "ALARM_ACTIVE"            # 报警状态
    MAINTENANCE = "MAINTENANCE"              # 调试维护模式
    OFFLINE = "OFFLINE"                      # 后端或关键硬件离线


class PageType(Enum):
    """页面类型枚举"""
    DASHBOARD = "总览"
    AUTH = "认证"
    TOOLS = "工具"
    CHARGING = "充电"
    ENVIRONMENT = "环境"
    RECORDS = "记录"
    SETTINGS = "设置"
    DEBUG = "调试"


# 状态机配置：每个状态的默认页面和允许显示的页面
STATE_CONFIG = {
    SystemState.STANDBY: {
        "default_page": PageType.DASHBOARD,
        "allowed_pages": [PageType.DASHBOARD, PageType.AUTH]
    },
    SystemState.AUTH_PENDING: {
        "default_page": PageType.AUTH,
        "allowed_pages": [PageType.DASHBOARD, PageType.AUTH]
    },
    SystemState.USER_AUTHED: {
        "default_page": PageType.DASHBOARD,
        "allowed_pages": [PageType.DASHBOARD, PageType.TOOLS, PageType.CHARGING,
                         PageType.ENVIRONMENT, PageType.RECORDS, PageType.AUTH]
    },
    SystemState.ADMIN_AUTHED: {
        "default_page": PageType.DASHBOARD,
        "allowed_pages": [PageType.DASHBOARD, PageType.AUTH, PageType.TOOLS,
                         PageType.CHARGING, PageType.ENVIRONMENT, PageType.RECORDS,
                         PageType.SETTINGS]
    },
    SystemState.CABINET_OPEN: {
        "default_page": PageType.TOOLS,
        "allowed_pages": [PageType.DASHBOARD, PageType.AUTH, PageType.TOOLS,
                         PageType.CHARGING, PageType.ENVIRONMENT, PageType.RECORDS,
                         PageType.SETTINGS]
    },
    SystemState.CHECKING_AFTER_CLOSE: {
        "default_page": PageType.TOOLS,
        "allowed_pages": [PageType.DASHBOARD, PageType.TOOLS]
    },
    SystemState.ALARM_ACTIVE: {
        "default_page": PageType.DASHBOARD,
        "allowed_pages": [PageType.DASHBOARD, PageType.TOOLS, PageType.CHARGING,
                         PageType.ENVIRONMENT, PageType.RECORDS, PageType.AUTH]
    },
    SystemState.MAINTENANCE: {
        "default_page": PageType.DEBUG,
        "allowed_pages": [PageType.DEBUG, PageType.SETTINGS, PageType.DASHBOARD]
    },
    SystemState.OFFLINE: {
        "default_page": PageType.DASHBOARD,
        "allowed_pages": [PageType.DASHBOARD, PageType.AUTH, PageType.RECORDS]
    }
}


class StateMachine(QObject):
    """系统状态机"""

    # 信号：状态变化时触发
    state_changed = pyqtSignal(SystemState, SystemState)  # (old_state, new_state)
    page_should_change = pyqtSignal(PageType)  # 应该切换到的默认页面

    def __init__(self):
        super().__init__()
        self._current_state = SystemState.STANDBY
        self._current_user = None  # {"name": "赵增辉", "role": "admin" | "user"}

    @property
    def current_state(self) -> SystemState:
        """获取当前状态"""
        return self._current_state

    @property
    def current_user(self) -> dict:
        """获取当前用户"""
        return self._current_user

    def get_allowed_pages(self) -> list:
        """获取当前状态下允许显示的页面列表"""
        if self._current_state == SystemState.CABINET_OPEN and self._current_user:
            pages = [PageType.DASHBOARD, PageType.AUTH, PageType.TOOLS,
                     PageType.CHARGING, PageType.ENVIRONMENT, PageType.RECORDS]
            if self._current_user.get("role") == "admin":
                pages.append(PageType.SETTINGS)
            return pages
        return STATE_CONFIG[self._current_state]["allowed_pages"]

    def get_default_page(self) -> PageType:
        """获取当前状态的默认页面"""
        return STATE_CONFIG[self._current_state]["default_page"]

    def is_page_allowed(self, page: PageType) -> bool:
        """判断某个页面在当前状态下是否允许显示"""
        return page in self.get_allowed_pages()

    def transition_to(self, new_state: SystemState, auto_switch_page: bool = True):
        """
        状态转换

        Args:
            new_state: 目标状态
            auto_switch_page: 是否自动切换到默认页面
        """
        if new_state == self._current_state:
            return

        old_state = self._current_state
        self._current_state = new_state

        print(f"[状态机] {old_state.value} -> {new_state.value}")

        # 发射状态变化信号
        self.state_changed.emit(old_state, new_state)

        # 如果需要，自动切换到默认页面
        if auto_switch_page:
            default_page = self.get_default_page()
            self.page_should_change.emit(default_page)

    # ========== 业务状态转换方法 ==========

    def on_auth_start(self):
        """开始认证"""
        if self._current_state == SystemState.STANDBY:
            self.transition_to(SystemState.AUTH_PENDING)

    def on_auth_success(self, user_name: str, role: str):
        """
        认证成功

        Args:
            user_name: 用户姓名
            role: "admin" 或 "user"
        """
        self._current_user = {"name": user_name, "role": role}

        if role == "admin":
            self.transition_to(SystemState.ADMIN_AUTHED)
        else:
            self.transition_to(SystemState.USER_AUTHED)

    def on_auth_failed(self):
        """认证失败"""
        self._current_user = None
        if self._current_state == SystemState.AUTH_PENDING:
            self.transition_to(SystemState.STANDBY, auto_switch_page=False)

    def on_cabinet_opened(self):
        """柜门打开"""
        if self._current_state in [SystemState.USER_AUTHED, SystemState.ADMIN_AUTHED]:
            self.transition_to(SystemState.CABINET_OPEN)

    def on_cabinet_closed(self):
        """柜门关闭，进入盘点状态"""
        if self._current_state == SystemState.CABINET_OPEN:
            self.transition_to(SystemState.CHECKING_AFTER_CLOSE)

    def on_checking_complete(self, is_normal: bool):
        """
        盘点完成

        Args:
            is_normal: 盘点结果是否正常
        """
        if self._current_state == SystemState.CHECKING_AFTER_CLOSE:
            if is_normal:
                self._current_user = None
                self.transition_to(SystemState.STANDBY)
            else:
                self.transition_to(SystemState.ALARM_ACTIVE)

    def on_alarm_raised(self):
        """触发报警"""
        if self._current_state != SystemState.ALARM_ACTIVE:
            self.transition_to(SystemState.ALARM_ACTIVE, auto_switch_page=False)

    def on_alarm_cleared(self):
        """清除报警（需管理员权限）"""
        if self._current_state == SystemState.ALARM_ACTIVE:
            if self._current_user and self._current_user["role"] == "admin":
                self.transition_to(SystemState.ADMIN_AUTHED)
            else:
                self._current_user = None
                self.transition_to(SystemState.STANDBY)

    def on_logout(self):
        """退出登录"""
        self._current_user = None
        self.transition_to(SystemState.STANDBY)

    def on_enter_maintenance(self):
        """进入维护模式（需管理员权限）"""
        if self._current_state == SystemState.ADMIN_AUTHED:
            self.transition_to(SystemState.MAINTENANCE)

    def on_exit_maintenance(self):
        """退出维护模式"""
        if self._current_state == SystemState.MAINTENANCE:
            self.transition_to(SystemState.ADMIN_AUTHED)

    def on_hardware_offline(self):
        """关键硬件离线"""
        self.transition_to(SystemState.OFFLINE)

    def on_hardware_online(self):
        """关键硬件恢复"""
        if self._current_state == SystemState.OFFLINE:
            self._current_user = None
            self.transition_to(SystemState.STANDBY)

    def get_state_display_text(self) -> str:
        """获取当前状态的中文显示文本"""
        state_text_map = {
            SystemState.STANDBY: "未认证待机",
            SystemState.AUTH_PENDING: "正在认证",
            SystemState.USER_AUTHED: "普通用户已认证",
            SystemState.ADMIN_AUTHED: "管理员已认证",
            SystemState.CABINET_OPEN: "柜门打开",
            SystemState.CHECKING_AFTER_CLOSE: "盘点中",
            SystemState.ALARM_ACTIVE: "报警状态",
            SystemState.MAINTENANCE: "维护模式",
            SystemState.OFFLINE: "离线"
        }
        return state_text_map.get(self._current_state, "未知状态")
