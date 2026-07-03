PROJECT := three_wire_usb_cdc

LIBOPENCM3 := ../third_party/libopencm3
PREFIX := arm-none-eabi-
CC := $(PREFIX)gcc
OBJCOPY := $(PREFIX)objcopy
SIZE := $(PREFIX)size

CPU := -mcpu=cortex-m3 -mthumb
CFLAGS := $(CPU) -Os -g3 -Wall -Wextra -ffunction-sections -fdata-sections
CFLAGS += -DSTM32F1 -I$(LIBOPENCM3)/include
LDFLAGS := $(CPU) -Wl,--gc-sections -Wl,-Map=build/$(PROJECT).map
LDFLAGS += -Tstm32f103c8t6.ld -L$(LIBOPENCM3)/lib -lopencm3_stm32f1

SRC := src/startup_stm32f103xb.s src/main.c
OBJ := $(addprefix build/,$(SRC:.c=.o))
OBJ := $(OBJ:.s=.o)

.PHONY: all clean flash

all: build/$(PROJECT).elf build/$(PROJECT).bin
	$(SIZE) build/$(PROJECT).elf

build/$(PROJECT).elf: $(OBJ) stm32f103c8t6.ld | build
	$(CC) $(OBJ) $(LDFLAGS) -o $@

build/$(PROJECT).bin: build/$(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

build/%.o: %.c | build
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

build/%.o: %.s | build
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

build:
	@mkdir -p build

flash: build/$(PROJECT).bin
	STM32_Programmer_CLI -c port=SWD -w build/$(PROJECT).bin 0x08000000 -v -rst

clean:
	rm -rf build
