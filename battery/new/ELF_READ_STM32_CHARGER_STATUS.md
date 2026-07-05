# ELF 读取 STM32 转发的充电装置状态

更新时间：2026-07-03

注意：本文档记录的是旧版 `PB0/PB1/PB10` 三线 GPIO 状态字转发协议。当前已烧录的 STM32 固件改为 `PB0` 单线低速脉宽协议，只输出四个槽位的“空/有电池”稳定在位掩码。

当前主控板读取应优先使用：

```text
battery_box_sniffer/PB0_ONEWIRE_PRESENCE_PROTOCOL.md
```

旧三线协议内容保留在本文下方，仅作历史参考。

旧用途：下次在 ELF2 开发板上编写读取程序时，直接把本文档发给 Codex 作为接口说明。请让 Codex 按本文档实现 ELF 侧 GPIO 输入读取、状态字解析和稳定性滤波。

本文档用于下一阶段在 ELF2 开发板上编写 GPIO 读取程序。

## 1. 系统结构

STM32F103C8T6 负责监听充电装置显示板三线接口，并在本地解码后，通过 3 根 GPIO 把状态字发送给 ELF。

```text
充电装置 S/V/G  ->  STM32 PA0/PA1/PA2
STM32 解码      ->  STM32 PB0/PB1/PB10
STM32 PBx       ->  ELF GPIO
```

STM32 已烧录 USB CDC + GPIO 转发版固件：

```text
F:\Most_important\Zzzz\battery_box_sniffer\stm32_three_wire_usb_cdc\build\three_wire_usb_cdc.bin
```

## 2. STM32 引脚分配

### 2.1 充电装置到 STM32

```text
充电装置 S  -> STM32 PA0
充电装置 V  -> STM32 PA1
充电装置 G  -> STM32 PA2
充电装置 GND -> STM32 GND
```

注意：

```text
V 约为 5V，不要直接硬接 STM32 GPIO。
S/V/G 进入 PA0/PA1/PA2 前建议经过限流/分压/保护。
STM32 GND、充电装置 GND、ELF GND 必须共地。
```

### 2.2 STM32 到 ELF

```text
STM32 PB0  -> ELF_DATA
STM32 PB1  -> ELF_CLK
STM32 PB10 -> ELF_LATCH
STM32 GND  -> ELF GND
```

STM32 输出为 3.3V CMOS 电平。确认 ELF GPIO 也是 3.3V 容忍。

## 3. STM32 到 ELF 的三线协议

STM32 每约 500ms 输出一次 16-bit 状态字。

三根线含义：

```text
ELF_DATA  : 数据位
ELF_CLK   : 时钟
ELF_LATCH : 帧边界/有效信号
```

空闲状态：

```text
ELF_LATCH = 1
ELF_CLK   = 0
```

发送一帧时：

```text
1. STM32 拉低 ELF_LATCH
2. STM32 依次发送 bit0 到 bit15
3. 每一位：
   - STM32 先设置 ELF_DATA
   - STM32 拉高 ELF_CLK
   - ELF 在 ELF_CLK 上升沿读取 ELF_DATA
   - STM32 拉低 ELF_CLK
4. 16 位发送完成后，STM32 拉高 ELF_LATCH
5. ELF 在 ELF_LATCH 上升沿认为一帧完成
```

时序是毫秒级慢速脉冲，适合 ELF Linux 用户态 GPIO 边沿读取。

## 4. 状态字格式

STM32 输出 16 bit：

```text
bit15 = 1 表示状态字有效
bit0~bit14 = 充电装置原始状态字段
```

当前已确认的槽位存在位：

```text
bit4  = slot1_present
bit7  = slot2_present
bit10 = slot3_present
bit13 = slot4_present
```

当前候选状态位：

```text
bit12 = slot3_full_candidate
```

`bit12` 是根据“槽 3 已充满、槽 1 正在充电”实验得到的候选位。后续最好再用更多状态确认。

## 5. 已知实验样例

```text
四槽全空：
raw bits = 000000000000000
word     = 0x8000

只放槽1：
raw bits = 000010000000000
word     = 0x8010

只放槽2：
raw bits = 000000010000000
word     = 0x8080

只放槽3：
raw bits = 000000000010000
word     = 0x8400

只放槽4：
raw bits = 000000000000010
word     = 0xA000

槽1有电池、槽3有电池：
raw bits = 000010000010000
word     = 0x8410

槽1正在充电、槽3已充满：
raw bits = 000010000010100
word     = 0x9410
```

## 6. ELF 端读取算法

建议 ELF 使用 GPIO 边沿事件：

```text
ELF_CLK   : rising edge
ELF_LATCH : both edge 或 rising edge
ELF_DATA  : 普通输入
```

推荐逻辑：

```c
volatile uint16_t current_word = 0;
volatile int bit_index = 0;
volatile bool frame_active = false;
volatile bool frame_ready = false;
volatile uint16_t last_word = 0;

on_latch_falling() {
    current_word = 0;
    bit_index = 0;
    frame_active = true;
}

on_clk_rising() {
    if (!frame_active) return;
    int bit = gpio_read(ELF_DATA);
    if (bit_index < 16) {
        if (bit) {
            current_word |= (1u << bit_index);
        }
        bit_index++;
    }
}

on_latch_rising() {
    if (frame_active && bit_index == 16) {
        last_word = current_word;
        frame_ready = true;
    }
    frame_active = false;
}
```

解码函数：

```c
struct charger_state {
    bool valid;
    bool slot_present[4];
    bool slot3_full_candidate;
};

struct charger_state decode(uint16_t word) {
    struct charger_state s = {0};

    s.valid = (word & (1u << 15)) != 0;
    s.slot_present[0] = (word & (1u << 4))  != 0;
    s.slot_present[1] = (word & (1u << 7))  != 0;
    s.slot_present[2] = (word & (1u << 10)) != 0;
    s.slot_present[3] = (word & (1u << 13)) != 0;
    s.slot3_full_candidate = (word & (1u << 12)) != 0;

    return s;
}
```

## 7. 输出建议

ELF 程序可先打印：

```text
word=0x9410 valid=1 slot1=1 slot2=0 slot3=1 slot4=0 slot3_full_candidate=1
```

再转换为业务状态：

```text
slot1: present, charging/incomplete
slot2: empty
slot3: present, full candidate
slot4: empty
```

注意：目前只有 `present` 位已可靠确认，`full/charging/percentage` 仍需继续做控制变量实验。

## 8. 编写 ELF 代码时的注意事项

1. ELF 与 STM32 必须共地。
2. ELF GPIO 必须配置为输入，不能反向驱动 PB0/PB1/PB10。
3. 优先使用 `libgpiod` 的 edge event，而不是长时间 sleep 轮询。
4. 如果用轮询，轮询周期必须远小于 CLK 脉冲宽度。
5. 收到 `bit15=0` 的 word 时应认为无效或 STM32 尚未解码到源帧。
6. 建议连续读 3 帧一致后再更新业务状态，避免接线抖动或启动瞬间误读。
