#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include <libopencm3/cm3/nvic.h>
#include <libopencm3/cm3/systick.h>
#include <libopencm3/stm32/rcc.h>
#include <libopencm3/stm32/gpio.h>
#include <libopencm3/stm32/exti.h>
#include <libopencm3/stm32/timer.h>
#include <libopencm3/usb/usbd.h>
#include <libopencm3/usb/cdc.h>

#define RING_SIZE      8192U
#define USB_CHUNK_SIZE 64U
#define FRAME0         0xA5U
#define FRAME1         0x5AU
#define TYPE_EDGE      0xE1U
#define TYPE_STATUS    0x5AU
#define TYPE_DECODED   0xD5U
#define STATUS_INTERVAL_US 200000U
#define SOURCE_UNIT_US 1021U
#define SOURCE_GAP_US 10000U

// Charger inputs: S -> PA0. PA1/PA2 are held down when not connected.
// Main-controller low-speed one-wire output: PB0.
#define ELF_DATA_PORT GPIOB
#define ELF_DATA_PIN  GPIO0
#define ELF_CLK_PORT  GPIOB
#define ELF_CLK_PIN   GPIO1
#define ELF_LATCH_PORT GPIOB
#define ELF_LATCH_PIN  GPIO10
#define ELF_REPEAT_INTERVAL_MS 500U
#define ENABLE_ELF_RELAY 0

#define PB0_ONEWIRE_PORT GPIOB
#define PB0_ONEWIRE_PIN  GPIO0
#define PB0_FRAME_IDLE_MS 700U

#define PRESENCE_SLOT1_MASK 0x0070U
#define PRESENCE_SLOT2_MASK 0x0380U
#define PRESENCE_SLOT3_MASK 0x1C00U
#define PRESENCE_SLOT4_MASK 0x6000U

typedef struct __attribute__((packed)) {
    uint8_t ch;
    uint8_t level;
    uint8_t flags;
    uint32_t dt_us;
    uint32_t tick_us;
    uint16_t seq;
    uint16_t edge_count_low;
} EdgeRecord;

typedef struct __attribute__((packed)) {
    uint8_t levels;
    uint8_t flags;
    uint8_t reserved;
    uint32_t tick_us;
    uint32_t edge_count[3];
    uint32_t dropped_bytes;
} StatusRecord;

typedef struct __attribute__((packed)) {
    uint16_t word;
    uint32_t decoded_frame_count;
    uint32_t tick_us;
    uint32_t edge_count_s;
    uint8_t raw_presence_mask;
    uint8_t stable_presence_mask;
    uint8_t levels;
    uint8_t flags;
} DecodedRecord;

static usbd_device *usbdev;
static uint8_t usb_control_buffer[128];

static volatile uint8_t tx_ring[RING_SIZE];
static volatile uint16_t tx_head;
static volatile uint16_t tx_tail;
static volatile uint32_t last_tick[3];
static volatile uint32_t system_millis;
static volatile uint32_t edge_count[3];
static volatile uint32_t dropped_bytes;
static volatile uint16_t seq;
static volatile uint8_t overflow_latched;
static volatile uint16_t decoded_status_word;
static volatile uint32_t decoded_frame_count;
static volatile uint8_t decoded_presence_mask;
static volatile uint8_t stable_presence_mask;
static bool usb_configured;
static volatile bool capture_enabled = true;
static uint8_t source_units[48];
static uint8_t source_unit_count;

typedef struct {
    uint16_t duration_ms;
    uint8_t level;
} Pb0Phase;

static Pb0Phase pb0_phases[16];
static uint8_t pb0_phase_count;
static uint8_t pb0_phase_index;
static uint32_t pb0_next_ms;

void SysTick_Handler(void)
{
    system_millis++;
}

