import gpiod
import time

# 最新接线：GPIO.23 = GPIO2_C5--GPIO3_A4 = gpiochip3, line 4
chip = gpiod.Chip("gpiochip3")
line = chip.get_line(4)

# 申请为输出
line.request(consumer="buzzer", type=gpiod.LINE_REQ_DIR_OUT)

try:
    print("蜂鸣器响 5 秒...")
    line.set_value(1)   # 高电平触发
    time.sleep(5)

    print("蜂鸣器停 1 秒...")
    line.set_value(0)   # 低电平停止
    time.sleep(1)

    print("蜂鸣器再响 3 秒...")
    line.set_value(1)
    time.sleep(3)
    line.set_value(0)

    print("测试完成")
except KeyboardInterrupt:
    pass
finally:
    line.release()
