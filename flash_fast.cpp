#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>

static volatile uint32_t *gpio = nullptr;
static int targetPin = -1;

static const off_t GPIO_OFFSET = 0x200000; // from peripheral base
static const size_t GPIO_LEN = 0xB4;       // enough for registers we use

static void setExitHandler();
static void cleanupAndExit(int code);
static void sigHandler(int sig);
static bool mapGpio();
static void unmapGpio();
static void setPinOutput(int pin);
static void setPinHigh(int pin);
static void setPinLow(int pin);

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s <bcm_pin>\n", argv[0]);
        return 1;
    }

    targetPin = atoi(argv[1]);
    if (targetPin < 0 || targetPin > 53) {
        fprintf(stderr, "Invalid BCM pin: %d\n", targetPin);
        return 1;
    }

    if (!mapGpio()) {
        fprintf(stderr, "Failed to map gpio\n");
        return 1;
    }

    setExitHandler();
    setPinOutput(targetPin);

    volatile uint32_t *regSet =
        gpio + (0x1C / sizeof(uint32_t)); // GPSET0 offset
    volatile uint32_t *regClr =
        gpio + (0x28 / sizeof(uint32_t)); // GPCLR0 offset

    uint32_t mask = (1u << (targetPin & 31));

    // Tight toggle loop: set then clear as fast as possible.
    // Keep pointer volatile to ensure writes aren't optimized away.
    while (true) {
        *regSet = mask;
        *regClr = mask;
    }

    // unreachable, but keep interface clean
    cleanupAndExit(0);
    return 0;
}

static void setExitHandler() {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sigHandler;
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
}

static void sigHandler(int sig) {
    (void)sig;
    // turn LED off before exit
    setPinLow(targetPin);
    unmapGpio();
    _exit(0);
}

static void cleanupAndExit(int code) {
    if (gpio) {
        setPinLow(targetPin);
        unmapGpio();
    }
    exit(code);
}

static bool mapGpio() {
    // Allow override for Pi4: PERI_BASE env var e.g. 0xFE000000
    const char *env = getenv("PERI_BASE");
    unsigned long periBase = 0x3F000000UL; // default for many Pi models
    if (env) {
        periBase = strtoul(env, NULL, 0);
    }

    off_t gpioBase = (off_t)(periBase + GPIO_OFFSET);

    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open(/dev/mem)");
        return false;
    }

    void *m = mmap(NULL, GPIO_LEN, PROT_READ | PROT_WRITE,
                   MAP_SHARED, fd, gpioBase);
    close(fd);
    if (m == MAP_FAILED) {
        perror("mmap");
        return false;
    }
    gpio = reinterpret_cast<volatile uint32_t *>(m);
    return true;
}

static void unmapGpio() {
    if (gpio) {
        munmap((void *)gpio, GPIO_LEN);
        gpio = nullptr;
    }
}

static void setPinOutput(int pin) {
    int fsel = pin / 10;
    int shift = (pin % 10) * 3;
    volatile uint32_t *fselReg = gpio + (0x00 / sizeof(uint32_t)) + fsel;
    uint32_t v = *fselReg;
    v &= ~(0x7u << shift);
    v |= (0x1u << shift); // 001 = output
    *fselReg = v;
    // ensure pin is low to start
    setPinLow(pin);
}

static void setPinHigh(int pin) {
    volatile uint32_t *regSet =
        gpio + (0x1C / sizeof(uint32_t)) + (pin / 32);
    *regSet = (1u << (pin & 31));
}

static void setPinLow(int pin) {
    volatile uint32_t *regClr =
        gpio + (0x28 / sizeof(uint32_t)) + (pin / 32);
    *regClr = (1u << (pin & 31));
}

