#!/bin/bash
# 智能工具柜系统测试脚本

echo "=========================================="
echo "智能工具柜系统 - 功能测试"
echo "=========================================="
echo ""

# 检查权限
if [ "$EUID" -ne 0 ]; then
    echo "错误：需要root权限"
    echo "请使用: sudo bash scripts/test_main.sh"
    exit 1
fi

cd ~/smart_tool_cabinet

echo "1. 检查Python版本..."
python3 --version
echo ""

echo "2. 检查依赖库..."
python3 -c "import smbus2; print('✓ smbus2')" 2>/dev/null || echo "✗ smbus2 未安装"
python3 -c "import gpiod; print('✓ gpiod')" 2>/dev/null || echo "✗ gpiod 未安装"
echo ""

echo "3. 检查I2C设备..."
echo "   I2C4 (SHT30):"
i2cdetect -y 4 2>/dev/null | grep "44" && echo "   ✓ SHT30 (0x44) 已连接" || echo "   ✗ SHT30 未检测到"
echo "   I2C7 (PN532):"
i2cdetect -y 7 2>/dev/null | grep "24" && echo "   ✓ PN532 (0x24) 已连接" || echo "   ✗ PN532 未检测到"
echo "   I2C5 (PN532备用检查):"
i2cdetect -y 5 2>/dev/null | grep "24" && echo "   ✓ PN532 (0x24) 出现在I2C5" || echo "   ○ I2C5未检测到PN532"
echo ""

echo "4. 检查GPIO设备..."
gpioinfo | grep "gpiochip3" > /dev/null && echo "   ✓ gpiochip3 可用" || echo "   ✗ gpiochip3 不可用"
echo ""

echo "5. 检查配置文件..."
[ -f "authorized_cards.json" ] && echo "   ✓ authorized_cards.json" || echo "   ✗ authorized_cards.json 不存在"
[ -f "main.py" ] && echo "   ✓ main.py" || echo "   ✗ main.py 不存在"
echo ""

echo "6. 测试主程序语法..."
python3 -m py_compile main.py 2>/dev/null && echo "   ✓ 语法检查通过" || echo "   ✗ 语法错误"
echo ""

echo "=========================================="
echo "测试完成！"
echo ""
echo "启动系统命令："
echo "  sudo python3 main.py"
echo ""
echo "查看日志："
echo "  tail -f tool_cabinet.log"
echo "=========================================="
