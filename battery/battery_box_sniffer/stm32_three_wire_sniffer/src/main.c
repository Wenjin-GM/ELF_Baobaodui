#include <stdint.h>
#include <stdbool.h>

#define PERIPH_BASE      0x40000000UL
#define APB1PERIPH_BASE  PERIPH_BASE
#define APB2PERIPH_BASE  0x40010000UL
#define AHBPERIPH_BASE   0x40018000UL

#define RCC_BASE         0x40021000UL
#define FLASH_BASE       0x40022000UL
#define GPIOA_BASE       0x40010800UL
#define AFIO_BASE        0x40010000UL
#define EXTI_BASE        0x40010400UL
#define USART1_BASE      0x40013800UL
#define DMA1_BASE        0x40020000UL
#define TIM2_BASE        0x40000000UL
#define NVIC_ISER0       (*(volatile uint32_t *)0xE000E100UL)
#define NVIC_ISER1       (*(volatile uint32_t *)0xE000E104UL)

#define REG32(addr)      (*(volatile uint32_t *)(addr))

#define RCC_CR           REG32(RCC_BASE + 0x00)
#define RCC_CFGR         REG32(RCC_BASE + 0x04)
#define RCC_APB2ENR      REG32(RCC_BASE + 0x18)
#define RCC_APB1ENR      REG32(RCC_BASE + 0x1C)
#define RCC_AHBENR       REG32(RCC_BASE + 0x14)
#define FLASH_ACR        REG32(FLASH_BASE + 0x00)

#define GPIOA_CRL        REG32(GPIOA_BASE + 0x00)
#define GPIOA_CRH        REG32(GPIOA_BASE + 0x04)
#define GPIOA_IDR        REG32(GPIOA_BASE + 0x08)
#define GPIOA_ODR        REG32(GPIOA_BASE + 0x0C)

#define AFIO_EXTICR1     REG32(AFIO_BASE + 0x08)
#define AFIO_MAPR        REG32(AFIO_BASE + 0x04)

#define EXTI_IMR         REG32(EXTI_BASE + 0x00)
#define EXTI_RTSR        REG32(EXTI_BASE + 0x08)
#define EXTI_FTSR        REG32(EXTI_BASE + 0x0C)
#define EXTI_PR          REG32(EXTI_BASE + 0x14)

#define TIM2_CR1         REG32(TIM2_BASE + 0x00)
#define TIM2_PSC         REG32(TIM2_BASE + 0x28)
#define TIM2_ARR         REG32(TIM2_BASE + 0x2C)
#define TIM2_CNT         REG32(TIM2_BASE + 0x24)

#define USART1_SR        REG32(USART1_BASE + 0x00)
#define USART1_DR        REG32(USART1_BASE + 0x04)
#define USART1_BRR       REG32(USART1_BASE + 0x08)
#define USART1_CR1       REG32(USART1_BASE + 0x0C)
#define USART1_CR3       REG32(USART1_BASE + 0x14)

#define DMA1_ISR         REG32(DMA1_BASE + 0x00)
#define DMA1_IFCR        REG32(DMA1_BASE + 0x04)
#define DMA1_CH4_CCR     REG32(DMA1_BASE + 0x44)
#define DMA1_CH4_CNDTR   REG32(DMA1_BASE + 0x48)
#define DMA1_CH4_CPAR    REG32(DMA1_BASE + 0x4C)
#define DMA1_CH4_CMAR    REG32(DMA1_BASE + 0x50)

#define RING_SIZE        8192U
#define TX_CHUNK_SIZE    256U
#define BAUDRATE         115200U
#define SYSCLK_HZ        64000000U
#define TIMER_HZ         1000000U

#define MAGIC_EDGE       0xE1U
#define MAGIC_STATUS     0x5AU

typedef struct __attribute__((packed)) {
    uint8_t magic;
    uint8_t ch;
    uint8_t level;
    uint8_t flags;
    uint32_t dt_us;
    uint32_t tick_us;
    uint16_t seq;
    uint16_t edge_count_low;
} EdgeRecord;

