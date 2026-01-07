import asyncio
import random
import threading
import sys
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
BUTTON_ACTIONS = {
    0: "attack_left",
    1: "move_left",
    2: "move_right",
    3: "attack_right",
}

# LED indices
STATUS_OK_LED = 8
STATUS_FAIL_LED = 9
GREEN_LEDS = [4, 5]
RED_LEDS = [0, 1]

# Spawn positions
SPAWN_POSITIONS = [0, WORLD_SIZE - 1]

# Timing
COUNTDOWN_SECONDS = 3
RESTART_DELAY_SECONDS = 5


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
        self.position = (self.position - 1) % WORLD_SIZE

    def move_right(self):
        self.position = (self.position + 1) % WORLD_SIZE

    def take_damage(self):
        self.health = max(0, self.health - 1)

    def is_alive(self) -> bool:
        return self.health > 0


class Game:
    """
    Main game controller with added CLI Hacks.
    """

    def __init__(self, board: Ladderboard, multiplayer: Multiplayer):
        self.board = board
        self.mp = multiplayer
        self.players = {}
        self.local_player = None
        self.remote_player = None
        self.running = False
        self.game_over = False
        self._loop = None

        # --- HACK CONFIGURATION ---
        self.hack_killaura = False
        self.hack_random_move = False
        # --------------------------

        self.local_player = Player(self.mp.peer_id, position=0)
        self.players[self.mp.peer_id] = self.local_player

        self._setup_button_handlers()
        self._setup_network_handlers()

    # ... [Previous button handling code remains the same] ...
    def _setup_button_handlers(self):
        for button_index, action in BUTTON_ACTIONS.items():
            if action is not None:
                self._bind_action(button_index, action)

    def _bind_action(self, button_index: int, action: str):
        button = self.board.buttons[button_index]
        if action == "move_left":
            button.on_press(lambda: self._safe_action(self.local_player.move_left))
        elif action == "move_right":
            button.on_press(lambda: self._safe_action(self.local_player.move_right))
        elif action == "attack_left":
            button.on_press(lambda: self._safe_attack(-1))
        elif action == "attack_right":
            button.on_press(lambda: self._safe_attack(1))

    def _safe_action(self, action_func):
        """Helper to run movement actions."""
        if self.game_over: return
        action_func()
        self._broadcast_state()
        self.render()

    def _safe_attack(self, direction):
        """Helper to run attack actions."""
        if self.game_over: return
        self._attack_direction(direction)

    def _attack_direction(self, direction: int):
        if self.remote_player is None:
            return

        target_position = (self.local_player.position + direction) % WORLD_SIZE

        if self.remote_player.position == target_position:
            self._broadcast_attack(target_position)
            self._schedule_blink(STATUS_OK_LED)
            print(f"[ATTACK] You hit the opponent at position {target_position}!")

    def _schedule_blink(self, led_index: int):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self._blink_led(led_index))
            )

    async def _blink_led(self, led_index: int):
        self.board.leds[led_index].on()
        await asyncio.sleep(0.2)
        self.board.leds[led_index].off()

    async def _victory_animation(self):
        for _ in range(10):
            self.board.leds[GREEN_LEDS[0]].on()
            self.board.leds[GREEN_LEDS[1]].on()
            await asyncio.sleep(0.2)
            self.board.leds[GREEN_LEDS[0]].off()
            self.board.leds[GREEN_LEDS[1]].off()
            await asyncio.sleep(0.2)
        print("Victory! You won!")

    async def _defeat_animation(self):
        for _ in range(10):
            self.board.leds[RED_LEDS[0]].on()
            self.board.leds[RED_LEDS[1]].on()
            await asyncio.sleep(0.2)
            self.board.leds[RED_LEDS[0]].off()
            self.board.leds[RED_LEDS[1]].off()
            await asyncio.sleep(0.2)
        print("Defeat! You lost!")

    # ... [Network handlers] ...
    def _setup_network_handlers(self):
        self.mp.on("game_state", self._on_game_state)
        self.mp.on("attack", self._on_attack)
        self.mp.on("peer_connected", self._on_peer_connected)
        self.mp.on("peer_disconnected", self._on_peer_disconnected)
        self.mp.on("all_peers_connected", self._on_all_peers_connected)

    def _on_game_state(self, peer, data: dict):
        player_id = data.get("player_id")
        position = data.get("position")
        health = data.get("health", INITIAL_HEALTH)

        if player_id and player_id != self.mp.peer_id:
            if player_id not in self.players:
                self.players[player_id] = Player(player_id, position)
                self.players[player_id].health = health
                self.remote_player = self.players[player_id]
                self._assign_spawn_positions()
            else:
                self.players[player_id].position = position
                self.players[player_id].health = health
        self.render()

    def _on_attack(self, peer, data: dict):
        target_position = data.get("target_position")
        if self.local_player.position == target_position:
            self.local_player.take_damage()
            self._schedule_blink(STATUS_FAIL_LED)
            print(f"[DAMAGE] Took damage! Health: {self.local_player.health}")
            self._broadcast_state()
            if not self.local_player.is_alive():
                self._handle_game_over(winner=False)
        self.render()

    def _handle_game_over(self, winner: bool):
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
        print(f"Peer connected: {peer.peer_id}")
        self._broadcast_state()

    def _on_peer_disconnected(self, peer):
        print(f"Peer disconnected: {peer.peer_id}")
        if peer.peer_id in self.players:
            del self.players[peer.peer_id]
            if self.remote_player and self.remote_player.player_id == peer.peer_id:
                self.remote_player = None
        self.render()

    def _on_all_peers_connected(self):
        print("All players connected! Game starting...")
        self._broadcast_state()
        self.render()

    def _broadcast_state(self):
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
        attack_data = {
            "attacker_id": self.local_player.player_id,
            "target_position": target_position,
        }
        if self._loop is not None:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.mp._emit_to_all("attack", attack_data))
            )

    def render(self):
        if self.game_over: return
        for i in range(WORLD_SIZE):
            self.board.leds[i].off()
        self.board.leds[self.local_player.position].on()
        if self.remote_player:
            self.board.leds[self.remote_player.position].on()

    async def _countdown(self):
        print("Get ready!")
        for i in range(COUNTDOWN_SECONDS, 0, -1):
            print(f"Starting in {i}...")
            self.board.leds_on("ALL")
            await asyncio.sleep(0.5)
            self.board.leds_off("ALL")
            await asyncio.sleep(0.5)
        print("GO!")

    def _assign_spawn_positions(self):
        if self.remote_player is None: return
        if self.local_player.player_id < self.remote_player.player_id:
            self.local_player.position = SPAWN_POSITIONS[0]
            self.remote_player.position = SPAWN_POSITIONS[1]
        else:
            self.local_player.position = SPAWN_POSITIONS[1]
            self.remote_player.position = SPAWN_POSITIONS[0]

    def _reset_game(self):
        self.game_over = False
        self.local_player.health = INITIAL_HEALTH
        if self.remote_player:
            self.remote_player.health = INITIAL_HEALTH
        self._assign_spawn_positions()
        self.board.leds_off("ALL")

    # ============================================
    # HACK IMPLEMENTATIONS
    # ============================================

    def _cli_input_listener(self):
        """Runs in a separate thread to handle CLI commands without blocking."""
        print("\n=== HACK CLI READY ===")
        print("Type 'killaura' to toggle auto-attack")
        print("Type 'move' to toggle random movement")
        print("Type 'status' to see enabled hacks\n")
        
        while self.running:
            try:
                # Use sys.stdin.readline to be slightly more thread-friendly than input()
                cmd = sys.stdin.readline().strip().lower()
                
                if cmd == "killaura":
                    self.hack_killaura = not self.hack_killaura
                    print(f"\n[HACK] Killaura enabled: {self.hack_killaura}")
                
                elif cmd == "move":
                    self.hack_random_move = not self.hack_random_move
                    print(f"\n[HACK] Random move enabled: {self.hack_random_move}")
                
                elif cmd == "status":
                    print(f"\n[STATUS] Killaura: {self.hack_killaura} | Move: {self.hack_random_move}")
                
            except Exception as e:
                print(f"CLI Error: {e}")
                break

    async def _hack_logic_loop(self):
        """Main loop that executes the hacks if they are enabled."""
        while self.running:
            if not self.game_over:
                
                # --- RANDOM MOVE HACK ---
                if self.hack_random_move:
                    if random.choice([True, False]):
                        self.local_player.move_left()
                    else:
                        self.local_player.move_right()
                    self._broadcast_state()
                    self.render()
                    # Wait a bit so we don't teleport too fast and crash logic
                    await asyncio.sleep(0.4) 

                # --- KILLAURA HACK ---
                if self.hack_killaura and self.remote_player:
                    lp = self.local_player.position
                    rp = self.remote_player.position
                    
                    # Check Left
                    if (lp - 1) % WORLD_SIZE == rp:
                        print("[HACK] Killaura detected enemy LEFT")
                        self._attack_direction(-1)
                        await asyncio.sleep(0.2) # Attack delay
                    
                    # Check Right
                    elif (lp + 1) % WORLD_SIZE == rp:
                        print("[HACK] Killaura detected enemy RIGHT")
                        self._attack_direction(1)
                        await asyncio.sleep(0.2) # Attack delay

            # Run this loop 10 times a second
            await asyncio.sleep(0.1)

    async def start(self):
        self.running = True
        self._loop = asyncio.get_running_loop()

        # Start Multiplayer
        await self.mp.start_server()

        print(f"Waiting for {NUM_PLAYERS - 1} other player(s)...")
        self.render()
        await self.mp.seek_peers(NUM_PLAYERS - 1)
        
        # --- START HACKS ---
        # 1. Start the CLI listener in a background thread
        cli_thread = threading.Thread(target=self._cli_input_listener, daemon=True)
        cli_thread.start()

        # 2. Start the Hack Logic in the asyncio loop
        asyncio.create_task(self._hack_logic_loop())
        # -------------------

        while self.running:
            await self._countdown()
            print("Game started! Use CLI commands to cheat.")
            self._broadcast_state()
            self.render()

            try:
                while self.running and not self.game_over:
                    if self.remote_player and not self.remote_player.is_alive():
                        self._handle_game_over(winner=True)
                        break
                    await asyncio.sleep(0.1)
                
                if self.game_over and self.running:
                    print(f"\nRestarting in {RESTART_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(RESTART_DELAY_SECONDS)
                    self._reset_game()
                    
            except KeyboardInterrupt:
                await self.stop()
                break

    async def stop(self):
        self.running = False
        self.board.leds_off("ALL")
        await self.mp.stop_server()
        print("Game stopped.")

# ============================================
# MAIN ENTRY POINT
# ============================================

async def main():
    board = Ladderboard()
    mp = Multiplayer(GAME_NAME)
    game = Game(board, mp)

    try:
        await game.start()
    except KeyboardInterrupt:
        await game.stop()

if __name__ == "__main__":
    asyncio.run(main())