static const struct usb_device_descriptor dev = {
    .bLength = USB_DT_DEVICE_SIZE,
    .bDescriptorType = USB_DT_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = USB_CLASS_CDC,
    .bDeviceSubClass = 0,
    .bDeviceProtocol = 0,
    .bMaxPacketSize0 = 64,
    .idVendor = 0x0483,
    .idProduct = 0x5740,
    .bcdDevice = 0x0200,
    .iManufacturer = 1,
    .iProduct = 2,
    .iSerialNumber = 3,
    .bNumConfigurations = 1,
};

static const struct usb_endpoint_descriptor comm_endp[] = {{
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = 0x83,
    .bmAttributes = USB_ENDPOINT_ATTR_INTERRUPT,
    .wMaxPacketSize = 16,
    .bInterval = 255,
}};

static const struct usb_endpoint_descriptor data_endp[] = {{
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = 0x01,
    .bmAttributes = USB_ENDPOINT_ATTR_BULK,
    .wMaxPacketSize = 64,
    .bInterval = 1,
}, {
    .bLength = USB_DT_ENDPOINT_SIZE,
    .bDescriptorType = USB_DT_ENDPOINT,
    .bEndpointAddress = 0x82,
    .bmAttributes = USB_ENDPOINT_ATTR_BULK,
    .wMaxPacketSize = 64,
    .bInterval = 1,
}};

static const struct {
    struct usb_cdc_header_descriptor header;
    struct usb_cdc_call_management_descriptor call_mgmt;
    struct usb_cdc_acm_descriptor acm;
    struct usb_cdc_union_descriptor cdc_union;
} __attribute__((packed)) cdcacm_functional_descriptors = {
    .header = {
        .bFunctionLength = sizeof(struct usb_cdc_header_descriptor),
        .bDescriptorType = CS_INTERFACE,
        .bDescriptorSubtype = USB_CDC_TYPE_HEADER,
        .bcdCDC = 0x0110,
    },
    .call_mgmt = {
        .bFunctionLength = sizeof(struct usb_cdc_call_management_descriptor),
        .bDescriptorType = CS_INTERFACE,
        .bDescriptorSubtype = USB_CDC_TYPE_CALL_MANAGEMENT,
        .bmCapabilities = 0,
        .bDataInterface = 1,
    },
    .acm = {
        .bFunctionLength = sizeof(struct usb_cdc_acm_descriptor),
        .bDescriptorType = CS_INTERFACE,
        .bDescriptorSubtype = USB_CDC_TYPE_ACM,
        .bmCapabilities = 0,
    },
    .cdc_union = {
        .bFunctionLength = sizeof(struct usb_cdc_union_descriptor),
        .bDescriptorType = CS_INTERFACE,
        .bDescriptorSubtype = USB_CDC_TYPE_UNION,
        .bControlInterface = 0,
        .bSubordinateInterface0 = 1,
    },
};

static const struct usb_interface_descriptor comm_iface[] = {{
    .bLength = USB_DT_INTERFACE_SIZE,
    .bDescriptorType = USB_DT_INTERFACE,
    .bInterfaceNumber = 0,
    .bAlternateSetting = 0,
    .bNumEndpoints = 1,
    .bInterfaceClass = USB_CLASS_CDC,
    .bInterfaceSubClass = USB_CDC_SUBCLASS_ACM,
    .bInterfaceProtocol = USB_CDC_PROTOCOL_AT,
    .iInterface = 0,
    .endpoint = comm_endp,
    .extra = &cdcacm_functional_descriptors,
    .extralen = sizeof(cdcacm_functional_descriptors),
}};

static const struct usb_interface_descriptor data_iface[] = {{
    .bLength = USB_DT_INTERFACE_SIZE,
    .bDescriptorType = USB_DT_INTERFACE,
    .bInterfaceNumber = 1,
    .bAlternateSetting = 0,
    .bNumEndpoints = 2,
    .bInterfaceClass = USB_CLASS_DATA,
    .bInterfaceSubClass = 0,
    .bInterfaceProtocol = 0,
    .iInterface = 0,
    .endpoint = data_endp,
}};

