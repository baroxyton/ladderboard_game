from Ladderboard import Ladderboard
from time import sleep

board = Ladderboard()

def red_lights():
    board.leds_on("RED")

def toggle_lights():
    board.leds_toggle()

board.buttons[0].on_press(red_lights)
board.buttons[1].on_press(toggle_lights)

def main():
    pass

while True:
    sleep(1)
