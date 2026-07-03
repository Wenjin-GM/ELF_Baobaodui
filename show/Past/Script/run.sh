#!/bin/bash
# 智能安全工具柜界面启动脚本

echo "========================================"
echo "  智能安全工具柜触摸屏界面"
echo "  宝宝队 ELF 2 / RK3588"
echo "========================================"
echo ""

# 检查 Python3
if ! command -v python3 &> /dev/null
then
    echo "错误: 未找到 python3，请先安装"
    exit 1
fi

# 检查 PyQt5
python3 -c "import PyQt5" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "错误: 未找到 PyQt5"
    echo "请运行: sudo apt install python3-pyqt5"
    echo "或者: pip3 install PyQt5"
    exit 1
fi

echo "环境检查通过"
echo "启动界面程序..."
echo ""

# 进入脚本目录
cd "$(dirname "$0")"

# 启动程序
python3 main.py

echo ""
echo "程序已退出"