static const struct usb_interface ifaces[] = {{
    .num_altsetting = 1,
    .altsetting = comm_iface,
}, {
    .num_altsetting = 1,
    .altsetting = data_iface,
}};

static const struct usb_config_descriptor config = {
    .bLength = USB_DT_CONFIGURATION_SIZE,
    .bDescriptorType = USB_DT_CONFIGURATION,
    .wTotalLength = 0,
    .bNumInterfaces = 2,
    .bConfigurationValue = 1,
    .iConfiguration = 0,
    .bmAttributes = 0x80,
    .bMaxPower = 0x32,
    .interface = ifaces,
};

static const char *usb_strings[] = {
    "Codex",
    "Three Wire Sniffer CDC",
    "S-V-G-001",
};

static uint16_t ring_used(void)
{
    return (uint16_t)((tx_head - tx_tail) & (RING_SIZE - 1U));
}

static uint16_t ring_free(void)
{
    return (uint16_t)(RING_SIZE - 1U - ring_used());
}

static bool ring_push_byte(uint8_t b)
{
    uint16_t next = (uint16_t)((tx_head + 1U) & (RING_SIZE - 1U));
    if (next == tx_tail) {
        dropped_bytes++;
        overflow_latched = 1;
        return false;
    }
    tx_ring[tx_head] = b;
    tx_head = next;
    return true;
}

static void ring_push_frame(uint8_t type, const void *payload, uint8_t len)
{
    const uint8_t *p = (const uint8_t *)payload;
    uint8_t crc = type ^ len;
    ring_push_byte(FRAME0);
    ring_push_byte(FRAME1);
    ring_push_byte(type);
    ring_push_byte(len);
    for (uint8_t i = 0; i < len; i++) {
        crc ^= p[i];
        ring_push_byte(p[i]);
    }
    ring_push_byte(crc);
}

static uint8_t quantize_source_unit(uint32_t dt_us)
{
    uint32_t unit = (dt_us + (SOURCE_UNIT_US / 2U)) / SOURCE_UNIT_US;
    if (unit > 255U) {
        unit = 255U;
    }
    return (uint8_t)unit;
}

static uint8_t presence_mask_from_word(uint16_t word)
{
    uint16_t raw = (uint16_t)(word & 0x7FFFU);
    uint8_t mask = 0U;

    // The charger appears to encode each slot as a small multi-bit field.
    // Empty is field == 0. Any non-zero field is treated as battery present.
    // Known presence bits from experiments are bit4/7/10/13; adjacent bits
    // are deliberately included to allow full/two-bar/one-bar states.
    if (raw & PRESENCE_SLOT1_MASK) {
        mask |= 0x01U;
    }
    if (raw & PRESENCE_SLOT2_MASK) {
        mask |= 0x02U;
    }
    if (raw & PRESENCE_SLOT3_MASK) {
        mask |= 0x04U;
    }
    if (raw & PRESENCE_SLOT4_MASK) {
        mask |= 0x08U;
    }

    return mask;
}

static void update_stable_presence(uint8_t mask)
{
    static uint8_t score[4];

    for (uint8_t i = 0; i < 4U; i++) {
        uint8_t bit = (uint8_t)(1U << i);
        if (mask & bit) {
            if (score[i] < 10U) {
                score[i] += 2U;
                if (score[i] > 10U) {
                    score[i] = 10U;
                }
            }
        } else if (score[i] > 0U) {
            score[i]--;
        }

        if (score[i] >= 4U) {
            stable_presence_mask |= bit;
        } else if (score[i] == 0U) {
            stable_presence_mask &= (uint8_t)~bit;
        }
    }
}

