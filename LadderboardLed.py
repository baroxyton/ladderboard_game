from gpiozero import LED


class LadderboardLed:
    def __init__(self, pin, color):
        self._pin = pin
        self._color = color
        self._on = False
        self._LED = LED(self._pin)

    def get_color(self):
        return self._color

    def on(self):
        self._LED.on()
        self._on = True

    def toggle(self):
        if self._on:
            self.off()
        else:
            self.on()

    def off(self):
        self._LED.off()
        self._on = False

    def is_on(self):
        return self._on
