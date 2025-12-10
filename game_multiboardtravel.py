import asyncio
import random
from api.Ladderboard import Ladderboard
from api.Multiplayer import Multiplayer

# ============================================
# GAME CONFIGURATION
# ============================================

# Game identifier for multiplayer matchmaking
GAME_NAME = "multiboard_travel"

# Number of players to wait for
NUM_PLAYERS = 2

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
    
    def __init__(self, player_id: str, position: int = None):
        self.player_id = player_id
        self.position = position if position is not None else random.randint(0, WORLD_SIZE - 1)
        
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
            
    def set_state(self, lit_leds: list):
        """Set the world state from a list of lit LED positions."""
        self.lit_leds = set(lit_leds)
            
    def is_led_on(self, position: int) -> bool:
        """Check if an LED at a position is lit in the world."""
        return position in self.lit_leds


class Game:
    """
    Main game controller that manages players, the world, and rendering.
    Each Raspberry Pi runs one instance with its own ladderboard.
    Game state is synchronized via the Multiplayer networking API.
    """
    
    def __init__(self, board: Ladderboard, multiplayer: Multiplayer):
        """
        Initialize the game with a single ladderboard and multiplayer connection.
        
        Args:
            board: The local Ladderboard instance
            multiplayer: The Multiplayer instance for networking
        """
        self.board = board
        self.mp = multiplayer
        self.world = GameWorld()
        self.players = {}  # player_id -> Player
        self.local_player = None  # Reference to this Pi's player
        self.running = False
        self._loop = None  # Store event loop reference for thread-safe callbacks
        
        # Create local player
        self.local_player = Player(self.mp.peer_id)
        self.players[self.mp.peer_id] = self.local_player
        
        # Setup button handlers
        self._setup_button_handlers()
        
        # Setup network message handlers
        self._setup_network_handlers()
        
    def _setup_button_handlers(self):
        """Configure button handlers based on BUTTON_ACTIONS mapping."""
        for button_index, action in BUTTON_ACTIONS.items():
            if action is not None:
                self._bind_action(button_index, action)
                    
    def _bind_action(self, button_index: int, action: str):
        """
        Bind an action to a specific button for the local player.
        
        Args:
            button_index: Index of the button (0-3)
            action: Action string from BUTTON_ACTIONS
        """
        button = self.board.buttons[button_index]
        
        # Create action handlers
        if action == "toggle_led":
            def handler():
                self.world.toggle_led(self.local_player.position)
                self._broadcast_state()
                self.render()
            button.on_press(handler)
            
        elif action == "move_left":
            def handler():
                self.local_player.move_left()
                self._broadcast_state()
                self.render()
            button.on_press(handler)
            
        elif action == "move_right":
            def handler():
                self.local_player.move_right()
                self._broadcast_state()
                self.render()
            button.on_press(handler)
            
        # Add more actions here in the future:
        # elif action == "some_new_action":
        #     def handler():
        #         # new action logic
        #         self._broadcast_state()
        #         self.render()
        #     button.on_press(handler)
    
    def _setup_network_handlers(self):
        """Setup handlers for network events."""
        # Handle game state updates from other players
        self.mp.on("game_state", self._on_game_state)
        
        # Handle new peer connections
        self.mp.on("peer_connected", self._on_peer_connected)
        
        # Handle peer disconnections
        self.mp.on("peer_disconnected", self._on_peer_disconnected)
        
        # Handle when all peers are connected
        self.mp.on("all_peers_connected", self._on_all_peers_connected)
    
    def _on_game_state(self, peer, data: dict):
        """Handle incoming game state from another player."""
        # Update remote player position
        player_id = data.get("player_id")
        position = data.get("position")
        world_leds = data.get("world_leds", [])
        
        if player_id and player_id != self.mp.peer_id:
            if player_id not in self.players:
                self.players[player_id] = Player(player_id, position)
            else:
                self.players[player_id].position = position
        
        # Update world state
        self.world.set_state(world_leds)
        
        # Re-render with updated state
        self.render()
    
    def _on_peer_connected(self, peer):
        """Handle a new peer connecting."""
        print(f"Peer connected: {peer.peer_id}")
        # Send our current state to the new peer
        self._broadcast_state()
    
    def _on_peer_disconnected(self, peer):
        """Handle a peer disconnecting."""
        print(f"Peer disconnected: {peer.peer_id}")
        if peer.peer_id in self.players:
            del self.players[peer.peer_id]
        self.render()
    
    def _on_all_peers_connected(self):
        """Handle when all peers have connected."""
        print("All players connected! Game starting...")
        self._broadcast_state()
        self.render()
    
    def _broadcast_state(self):
        """Broadcast current game state to all peers (thread-safe)."""
        state = {
            "player_id": self.local_player.player_id,
            "position": self.local_player.position,
            "world_leds": list(self.world.lit_leds)
        }
        # Schedule the async emit on the event loop (thread-safe for button callbacks)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.mp._emit_to_all("game_state", state))
            )
    
    def render(self):
        """
        Render the current game state to the local board.
        Shows:
        - World LEDs that are toggled on
        - The local player's character position (as a lit LED)
        - Other players' positions are also shown
        """
        # First, turn off all normal LEDs (the world)
        for i in range(WORLD_SIZE):
            self.board.leds[i].off()
        
        # Turn on LEDs that are part of the world state
        for led_pos in self.world.lit_leds:
            self.board.leds[led_pos].on()
        
        # Turn on LEDs at all player positions
        for player in self.players.values():
            self.board.leds[player.position].on()
    
    async def start(self):
        """Start the game - connect to peers and begin game loop."""
        self.running = True
        
        # Store the event loop reference for thread-safe button callbacks
        self._loop = asyncio.get_running_loop()
        
        # Start multiplayer server
        await self.mp.start_server()
        
        print(f"Waiting for {NUM_PLAYERS - 1} other player(s)...")
        print(f"Local player spawned at position {self.local_player.position}")
        
        # Initial render - show our player while waiting
        self.render()
        
        # Seek other players
        await self.mp.seek_peers(NUM_PLAYERS - 1)
        
        print("Game started!")
        print(f"Local player position: {self.local_player.position}")
        print("Controls:")
        for btn, action in BUTTON_ACTIONS.items():
            if action:
                print(f"  Button {btn}: {action}")
        
        # Main game loop - keeps the game running
        try:
            while self.running:
                await asyncio.sleep(0.1)  # Small delay to prevent CPU spinning
        except KeyboardInterrupt:
            await self.stop()
            
    async def stop(self):
        """Stop the game and clean up."""
        self.running = False
        # Turn off all LEDs
        self.board.leds_off("ALL")
        # Stop multiplayer server
        await self.mp.stop_server()
        print("Game stopped.")


# ============================================
# MAIN ENTRY POINT
# ============================================

async def main():
    # Create the local ladderboard (one per Raspberry Pi)
    board = Ladderboard()
    
    # Create multiplayer connection
    mp = Multiplayer(GAME_NAME)
    
    # Create and start the game
    game = Game(board, mp)
    
    try:
        await game.start()
    except KeyboardInterrupt:
        await game.stop()


if __name__ == "__main__":
    asyncio.run(main())

