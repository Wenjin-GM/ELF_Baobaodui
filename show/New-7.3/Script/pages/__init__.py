#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pages package

包含所有页面模块
"""

from .dashboard_page import DashboardPage
from .auth_page import AuthPage
from .tools_page import ToolsPage
from .charging_page import ChargingPage
from .environment_page import EnvironmentPage
from .records_page import RecordsPage
from .settings_page import SettingsPage
from .debug_page import DebugPage

__all__ = [
    'DashboardPage',
    'AuthPage',
    'ToolsPage',
    'ChargingPage',
    'EnvironmentPage',
    'RecordsPage',
    'SettingsPage',
    'DebugPage',
]