typedef struct __attribute__((packed)) {
    uint8_t magic;
    uint8_t levels;
    uint8_t flags;
    uint8_t reserved;
    uint32_t tick_us;
    uint32_t edge_count[3];
    uint32_t dropped_bytes;
} StatusRecord;

static volatile uint8_t tx_ring[RING_SIZE];
static volatile uint16_t tx_head = 0;
static volatile uint16_t tx_tail = 0;
static volatile bool dma_busy = false;
static uint8_t dma_chunk[TX_CHUNK_SIZE];

static volatile uint32_t last_tick[3] = {0, 0, 0};
static volatile uint32_t edge_count[3] = {0, 0, 0};
static volatile uint32_t dropped_bytes = 0;
static volatile uint16_t seq = 0;
static volatile uint8_t overflow_latched = 0;

static void delay_cycles(volatile uint32_t n)
{
    while (n--) {
        __asm volatile ("nop");
    }
}

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
        overflow_latched = 1U;
        return false;
    }
    tx_ring[tx_head] = b;
    tx_head = next;
    return true;
}

static void ring_push_bytes(const void *data, uint16_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    for (uint16_t i = 0; i < len; i++) {
        if (!ring_push_byte(p[i])) {
            break;
        }
    }
}

static void clock_init(void)
{
    RCC_CR |= (1U << 0);                 // HSI on
    while (!(RCC_CR & (1U << 1))) {}

    FLASH_ACR = (1U << 4) | 0x02U;       // Prefetch enable, 2 wait states.

    RCC_CFGR = 0;
    RCC_CFGR |= (0x04U << 8);            // APB1 = HCLK/2, within 36 MHz limit.
    RCC_CFGR |= (0x0EU << 18);           // PLLMUL x16: HSI/2 * 16 = 64 MHz
    RCC_CR |= (1U << 24);                // PLL on
    while (!(RCC_CR & (1U << 25))) {}

    RCC_CFGR |= (0x02U << 0);            // SW = PLL
    while (((RCC_CFGR >> 2) & 0x03U) != 0x02U) {}
}

static void gpio_init(void)
{
    RCC_APB2ENR |= (1U << 0) | (1U << 2) | (1U << 14); // AFIO, GPIOA, USART1
    RCC_APB1ENR |= (1U << 0);                          // TIM2
    RCC_AHBENR |= (1U << 0);                           // DMA1

    // PA0/PA1/PA2 input floating: CNF=01 MODE=00.
    GPIOA_CRL &= ~((0xFU << 0) | (0xFU << 4) | (0xFU << 8));
    GPIOA_CRL |=  ((0x4U << 0) | (0x4U << 4) | (0x4U << 8));

    // PA9 USART1_TX alternate function push-pull 50 MHz. PA10 floating input.
    GPIOA_CRH &= ~((0xFU << 4) | (0xFU << 8));
    GPIOA_CRH |=  ((0xBU << 4) | (0x4U << 8));

    // Keep JTAG/SWD default; no remap. EXTI0/1/2 source = GPIOA.
    AFIO_EXTICR1 &= ~0x0FFFU;
    (void)AFIO_MAPR;
}

static void tim2_init(void)
{
    TIM2_PSC = (SYSCLK_HZ / TIMER_HZ) - 1U;
    TIM2_ARR = 0xFFFFFFFFU;
    TIM2_CNT = 0;
    TIM2_CR1 = 1U;
}

static void usart1_dma_init(void)
{
    USART1_CR1 = 0;
    USART1_CR3 = 0;

    // APB2 USART clock is 64 MHz. BRR encodes mantissa:fraction of USARTDIV.
    USART1_BRR = (uint32_t)(((SYSCLK_HZ * 25U) / (4U * BAUDRATE) / 100U) << 4) |
                 (uint32_t)(((((SYSCLK_HZ * 25U) / (4U * BAUDRATE)) -
                              (100U * ((SYSCLK_HZ * 25U) / (4U * BAUDRATE) / 100U))) * 16U + 50U) / 100U);
    USART1_CR3 |= (1U << 7);             // DMAT
    USART1_CR1 |= (1U << 13) | (1U << 3); // UE, TE

    DMA1_CH4_CCR = 0;
    DMA1_CH4_CPAR = USART1_BASE + 0x04;
    DMA1_IFCR = (0x0FU << 12);           // Clear CH4 flags.
    NVIC_ISER0 = (1U << 14);             // DMA1 Channel4 IRQ.
}