static void decode_source_frame(void)
{
    if (source_unit_count < 35U) {
        return;
    }

    // Observed source frame:
    // [idle gap], 4T, 3T, 3T, then 32 duration units.
    if (source_units[1] < 3U || source_units[1] > 5U ||
        source_units[2] < 2U || source_units[2] > 4U ||
        source_units[3] < 2U || source_units[3] > 4U) {
        return;
    }

    uint16_t word = 0;
    for (uint8_t bit = 0; bit < 15U; bit++) {
        uint8_t a = source_units[5U + bit * 2U];
        uint8_t b = source_units[6U + bit * 2U];

        // Candidate encoding verified by experiments:
        // pair 1T,2T means bit=1; pair 2T,1T means bit=0.
        if (a == 1U && b == 2U) {
            word |= (uint16_t)(1U << bit);
        } else if (a == 2U && b == 1U) {
            // bit remains zero
        } else {
            return;
        }
    }

    decoded_status_word = (uint16_t)(0x8000U | word); // bit15 marks decoded frame valid.
    decoded_presence_mask = presence_mask_from_word(decoded_status_word);
    update_stable_presence(decoded_presence_mask);
    decoded_frame_count++;
}

static void usb_try_send(void)
{
    uint8_t chunk[USB_CHUNK_SIZE];
    uint16_t n = 0;

    if (!usb_configured || tx_tail == tx_head) {
        return;
    }

    while (tx_tail != tx_head && n < USB_CHUNK_SIZE) {
        chunk[n++] = tx_ring[tx_tail];
        tx_tail = (uint16_t)((tx_tail + 1U) & (RING_SIZE - 1U));
    }

    int sent = usbd_ep_write_packet(usbdev, 0x82, chunk, n);
    if (sent <= 0) {
        tx_tail = (uint16_t)((tx_tail - n) & (RING_SIZE - 1U));
    } else if ((uint16_t)sent < n) {
        tx_tail = (uint16_t)((tx_tail - (n - (uint16_t)sent)) & (RING_SIZE - 1U));
    }
}

static void short_delay(void)
{
    // Millisecond-scale pulses so a Linux userspace GPIO reader on ELF can keep up.
    for (volatile uint32_t i = 0; i < 72000U; i++) {
        __asm volatile ("nop");
    }
}

static void pb0_set(uint8_t level)
{
    if (level) {
        gpio_set(PB0_ONEWIRE_PORT, PB0_ONEWIRE_PIN);
    } else {
        gpio_clear(PB0_ONEWIRE_PORT, PB0_ONEWIRE_PIN);
    }
}

static void pb0_build_frame(uint8_t presence_mask)
{
    uint8_t n = 0;

    // PB0 one-wire protocol, active-low pulse width coding:
    // idle high
    // start: low 300 ms, high 100 ms
    // slot1..slot4:
    //   empty   -> low 100 ms, high 100 ms
    //   present -> low 300 ms, high 100 ms
    // stop/idle: low 100 ms, then high for PB0_FRAME_IDLE_MS
    pb0_phases[n++] = (Pb0Phase){300U, 0U};
    pb0_phases[n++] = (Pb0Phase){100U, 1U};

    for (uint8_t i = 0; i < 4U; i++) {
        bool present = (presence_mask & (uint8_t)(1U << i)) != 0U;
        pb0_phases[n++] = (Pb0Phase){present ? 300U : 100U, 0U};
        pb0_phases[n++] = (Pb0Phase){100U, 1U};
    }

    pb0_phases[n++] = (Pb0Phase){100U, 0U};
    pb0_phases[n++] = (Pb0Phase){PB0_FRAME_IDLE_MS, 1U};

    pb0_phase_count = n;
    pb0_phase_index = 0U;
}

