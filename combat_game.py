import asyncio
import random
from api.Ladderboard import Ladderboard
from api.Multiplayer import Multiplayer

# ============================================
# GAME CONFIGURATION
# ============================================

# Game identifier for multiplayer matchmaking
GAME_NAME = "combat_game"

# Number of players to wait for
NUM_PLAYERS = 2

# Number of normal LEDs in the "world" (excluding status LEDs)
WORLD_SIZE = 8

# Player health settings
INITIAL_HEALTH = 5

# Button action mappings
# Button 0 (leftmost): attack left
# Button 1 (center-left): move left
# Button 2 (center-right): move right
# Button 3 (rightmost): attack right
BUTTON_ACTIONS = {
    0: "attack_left",
    1: "move_left",
    2: "move_right",
    3: "attack_right",
}

# LED indices for status and victory/defeat animations
STATUS_OK_LED = 8      # Green status LED
STATUS_FAIL_LED = 9    # Red status LED
GREEN_LEDS = [4, 5]    # Main green LEDs for winner
RED_LEDS = [0, 1]      # Main red LEDs for loser

# Spawn positions for players (opposite sides)
SPAWN_POSITIONS = [0, WORLD_SIZE - 1]  # Left side and right side

# Countdown duration
COUNTDOWN_SECONDS = 3

# Time to wait before restart after game over
RESTART_DELAY_SECONDS = 5

# Attack cooldown in seconds (prevents spam-clicking)
ATTACK_COOLDOWN = 1


# ============================================
# GAME CLASSES
# ============================================


class Player:
    """Represents a player with a character on the ladderboard."""

    def __init__(self, player_id: str, position: int = None):
        self.player_id = player_id
        self.position = position if position is not None else 0
        self.health = INITIAL_HEALTH

    def move_left(self):
        """Move the character one LED to the left (wraps around)."""
        self.position = (self.position - 1) % WORLD_SIZE

    def move_right(self):
        """Move the character one LED to the right (wraps around)."""
        self.position = (self.position + 1) % WORLD_SIZE

    def take_damage(self):
        """Reduce health by 1."""
        self.health = max(0, self.health - 1)

    def is_alive(self) -> bool:
        """Check if player is still alive."""
        return self.health > 0


