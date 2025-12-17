#include <iostream>
#include <thread>
#include <chrono>
#include <gpiod.hpp> // Requires libgpiod-dev
#include <cmath>     // For rounding

int main() {
    int pinNum;
    int chipNum = 0;
    double frequencyHz = 100.0; // Standard for LEDs (stops flickering)
    double brightnessPercent;   // 0 to 100

    std::cout << "--- GPIO Software PWM (Brightness Control) ---\n";
    std::cout << "Enter GPIO Chip number (usually 0): ";
    std::cin >> chipNum;
    std::cout << "Enter GPIO Pin number: ";
    std::cin >> pinNum;
    
    // We fix the frequency to 100Hz or higher so the human eye doesn't see flickering
    std::cout << "Enter Frequency in Hz (Rec: 100): ";
    std::cin >> frequencyHz;

    std::cout << "Enter Brightness (0-100%): ";
    std::cin >> brightnessPercent;

    // Safety checks
    if (brightnessPercent < 0) brightnessPercent = 0;
    if (brightnessPercent > 100) brightnessPercent = 100;
    if (frequencyHz <= 0) frequencyHz = 1;

    // Calculate timings
    // Total time for one cycle in microseconds (1,000,000 us = 1 sec)
    double periodUs = 1000000.0 / frequencyHz;
    
    // How long to stay ON
    long onTimeUs = (long)(periodUs * (brightnessPercent / 100.0));
    
    // How long to stay OFF
    long offTimeUs = (long)(periodUs - onTimeUs);

    std::cout << "Cycle Info -> Period: " << periodUs << "us | ON: " << onTimeUs << "us | OFF: " << offTimeUs << "us\n";
    std::cout << "Running... Press Ctrl+C to stop.\n";

    try {
        std::string chipPath = "gpiochip" + std::to_string(chipNum);
        gpiod::chip chip(chipPath);
        gpiod::line line = chip.get_line(pinNum);
        line.request({"gpio-pwm", gpiod::line_request::DIRECTION_OUTPUT, 0});

        while (true) {
            // 1. Turn ON
            if (onTimeUs > 0) {
                line.set_value(1);
                std::this_thread::sleep_for(std::chrono::microseconds(onTimeUs));
            }

            // 2. Turn OFF
            if (offTimeUs > 0) {
                line.set_value(0);
                std::this_thread::sleep_for(std::chrono::microseconds(offTimeUs));
            }
        }
    } 
    catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