static void pb0_onewire_update(uint32_t now_ms)
{
    if (pb0_phase_count == 0U) {
        pb0_build_frame(stable_presence_mask);
        pb0_set(pb0_phases[0].level);
        pb0_next_ms = now_ms + pb0_phases[0].duration_ms;
        return;
    }

    if ((int32_t)(now_ms - pb0_next_ms) < 0) {
        return;
    }

    pb0_phase_index++;
    if (pb0_phase_index >= pb0_phase_count) {
        pb0_build_frame(stable_presence_mask);
    }

    pb0_set(pb0_phases[pb0_phase_index].level);
    pb0_next_ms = now_ms + pb0_phases[pb0_phase_index].duration_ms;
}

static void elf_publish_status(void)
{
    uint16_t word = decoded_status_word;

    gpio_clear(ELF_LATCH_PORT, ELF_LATCH_PIN);
    gpio_clear(ELF_CLK_PORT, ELF_CLK_PIN);
    short_delay();

    // Transmit status bit index 0 first, then 1..15.
    for (uint8_t i = 0; i < 16U; i++) {
        if (word & (uint16_t)(1U << i)) {
            gpio_set(ELF_DATA_PORT, ELF_DATA_PIN);
        } else {
            gpio_clear(ELF_DATA_PORT, ELF_DATA_PIN);
        }
        short_delay();
        gpio_set(ELF_CLK_PORT, ELF_CLK_PIN);
        short_delay();
        gpio_clear(ELF_CLK_PORT, ELF_CLK_PIN);
        short_delay();
    }

    gpio_set(ELF_LATCH_PORT, ELF_LATCH_PIN);
}

static uint8_t pin_level(uint8_t ch)
{
    return (uint8_t)((gpio_get(GPIOA, (uint16_t)(GPIO0 << ch)) != 0) ? 1 : 0);
}

static void capture_edge(uint8_t ch)
{
    if (ring_free() < 128U) {
        exti_disable_request(EXTI0);
        capture_enabled = false;
        dropped_bytes++;
        overflow_latched = 1U;
        return;
    }

    uint32_t now = timer_get_counter(TIM2) & 0xFFFFU;
    uint32_t dt = (now - last_tick[ch]) & 0xFFFFU;
    last_tick[ch] = now;
    edge_count[ch]++;

    if (ch == 0U) {
        if (dt > SOURCE_GAP_US) {
            decode_source_frame();
            source_unit_count = 0;
        }
        if (source_unit_count < sizeof(source_units)) {
            source_units[source_unit_count++] = quantize_source_unit(dt);
        }
    }

    EdgeRecord r;
    r.ch = ch;
    r.level = pin_level(ch);
    r.flags = overflow_latched;
    r.dt_us = dt;
    r.tick_us = (system_millis * 1000U) + (now % 1000U);
    r.seq = seq++;
    r.edge_count_low = (uint16_t)edge_count[ch];
    overflow_latched = 0;

    ring_push_frame(TYPE_EDGE, &r, sizeof(r));
}

void EXTI0_IRQHandler(void)
{
    if (exti_get_flag_status(EXTI0)) {
        exti_reset_request(EXTI0);
        capture_edge(0);
    }
}

void EXTI1_IRQHandler(void)
{
    if (exti_get_flag_status(EXTI1)) {
        exti_reset_request(EXTI1);
        capture_edge(1);
    }
}

void EXTI2_IRQHandler(void)
{
    if (exti_get_flag_status(EXTI2)) {
        exti_reset_request(EXTI2);
        capture_edge(2);
    }
}

static enum usbd_request_return_codes cdcacm_control_request(
    usbd_device *dev_handle,
    struct usb_setup_data *req,
    uint8_t **buf,
    uint16_t *len,
    usbd_control_complete_callback *complete)
{
    (void)dev_handle;
    (void)complete;

    switch (req->bRequest) {
    case USB_CDC_REQ_SET_CONTROL_LINE_STATE:
        return USBD_REQ_HANDLED;
    case USB_CDC_REQ_SET_LINE_CODING:
        if (*len < sizeof(struct usb_cdc_line_coding)) {
            return USBD_REQ_NOTSUPP;
        }
        return USBD_REQ_HANDLED;
    case USB_CDC_REQ_GET_LINE_CODING: {
        static struct usb_cdc_line_coding coding = {
            .dwDTERate = 115200,
            .bCharFormat = USB_CDC_1_STOP_BITS,
            .bParityType = USB_CDC_NO_PARITY,
            .bDataBits = 8,
        };
        *buf = (uint8_t *)&coding;
        *len = sizeof(coding);
        return USBD_REQ_HANDLED;
    }
    default:
        return USBD_REQ_NOTSUPP;
    }
}

