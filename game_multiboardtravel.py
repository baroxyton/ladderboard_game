from api.Ladderboard import Ladderboard
from time import sleep
import random

# ============================================
# GAME CONFIGURATION
# ============================================

# Number of normal LEDs in the "world" (excluding status LEDs)
WORLD_SIZE = 8

# Button action mappings - assign any action to any button (0-3)
# Available actions: "toggle_led", "move_left", "move_right"
# You can add more actions in the future and map them here
BUTTON_ACTIONS = {
    0: "toggle_led",    # Button 0 toggles the LED at character position
    1: "move_left",     # Button 1 moves character left
    2: "move_right",    # Button 2 moves character right
    3: None,            # Button 3 not assigned (available for future actions)
}


# ============================================
# GAME CLASSES
# ============================================

class Player:
    """Represents a player with a character on the ladderboard."""
    
    def __init__(self, player_id: int, board: Ladderboard):
        self.player_id = player_id
        self.board = board
        self.position = random.randint(0, WORLD_SIZE - 1)  # Random spawn position
        
    def move_left(self):
        """Move the character one LED to the left (wraps around)."""
        self.position = (self.position - 1) % WORLD_SIZE
        
    def move_right(self):
        """Move the character one LED to the right (wraps around)."""
        self.position = (self.position + 1) % WORLD_SIZE


class GameWorld:
    """
    Represents the shared game world.
    The world is a set of LEDs that can be toggled on/off independently of player positions.
    """
    
    def __init__(self):
        # Track which LEDs in the world are "permanently" on (toggled by players)
        self.lit_leds = set()
        
    def toggle_led(self, position: int):
        """Toggle an LED in the world on/off."""
        if position in self.lit_leds:
            self.lit_leds.remove(position)
        else:
            self.lit_leds.add(position)
            
    def is_led_on(self, position: int) -> bool:
        """Check if an LED at a position is lit in the world."""
        return position in self.lit_leds


class Game:
    """
    Main game controller that manages players, the world, and rendering.
    Designed for 2 players on 2 different ladderboards.
    """
    
    def __init__(self, boards: list[Ladderboard]):
        """
        Initialize the game with a list of ladderboards.
        Each board corresponds to one player.
        
        Args:
            boards: List of Ladderboard instances (one per player)
        """
        self.boards = boards
        self.world = GameWorld()
        self.players = []
        self.running = False
        
        # Create a player for each board
        for i, board in enumerate(boards):
            player = Player(i, board)
            self.players.append(player)
            
        # Setup button handlers for each player
        self._setup_button_handlers()
        
    def _setup_button_handlers(self):
        """Configure button handlers based on BUTTON_ACTIONS mapping."""
        for player in self.players:
            for button_index, action in BUTTON_ACTIONS.items():
                if action is not None:
                    self._bind_action(player, button_index, action)
                    
    def _bind_action(self, player: Player, button_index: int, action: str):
        """
        Bind an action to a specific button for a player.
        
        Args:
            player: The player whose button to bind
            button_index: Index of the button (0-3)
            action: Action string from BUTTON_ACTIONS
        """
        button = player.board.buttons[button_index]
        
        # Create action handlers
        # Using a closure to capture the current player reference
        if action == "toggle_led":
            def handler(p=player):
                self.world.toggle_led(p.position)
                self.render()
            button.on_press(handler)
            
        elif action == "move_left":
            def handler(p=player):
                p.move_left()
                self.render()
            button.on_press(handler)
            
        elif action == "move_right":
            def handler(p=player):
                p.move_right()
                self.render()
            button.on_press(handler)
            
        # Add more actions here in the future:
        # elif action == "some_new_action":
        #     def handler(p=player):
        #         # new action logic
        #         self.render()
        #     button.on_press(handler)
    
    def render(self):
        """
        Render the current game state to all boards.
        Each board shows:
        - World LEDs that are toggled on
        - The player's character position (as a lit LED)
        """
        for player in self.players:
            board = player.board
            
            # First, turn off all normal LEDs (the world)
            for i in range(WORLD_SIZE):
                board.leds[i].off()
            
            # Turn on LEDs that are part of the world state
            for led_pos in self.world.lit_leds:
                board.leds[led_pos].on()
            
            # Turn on the LED at the player's position (character)
            board.leds[player.position].on()
    
    def start(self):
        """Start the game loop."""
        self.running = True
        
        # Initial render - all LEDs off except player positions
        self.render()
        
        print("Game started!")
        print(f"Player spawn positions: {[p.position for p in self.players]}")
        print("Controls:")
        for btn, action in BUTTON_ACTIONS.items():
            if action:
                print(f"  Button {btn}: {action}")
        
        # Main game loop - keeps the game running
        try:
            while self.running:
                sleep(0.1)  # Small delay to prevent CPU spinning
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        """Stop the game and clean up."""
        self.running = False
        # Turn off all LEDs on all boards
        for board in self.boards:
            board.leds_off("ALL")
        print("Game stopped.")


# ============================================
# MAIN ENTRY POINT
# ============================================

if __name__ == "__main__":
    # Create ladderboards for each player
    # In a real setup, each Raspberry Pi would create its own board
    # and networking would sync the game state
    
    # For now, we create the boards locally
    # When running on separate Pi's, each would only create one board
    board1 = Ladderboard()
    board2 = Ladderboard()
    
    # Create and start the game
    game = Game([board1, board2])
    game.start()

