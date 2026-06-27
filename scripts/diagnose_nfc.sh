#!/bin/bash
# NFC问题诊断脚本

echo "========================================"
echo "NFC问题诊断 - V1.1"
echo "========================================"
echo ""

cd ~/smart_tool_cabinet

echo "1. 检查主程序是否运行..."
if pgrep -f "python3 main.py" > /dev/null; then
    echo "   ✓ 主程序正在运行"
    ps aux | grep "python3 main.py" | grep -v grep
else
    echo "   ✗ 主程序未运行 - 这就是问题！"
    echo "   → 需要启动: sudo python3 main.py"
fi
echo ""

echo "2. 检查I2C7设备..."
if sudo i2cdetect -y 7 2>/dev/null | grep -q "24"; then
    echo "   ✓ PN532 (0x24) 已连接"
    sudo i2cdetect -y 7 | grep -A1 "20:"
else
    echo "   ✗ I2C7未检测到PN532，继续检查I2C5..."
    if sudo i2cdetect -y 5 2>/dev/null | grep -q "24"; then
        echo "   ✓ PN532 (0x24) 出现在I2C5，请同步修改 I2C_BUS_NFC"
        sudo i2cdetect -y 5 | grep -A1 "20:"
    else
        echo "   ✗ I2C5/I2C7均未检测到PN532"
    fi
fi
echo ""

echo "3. 检查最近的日志..."
echo "   启动日志:"
tail -200 tool_cabinet.log | grep -E "启动|初始化" | tail -5
echo ""
echo "   NFC线程日志:"
tail -200 tool_cabinet.log | grep -E "NFC|线程" | tail -5
echo ""
echo "   最后10行日志:"
tail -10 tool_cabinet.log
echo ""

echo "4. 测试NFC硬件..."
echo "   运行基础测试脚本..."
cd ~/smart_tool_cabinet
if [ -f "PN532/tests/test_nfc_basic.py" ]; then
    echo "   → sudo python3 PN532/tests/test_nfc_basic.py"
    timeout 5 sudo python3 PN532/tests/test_nfc_basic.py 2>&1 | head -20
else
    echo "   ✗ 测试脚本不存在"
fi
echo ""

echo "========================================"
echo "诊断完成！"
echo ""
echo "问题排查："
echo "1. 如果主程序未运行 → 启动它"
echo "2. 如果PN532未检测到 → 检查I2C连接和拨码开关"
echo "3. 如果硬件测试失败 → 检查硬件连接"
echo ""
echo "启动命令："
echo "  cd ~/smart_tool_cabinet"
echo "  sudo python3 main.py"
echo "========================================"