static void cdcacm_data_rx_cb(usbd_device *dev_handle, uint8_t ep)
{
    (void)ep;
    char buf[64];
    while (usbd_ep_read_packet(dev_handle, 0x01, buf, sizeof(buf)) > 0) {
    }
}

static void cdcacm_set_config(usbd_device *dev_handle, uint16_t wValue)
{
    (void)wValue;
    usbd_ep_setup(dev_handle, 0x01, USB_ENDPOINT_ATTR_BULK, 64, cdcacm_data_rx_cb);
    usbd_ep_setup(dev_handle, 0x82, USB_ENDPOINT_ATTR_BULK, 64, NULL);
    usbd_ep_setup(dev_handle, 0x83, USB_ENDPOINT_ATTR_INTERRUPT, 16, NULL);
    usbd_register_control_callback(
        dev_handle,
        USB_REQ_TYPE_CLASS | USB_REQ_TYPE_INTERFACE,
        USB_REQ_TYPE_TYPE | USB_REQ_TYPE_RECIPIENT,
        cdcacm_control_request);
    usb_configured = true;
}

static void clock_setup(void)
{
    rcc_clock_setup_in_hse_8mhz_out_72mhz();
    rcc_set_usbpre(RCC_CFGR_USBPRE_PLL_CLK_DIV1_5);
}

static void gpio_setup(void)
{
    rcc_periph_clock_enable(RCC_AFIO);
    rcc_periph_clock_enable(RCC_GPIOA);
    rcc_periph_clock_enable(RCC_GPIOB);

    gpio_set_mode(GPIOA, GPIO_MODE_INPUT, GPIO_CNF_INPUT_FLOAT, GPIO0);
    gpio_set_mode(GPIOA, GPIO_MODE_INPUT, GPIO_CNF_INPUT_PULL_UPDOWN, GPIO1 | GPIO2);
    gpio_clear(GPIOA, GPIO1 | GPIO2);
    gpio_set_mode(GPIOB, GPIO_MODE_OUTPUT_2_MHZ, GPIO_CNF_OUTPUT_PUSHPULL,
                  ELF_DATA_PIN | ELF_CLK_PIN | ELF_LATCH_PIN);
    gpio_set(PB0_ONEWIRE_PORT, PB0_ONEWIRE_PIN);
    gpio_clear(ELF_CLK_PORT, ELF_CLK_PIN);
    gpio_set(ELF_LATCH_PORT, ELF_LATCH_PIN);

    // Force USB re-enumeration on boards where D+ has a fixed pull-up.
    gpio_set_mode(GPIOA, GPIO_MODE_OUTPUT_2_MHZ, GPIO_CNF_OUTPUT_PUSHPULL, GPIO12);
    gpio_clear(GPIOA, GPIO12);
    for (volatile uint32_t i = 0; i < 900000; i++) {
        __asm volatile ("nop");
    }
    gpio_set_mode(GPIOA, GPIO_MODE_INPUT, GPIO_CNF_INPUT_FLOAT, GPIO12);
}

static void timer_setup(void)
{
    rcc_periph_clock_enable(RCC_TIM2);
    timer_set_prescaler(TIM2, 71); // TIM2 clock is 72 MHz, counter is 1 MHz.
    timer_set_period(TIM2, 0xFFFFFFFF);
    timer_enable_counter(TIM2);

    systick_set_clocksource(STK_CSR_CLKSOURCE_AHB);
    systick_set_reload(72000U - 1U);
    systick_interrupt_enable();
    systick_counter_enable();
}

