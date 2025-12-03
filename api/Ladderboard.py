import gpiozero
from api.LadderboardButton import LadderboardButton
from api.LadderboardLed import LadderboardLed


class Ladderboard:
    def __init__(self):
        self.LED_PINS = [17, 18, 27, 22, 23, 24, 4, 25, 3, 2]
        self.LED_COLORS = [
            "RED",
            "RED",
            "YELLOW",
            "YELLOW",
            "GREEN",
            "GREEN",
            "BLUE",
            "BLUE",
            "STATUS_OK",
            "STATUS_FAIL",
        ]
        self.BUTTON_PINS = [9, 10, 8, 7]
        self.buttons = []
        self.leds = []

        for i in range(len(self.LED_PINS)):
            self.leds.append(LadderboardLed(self.LED_PINS[i], self.LED_COLORS[i]))

        for button_pin in self.BUTTON_PINS:
            self.buttons.append(LadderboardButton(button_pin))

    def countdown(self, delay):
        pass  # lol

    def leds_on(self, color="ALL"):
        for led in self.leds:
            if color == "ALL" or led.get_color() == color:
                led.on()

    def leds_off(self, color="ALL"):
        for led in self.leds:
            if color == "ALL" or led.get_color() == color:
                led.off()

    def leds_toggle(self, color="ALL"):
        for led in self.leds:
            if color == "ALL" or led.get_color() == color:
                led.toggle()
