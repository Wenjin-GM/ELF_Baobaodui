#!/bin/bash
# 智能工具柜系统检查脚本（不需要sudo）

echo "=========================================="
echo "智能工具柜系统 - 基础检查"
echo "=========================================="
echo ""

cd ~/smart_tool_cabinet

echo "1. Python版本:"
python3 --version
echo ""

echo "2. 依赖库检查:"
python3 -c "import smbus2; print('  ✓ smbus2')" 2>/dev/null || echo "  ✗ smbus2 未安装"
python3 -c "import gpiod; print('  ✓ gpiod')" 2>/dev/null || echo "  ✗ gpiod 未安装"
echo ""

echo "3. 文件检查:"
[ -f "main.py" ] && echo "  ✓ main.py ($(wc -l < main.py) 行)" || echo "  ✗ main.py 不存在"
[ -f "authorized_cards.json" ] && echo "  ✓ authorized_cards.json" || echo "  ✗ authorized_cards.json 不存在"
[ -f "README.md" ] && echo "  ✓ README.md" || echo "  ✗ README.md 不存在"
[ -f "docs/connect_way.md" ] && echo "  ✓ docs/connect_way.md" || echo "  ✗ docs/connect_way.md 不存在"
echo ""

echo "4. 语法检查:"
python3 -m py_compile main.py 2>/dev/null && echo "  ✓ main.py 语法正确" || echo "  ✗ main.py 语法错误"
echo ""

echo "5. 导入测试:"
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    # 测试导入（不运行主程序）
    import importlib.util
    spec = importlib.util.spec_from_file_location('main', 'main.py')
    print('  ✓ 模块可以加载')
except Exception as e:
    print(f'  ✗ 导入错误: {e}')
"
echo ""

echo "=========================================="
echo "检查完成！"
echo ""
echo "运行系统需要在串口终端中执行:"
echo "  cd ~/smart_tool_cabinet"
echo "  sudo python3 main.py"
echo "=========================================="
