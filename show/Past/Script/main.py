#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能安全工具柜 PyQt5 触摸屏界面主程序

项目：宝宝队 ELF 2 / RK3588 智能安全工具柜
目标：10寸HDMI触摸屏全屏界面，状态机驱动页面切换
"""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from main_window import MainWindow


def main():
    """主函数：启动 PyQt5 应用"""
    # 启用高DPI支持
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("智能安全工具柜")

    # 创建主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