static void exti_init(void)
{
    EXTI_IMR  |= 0x07U;
    EXTI_RTSR |= 0x07U;
    EXTI_FTSR |= 0x07U;
    EXTI_PR    = 0x07U;

    NVIC_ISER0 = (1U << 6) | (1U << 7) | (1U << 8); // EXTI0, EXTI1, EXTI2.
}

static uint8_t pin_level(uint8_t ch)
{
    return (uint8_t)((GPIOA_IDR >> ch) & 0x01U);
}

static void capture_edge(uint8_t ch)
{
    uint32_t now = TIM2_CNT;
    uint32_t dt = now - last_tick[ch];
    last_tick[ch] = now;
    edge_count[ch]++;

    EdgeRecord r;
    r.magic = MAGIC_EDGE;
    r.ch = ch;
    r.level = pin_level(ch);
    r.flags = overflow_latched;
    r.dt_us = dt;
    r.tick_us = now;
    r.seq = seq++;
    r.edge_count_low = (uint16_t)edge_count[ch];
    overflow_latched = 0;

    ring_push_bytes(&r, sizeof(r));
}

void EXTI0_IRQHandler(void)
{
    if (EXTI_PR & (1U << 0)) {
        EXTI_PR = (1U << 0);
        capture_edge(0);
    }
}

void EXTI1_IRQHandler(void)
{
    if (EXTI_PR & (1U << 1)) {
        EXTI_PR = (1U << 1);
        capture_edge(1);
    }
}

void EXTI2_IRQHandler(void)
{
    if (EXTI_PR & (1U << 2)) {
        EXTI_PR = (1U << 2);
        capture_edge(2);
    }
}

void DMA1_Channel4_IRQHandler(void)
{
    if (DMA1_ISR & (1U << 13)) {         // TCIF4
        DMA1_CH4_CCR &= ~1U;
        DMA1_IFCR = (0x0FU << 12);
        dma_busy = false;
    }
}

static void dma_try_start(void)
{
    if (dma_busy || tx_tail == tx_head) {
        return;
    }

    uint16_t n = 0;
    while (tx_tail != tx_head && n < TX_CHUNK_SIZE) {
        dma_chunk[n++] = tx_ring[tx_tail];
        tx_tail = (uint16_t)((tx_tail + 1U) & (RING_SIZE - 1U));
    }

    DMA1_CH4_CCR &= ~1U;
    DMA1_IFCR = (0x0FU << 12);
    DMA1_CH4_CMAR = (uint32_t)dma_chunk;
    DMA1_CH4_CNDTR = n;
    DMA1_CH4_CCR =
        (1U << 7) |     // MINC
        (1U << 4) |     // DIR: memory to peripheral
        (1U << 1);      // TCIE
    dma_busy = true;
    DMA1_CH4_CCR |= 1U;
}

static void send_status(void)
{
    StatusRecord s;
    s.magic = MAGIC_STATUS;
    s.levels = (uint8_t)(GPIOA_IDR & 0x07U);
    s.flags = overflow_latched;
    s.reserved = 0;
    s.tick_us = TIM2_CNT;
    s.edge_count[0] = edge_count[0];
    s.edge_count[1] = edge_count[1];
    s.edge_count[2] = edge_count[2];
    s.dropped_bytes = dropped_bytes;
    ring_push_bytes(&s, sizeof(s));
}

int main(void)
{
    clock_init();
    gpio_init();
    tim2_init();
    usart1_dma_init();

    last_tick[0] = TIM2_CNT;
    last_tick[1] = last_tick[0];
    last_tick[2] = last_tick[0];

    exti_init();

    uint32_t next_status = TIM2_CNT + TIMER_HZ;
    while (1) {
        uint32_t now = TIM2_CNT;
        if ((int32_t)(now - next_status) >= 0) {
            send_status();
            next_status += TIMER_HZ;
        }
        dma_try_start();
        if (ring_free() < 128U) {
            overflow_latched = 1U;
        }
        delay_cycles(32);
    }
}
