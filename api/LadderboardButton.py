from gpiozero import Button


class LadderboardButton:
    def __init__(self, pin):
        self._pin = pin
        self._is_pressed = False
        self._up_events = []
        self._down_events = []
        self._button = Button(self._pin)
        self._button.when_pressed = self._on_down
        self._button.when_released = self._on_up

    def is_pressed(self):
        return self._button.is_active

    def on_press(self, callback):
        self._up_events.append(callback)

    def on_pressed(self, fun):
        self._press_events.append(fun)

    def _on_down(self):
        self._is_pressed = True
        for event in self._down_events:
            event()

    def _on_up(self):
        self._is_pressed = False
        for event in self._up_events:
            event()
