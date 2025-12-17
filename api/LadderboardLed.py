from api.BrightnessLed import BrightnessLed


class LadderboardLed:
    def __init__(self, pin, color):
        self._pin = pin
        self._color = color
        self._on = False
        self._brightness = 1.0
        self._LED = BrightnessLed(self._pin)

    def get_color(self):
        return self._color

    def on(self, brightness: float = 1.0):
        """Turn the LED on with optional brightness (0.0-1.0)."""
        self._brightness = brightness
        self._LED.on(brightness=brightness)
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
    
    @property
    def brightness(self) -> float:
        """Get current brightness."""
        return self._brightness
    
    @brightness.setter
    def brightness(self, value: float):
        """Set brightness (0.0-1.0)."""
        self._brightness = value
        if self._on:
            self._LED.on(brightness=value)
