import asyncio
from api.Ladderboard import Ladderboard
from api.Multiplayer import Multiplayer


async def main():
    mp = Multiplayer("my_game")
    mp.on("message", lambda peer, data: print(f"Got message: {data}"))
    mp.on("peer_connected", lambda peer: print(f"Peer connected: {peer.peer_id}"))
    mp.on("all_peers_connected", lambda: print("All peers connected!"))
    
    await mp.start_server()
    await mp.seek_peers(1)
    mp.emit("message", {"text": "Hello everyone!"})  # Send to all peers
    
    # Keep the server running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await mp.stop_server()


if __name__ == "__main__":
    asyncio.run(main())