static void exti_setup(void)
{
    exti_select_source(EXTI0, GPIOA);
    exti_set_trigger(EXTI0, EXTI_TRIGGER_BOTH);
    exti_enable_request(EXTI0);
    exti_reset_request(EXTI0);

    nvic_enable_irq(NVIC_EXTI0_IRQ);
}

static void usb_setup(void)
{
    rcc_periph_clock_enable(RCC_USB);
    usbdev = usbd_init(&st_usbfs_v1_usb_driver, &dev, &config, usb_strings, 3,
                       usb_control_buffer, sizeof(usb_control_buffer));
    usbd_register_set_config_callback(usbdev, cdcacm_set_config);
}

static void send_status(void)
{
    StatusRecord s;
    if (ring_free() < 64U) {
        tx_tail = tx_head;
        dropped_bytes++;
        overflow_latched = 1U;
    }
    s.levels = (uint8_t)((gpio_get(GPIOA, GPIO0) ? 1 : 0) |
                         (gpio_get(GPIOA, GPIO1) ? 2 : 0) |
                         (gpio_get(GPIOA, GPIO2) ? 4 : 0));
    s.flags = overflow_latched;
    s.reserved = 0;
    s.tick_us = system_millis * 1000U;
    s.edge_count[0] = edge_count[0];
    s.edge_count[1] = edge_count[1];
    s.edge_count[2] = edge_count[2];
    s.dropped_bytes = dropped_bytes;
    ring_push_frame(TYPE_STATUS, &s, sizeof(s));
}

static void send_decoded_status(void)
{
    DecodedRecord d;
    if (ring_free() < 64U) {
        tx_tail = tx_head;
        dropped_bytes++;
        overflow_latched = 1U;
    }
    d.word = decoded_status_word;
    d.decoded_frame_count = decoded_frame_count;
    d.tick_us = system_millis * 1000U;
    d.edge_count_s = edge_count[0];
    d.raw_presence_mask = decoded_presence_mask;
    d.stable_presence_mask = stable_presence_mask;
    d.levels = (uint8_t)((gpio_get(GPIOA, GPIO0) ? 1 : 0) |
                         (gpio_get(GPIOA, GPIO1) ? 2 : 0) |
                         (gpio_get(GPIOA, GPIO2) ? 4 : 0));
    d.flags = overflow_latched;
    ring_push_frame(TYPE_DECODED, &d, sizeof(d));
}

int main(void)
{
    clock_setup();
    gpio_setup();
    timer_setup();
    exti_setup();
    usb_setup();

    last_tick[0] = timer_get_counter(TIM2) & 0xFFFFU;
    last_tick[1] = last_tick[0];
    last_tick[2] = last_tick[0];

    uint32_t next_status_ms = system_millis + 10U;
    uint32_t next_elf_ms = system_millis + 20U;
    while (1) {
        usbd_poll(usbdev);
        usb_try_send();

        uint32_t now_ms = system_millis;
        if ((int32_t)(now_ms - next_status_ms) >= 0) {
            send_status();
            send_decoded_status();
            next_status_ms += STATUS_INTERVAL_US / 1000U;
        }
        if (ring_free() < 128U) {
            overflow_latched = 1U;
        }
        if (!capture_enabled && ring_free() > (RING_SIZE / 2U)) {
            exti_reset_request(EXTI0);
            exti_enable_request(EXTI0);
            capture_enabled = true;
        }
        pb0_onewire_update(now_ms);
        if (ENABLE_ELF_RELAY && usb_configured && (int32_t)(now_ms - next_elf_ms) >= 0) {
            elf_publish_status();
            next_elf_ms += ELF_REPEAT_INTERVAL_MS;
        }
    }
}
