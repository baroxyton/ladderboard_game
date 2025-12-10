from api.Ladderboard import Ladderboard
from time import sleep
from api.Multiplayer import Multiplayer

mp = Multiplayer("my_game")
mp.on("message", lambda peer, data: print(f"Got message: {data}"))
mp.on("peer_connected", lambda peer: print(f"Peer connected: {peer.peer_id}"))
mp.on("all_peers_connected", lambda: print("All peers connected!"))
await mp.start_server()
await mp.seek_peers(3)  # Seek 3 peers
mp.emit("message", {"text": "Hello everyone!"})  # Send to all peers