class Game:
    """
    Main game controller for the combat game.
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
        self.players = {}  # player_id -> Player
        self.local_player = None  # Reference to this Pi's player
        self.remote_player = None  # Reference to the opponent
        self.running = False
        self.game_over = False
        self.game_started = False  # Track if game has started (after countdown)
        self._loop = None  # Store event loop reference for thread-safe callbacks
        self._last_attack_press_time = 0  # Track last valid attack button press
        self._loading = False  # Track if loading animation is running
        self._is_host = False  # Determines which peer coordinates round start
        self._round_start_event = asyncio.Event()  # Sync start between peers
        self._current_round = 0  # Track current round number to prevent cross-round signals

        # Create local player (position will be set when peer connects)
        self.local_player = Player(self.mp.peer_id, position=0)
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

        if action == "move_left":
            def handler(self=self):
                if self.game_over or not self.game_started:
                    return
                self._move_with_skip(-1)
                self._broadcast_state()
                self.render()
            button.on_press(handler)

        elif action == "move_right":
            def handler(self=self):
                if self.game_over or not self.game_started:
                    return
                self._move_with_skip(1)
                self._broadcast_state()
                self.render()
            button.on_press(handler)

        elif action == "attack_left":
            def handler(self=self):
                if self.game_over or not self.game_started:
                    return
                self._attack_direction(-1)
            button.on_press(handler)

        elif action == "attack_right":
            def handler(self=self):
                if self.game_over or not self.game_started:
                    return
                self._attack_direction(1)
            button.on_press(handler)

    def _attack_direction(self, direction: int):
        """
        Attack in a direction (-1 for left, +1 for right).
        If opponent is on the adjacent cell, deal damage.
        Pressing the button activates a cooldown period during which no attacks can occur.
        """
        import time
        
        if self.remote_player is None:
            return

        current_time = time.time()
        
        # Minecraft-style: attack only if button hasn't been pressed within cooldown window
        if current_time - self._last_attack_press_time < ATTACK_COOLDOWN:
            return  # Too soon since last press
        
        # Record this valid press time
        self._last_attack_press_time = current_time
        
        # Check if target is on adjacent position
        target_position = (self.local_player.position + direction) % WORLD_SIZE

        if self.remote_player.position == target_position:
            # Hit the opponent!
            self._broadcast_attack(target_position)
            # Blink green status LED (dealt damage)
            self._blink_status_hit()
            print(f"[ATTACK] You hit the opponent at position {target_position}!")

    def _schedule_blink(self, led_index: int):
        """Schedule an LED blink on the event loop."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._blink_led(led_index))
            )

    def _blink_status_hit(self):
        """Blink status LED when dealing damage (swap mapping)."""
        self._schedule_blink(STATUS_FAIL_LED)

    def _blink_status_hurt(self):
        """Blink status LED when taking damage (swap mapping)."""
        self._schedule_blink(STATUS_OK_LED)

    async def _blink_led(self, led_index: int):
        """Blink a single LED once."""
        self.board.leds[led_index].on()
        await asyncio.sleep(0.2)
        self.board.leds[led_index].off()

    async def _victory_animation(self):
        """Play victory animation - blink all green LEDs for a few seconds."""
        for _ in range(10):  # 10 blinks over ~4 seconds
            self.board.leds[GREEN_LEDS[0]].on()
            self.board.leds[GREEN_LEDS[1]].on()
            await asyncio.sleep(0.2)
            self.board.leds[GREEN_LEDS[0]].off()
            self.board.leds[GREEN_LEDS[1]].off()
            await asyncio.sleep(0.2)
        print("Victory! You won!")

    async def _defeat_animation(self):
        """Play defeat animation - blink all red LEDs for a few seconds."""
        for _ in range(10):  # 10 blinks over ~4 seconds
            self.board.leds[RED_LEDS[0]].on()
            self.board.leds[RED_LEDS[1]].on()
            await asyncio.sleep(0.2)
            self.board.leds[RED_LEDS[0]].off()
            self.board.leds[RED_LEDS[1]].off()
            await asyncio.sleep(0.2)
        print("Defeat! You lost!")

    def _setup_network_handlers(self):
        """Setup handlers for network events."""
        # Handle game state updates from other players
        self.mp.on("game_state", self._on_game_state)

        # Handle attack events
        self.mp.on("attack", self._on_attack)

        # Handle round start sync
        self.mp.on("start_round", self._on_start_round)

        # Handle new peer connections
        self.mp.on("peer_connected", self._on_peer_connected)

        # Handle peer disconnections
        self.mp.on("peer_disconnected", self._on_peer_disconnected)

        # Handle when all peers are connected
        self.mp.on("all_peers_connected", self._on_all_peers_connected)

    def _on_game_state(self, peer, data: dict):
        """Handle incoming game state from another player."""
        player_id = data.get("player_id")
        position = data.get("position")
        health = data.get("health", INITIAL_HEALTH)

        if player_id and player_id != self.mp.peer_id:
            if player_id not in self.players:
                self.players[player_id] = Player(player_id, position)
                self.players[player_id].health = health
                self.remote_player = self.players[player_id]
                # Set deterministic spawn positions based on peer_id comparison
                self._assign_spawn_positions()
                self._determine_host()
            else:
                self.players[player_id].position = position
                self.players[player_id].health = health

        # Re-render with updated state
        self.render()

    def _on_attack(self, peer, data: dict):
        """Handle incoming attack from opponent."""
        target_position = data.get("target_position")
        
        # Check if we're at the target position
        if self.local_player.position == target_position:
            self.local_player.take_damage()
            # Blink red status LED (took damage)
            self._blink_status_hurt()
            
            # Debug print health status
            print(f"[DAMAGE] You took damage! Your health: {self.local_player.health}/{INITIAL_HEALTH}")
            if self.remote_player:
                print(f"[DAMAGE] Opponent health: {self.remote_player.health}/{INITIAL_HEALTH}")
            
            # Broadcast updated state
            self._broadcast_state()
            
            # Check if game over
            if not self.local_player.is_alive():
                self._handle_game_over(winner=False)
        
        self.render()

    def _on_start_round(self, peer, data: dict):
        """Handle round start sync signal."""
        round_num = data.get("round_num", 0)
        # Only set event if this message is for the current round
        if round_num == self._current_round and self._round_start_event:
            self._round_start_event.set()

    def _handle_game_over(self, winner: bool):
        """Handle end of game."""
        self.game_over = True
        self.board.leds_off("ALL")
        
        if self._loop is not None:
            if winner:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._victory_animation())
                )
            else:
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._defeat_animation())
                )

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
            if self.remote_player and self.remote_player.player_id == peer.peer_id:
                self.remote_player = None
                # End current game immediately if in progress
                if self.game_started and not self.game_over:
                    print("Opponent disconnected during game. Ending round...")
                    self.game_over = True
                    self.game_started = False
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
            "health": self.local_player.health,
        }
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.mp._emit_to_all("game_state", state))
            )

    def _broadcast_attack(self, target_position: int):
        """Broadcast attack to all peers (thread-safe)."""
        attack_data = {
            "attacker_id": self.local_player.player_id,
            "target_position": target_position,
        }
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.mp._emit_to_all("attack", attack_data))
            )

    def render(self):
        """
        Render the current game state to the local board.
        Shows player positions as lit LEDs.
        """
        if self.game_over:
            return

        # Turn off all world LEDs first
        for i in range(WORLD_SIZE):
            self.board.leds[i].off()

        # Show local player position
        self.board.leds[self.local_player.position].on()

        # Show remote player position if exists
        if self.remote_player:
            self.board.leds[self.remote_player.position].on()

    async def _loading_animation(self):
        """Display loading animation while waiting for opponent."""
        self._loading = True
        led_index = 0
        
        while self._loading:
            # Turn off all world LEDs
            for i in range(WORLD_SIZE):
                self.board.leds[i].off()
            
            # Light up current LED
            self.board.leds[led_index].on()
            
            # Move to next LED
            led_index = (led_index + 1) % WORLD_SIZE
            
            await asyncio.sleep(0.1)
        
        # Turn off all LEDs when done
        self.board.leds_off("ALL")

    def _stop_loading(self):
        """Stop the loading animation."""
        self._loading = False

    async def _wait_for_opponent(self):
        """Wait for an opponent to connect, showing loading animation."""
        if self.remote_player is not None:
            return  # Already have opponent
        
        print("Waiting for opponent...")
        loading_task = asyncio.create_task(self._loading_animation())
        
        try:
            # Keep seeking until we have an opponent
            while self.running and self.remote_player is None:
                await self.mp.seek_peers(NUM_PLAYERS - 1)
                if self.remote_player is None:
                    await asyncio.sleep(0.5)  # Brief pause before retry
        finally:
            self._stop_loading()
            await loading_task

    async def _countdown(self):
        """Display countdown sequence before game starts."""
        print("Get ready!")
        
        # Step 1: All 8 world LEDs on for 2 seconds
        for i in range(WORLD_SIZE):
            self.board.leds[i].on()
        await asyncio.sleep(2)
        
        # Step 2: Only green LEDs for 1 second
        for i in range(WORLD_SIZE):
            self.board.leds[i].off()
        for led_idx in GREEN_LEDS:
            self.board.leds[led_idx].on()
        await asyncio.sleep(1)
        
        # Step 3: Only yellow LEDs for 1 second
        for led_idx in GREEN_LEDS:
            self.board.leds[led_idx].off()
        for led_idx in [2, 3]:  # Yellow LEDs
            self.board.leds[led_idx].on()
        await asyncio.sleep(1)
        
        # Step 4: Only red LEDs for 1 second
        for i in [2, 3]:
            self.board.leds[i].off()
        for led_idx in RED_LEDS:
            self.board.leds[led_idx].on()
        await asyncio.sleep(1)
        
        # Clear all LEDs
        self.board.leds_off("ALL")
        print("GO!")

    def _assign_spawn_positions(self):
        """
        Assign spawn positions based on peer_id comparison.
        The player with the 'smaller' peer_id gets position 0 (left),
        the other gets position 7 (right). This ensures both clients
        see the same board state.
        """
        if self.remote_player is None:
            return
        
        if self.local_player.player_id < self.remote_player.player_id:
            self.local_player.position = SPAWN_POSITIONS[0]  # Left
            self.remote_player.position = SPAWN_POSITIONS[1]  # Right
        else:
            self.local_player.position = SPAWN_POSITIONS[1]  # Right
            self.remote_player.position = SPAWN_POSITIONS[0]  # Left

    def _determine_host(self):
        """Decide which peer coordinates round starts (smallest peer_id)."""
        if self.remote_player is None:
            self._is_host = True
            return
        self._is_host = self.local_player.player_id < self.remote_player.player_id

    def _signal_round_start(self):
        """Host signals round start to peers and itself."""
        if self._round_start_event:
            self._round_start_event.set()
        if self._loop is not None:
            round_data = {"round_num": self._current_round}
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.mp._emit_to_all("start_round", round_data))
            )

    def _move_with_skip(self, direction: int):
        """Move player; if target occupied by opponent, jump over to next cell."""
        if self.remote_player is None:
            # Normal move if no opponent yet
            self.local_player.position = (self.local_player.position + direction) % WORLD_SIZE
            return

        target = (self.local_player.position + direction) % WORLD_SIZE
        if target == self.remote_player.position:
            # Jump over opponent to the next cell in same direction
            target = (target + direction) % WORLD_SIZE
        self.local_player.position = target

    def _reset_game(self):
        """Reset game state for a new round."""
        self.game_over = False
        self.game_started = False
        self.local_player.health = INITIAL_HEALTH
        if self.remote_player:
            self.remote_player.health = INITIAL_HEALTH
        # Re-assign spawn positions (deterministic based on peer_id)
        self._assign_spawn_positions()
        # Reset attack cooldown
        self._last_attack_press_time = 0
        # Increment round counter to invalidate any pending signals from previous round
        self._current_round += 1
        self.board.leds_off("ALL")

    async def start(self):
        """Start the game - connect to peers and begin game loop."""
        self.running = True

        # Store the event loop reference for thread-safe button callbacks
        self._loop = asyncio.get_running_loop()

        # Start multiplayer server
        await self.mp.start_server()

        # Wait for initial opponent connection
        await self._wait_for_opponent()
        
        # Determine host now that we know peers
        self._determine_host()

        # Game loop with restart capability
        while self.running:
            # Check if we need to wait for opponent (after disconnect or initial)
            if self.remote_player is None:
                await self._wait_for_opponent()
                if self.remote_player is None:
                    continue  # Still no opponent, retry
                self._determine_host()
            
            # Assign spawn positions now that both players are connected
            self._assign_spawn_positions()
            
            # Fresh event for this round - MUST be created BEFORE host signals
            # to avoid race condition where signal arrives before event is created
            self._round_start_event = asyncio.Event()
            
            # Host signals start; others wait for the signal
            if self._is_host:
                self._signal_round_start()

            # Wait for start signal then run the shared countdown
            await self._round_start_event.wait()
            
            # Check if opponent disconnected while waiting
            if self.remote_player is None:
                continue

            # Countdown before game starts
            await self._countdown()

            # Game has now started - enable controls
            self.game_started = True
            
            print("Game started!")
            print(f"Local player position: {self.local_player.position}")
            print("Controls:")
            print("  Button 0 (leftmost): Attack Left")
            print("  Button 1: Move Left")
            print("  Button 2: Move Right")
            print("  Button 3 (rightmost): Attack Right")
            print(f"\nHealth: {INITIAL_HEALTH} - Attack adjacent opponent to deal damage!")

            # Broadcast initial state and render
            self._broadcast_state()
            self.render()

            # Main game loop - keeps the game running until game over
            try:
                while self.running and not self.game_over:
                    # Check for opponent disconnect
                    if self.remote_player is None:
                        print("Opponent disconnected!")
                        break
                    
                    # Check for game over condition (opponent's health depleted)
                    if not self.remote_player.is_alive():
                        self._handle_game_over(winner=True)
                        break
                    await asyncio.sleep(0.1)
                
                # If game ended normally (not disconnect), wait for restart
                if self.game_over and self.running and self.remote_player is not None:
                    print(f"\nRestarting in {RESTART_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RESTART_DELAY_SECONDS)
                    self._reset_game()
                    print("\n" + "="*40)
                    print("NEW ROUND!")
                    print("="*40 + "\n")
                elif self.remote_player is None:
                    # Opponent disconnected - reset and go back to waiting
                    self._reset_game()
                    print("\nSearching for new opponent...\n")
                    
            except KeyboardInterrupt:
                await self.stop()
                break

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