# Written by AI
import asyncio
import json
import socket
import uuid
from typing import Callable, Dict, List, Optional, Set

IP_PREFIX = "10.102.251."
NUM_IPS = 20  # Consecutive IPs from IP_PREFIX
PORT = 9090


class Peer:
    """Represents a connected peer."""
    def __init__(self, peer_id: str, ip: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.peer_id = peer_id
        self.ip = ip
        self.reader = reader
        self.writer = writer

    async def send(self, event: str, data: dict):
        """Send a message to this peer."""
        message = json.dumps({"event": event, "data": data}) + "\n"
        self.writer.write(message.encode())
        await self.writer.drain()

    async def close(self):
        """Close connection to this peer."""
        self.writer.close()
        await self.writer.wait_closed()


class Multiplayer:
    """
    Multiplayer networking class with peer-to-peer connections.
    
    Usage:
        mp = Multiplayer("my_game")
        mp.on("message", lambda peer, data: print(f"Got message: {data}"))
        mp.on("peer_connected", lambda peer: print(f"Peer connected: {peer.peer_id}"))
        mp.on("all_peers_connected", lambda: print("All peers connected!"))
        await mp.start_server()
        await mp.seek_peers(3)  # Seek 3 peers
        mp.emit("message", {"text": "Hello everyone!"})  # Send to all peers
    """

    def __init__(self, app_name: str):
        self.app_name = app_name
        self.peer_id = str(uuid.uuid4())
        self.peers: Dict[str, Peer] = {}  # peer_id -> Peer
        self.max_peers: int = 0
        self.seeking_peers: int = 0
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._server: Optional[asyncio.Server] = None
        self._own_ips: Set[str] = set()
        self._connected_ips: Set[str] = set()
        self._running = False

    def _get_own_ips(self) -> Set[str]:
        """Get all IP addresses of this machine."""
        ips = set()
        try:
            # Get hostname-based IP
            hostname = socket.gethostname()
            ips.add(socket.gethostbyname(hostname))
        except Exception:
            pass
        
        # Try to get all network interfaces
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ips.add(info[4][0])
        except Exception:
            pass
        
        # Add localhost
        ips.add("127.0.0.1")
        
        # Also check which IPs in our range belong to us
        for i in range(1, NUM_IPS + 1):
            ip = f"{IP_PREFIX}{i}"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind((ip, 0))
                ips.add(ip)
                s.close()
            except Exception:
                pass
        
        return ips

    def on(self, event: str, handler: Callable):
        """Register an event handler (socket.io-like API)."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: Optional[Callable] = None):
        """Remove an event handler."""
        if event in self._event_handlers:
            if handler is None:
                del self._event_handlers[event]
            elif handler in self._event_handlers[event]:
                self._event_handlers[event].remove(handler)

    def _emit_local(self, event: str, *args):
        """Emit an event to local handlers."""
        if event in self._event_handlers:
            for handler in self._event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        asyncio.create_task(handler(*args))
                    else:
                        handler(*args)
                except Exception as e:
                    print(f"Error in event handler for '{event}': {e}")

    def emit(self, event: str, data: dict):
        """Send a message to all connected peers."""
        asyncio.create_task(self._emit_to_all(event, data))

    async def _emit_to_all(self, event: str, data: dict):
        """Send a message to all connected peers (async)."""
        for peer in list(self.peers.values()):
            try:
                await peer.send(event, data)
            except Exception as e:
                print(f"Error sending to peer {peer.peer_id}: {e}")
                await self._remove_peer(peer)

    async def send_to(self, peer_id: str, event: str, data: dict):
        """Send a message to a specific peer."""
        if peer_id in self.peers:
            try:
                await self.peers[peer_id].send(event, data)
            except Exception as e:
                print(f"Error sending to peer {peer_id}: {e}")
                await self._remove_peer(self.peers[peer_id])

    @property
    def is_accepting_connections(self) -> bool:
        """Check if we're still accepting new connections."""
        return len(self.peers) < self.max_peers and self.seeking_peers > 0

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming connection."""
        addr = writer.get_extra_info('peername')
        ip = addr[0] if addr else "unknown"
        peer = None
        
        try:
            # First, receive info request
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not line:
                writer.close()
                return
            
            msg = json.loads(line.decode().strip())
            
            if msg.get("type") == "info_request":
                # Respond with our info
                response = {
                    "type": "info_response",
                    "app_name": self.app_name,
                    "peer_id": self.peer_id,
                    "accepting": self.is_accepting_connections
                }
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
                
                # Wait for connection request
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not line:
                    writer.close()
                    return
                
                msg = json.loads(line.decode().strip())
            
            if msg.get("type") == "connect_request":
                remote_peer_id = msg.get("peer_id")
                remote_app = msg.get("app_name")
                
                # Check if we should accept
                if (remote_app == self.app_name and 
                    self.is_accepting_connections and
                    remote_peer_id not in self.peers and
                    remote_peer_id != self.peer_id):
                    
                    # Accept connection
                    response = {"type": "connect_accept", "peer_id": self.peer_id}
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()
                    
                    peer = Peer(remote_peer_id, ip, reader, writer)
                    self.peers[remote_peer_id] = peer
                    self._connected_ips.add(ip)
                    
                    self._emit_local("peer_connected", peer)
                    
                    # Check if all peers connected
                    if len(self.peers) >= self.max_peers:
                        self.seeking_peers = 0
                        self._emit_local("all_peers_connected")
                    
                    # Handle messages from this peer
                    await self._handle_peer_messages(peer)
                else:
                    # Reject connection
                    response = {"type": "connect_reject", "reason": "Not accepting connections"}
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()
                    writer.close()
                    
        except asyncio.TimeoutError:
            writer.close()
        except Exception as e:
            print(f"Error handling connection from {ip}: {e}")
            if peer:
                await self._remove_peer(peer)
            else:
                writer.close()

    async def _handle_peer_messages(self, peer: Peer):
        """Handle incoming messages from a connected peer."""
        try:
            while self._running:
                line = await peer.reader.readline()
                if not line:
                    break
                
                try:
                    msg = json.loads(line.decode().strip())
                    event = msg.get("event", "message")
                    data = msg.get("data", {})
                    self._emit_local(event, peer, data)
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            print(f"Connection to peer {peer.peer_id} lost: {e}")
        finally:
            await self._remove_peer(peer)

    async def _remove_peer(self, peer: Peer):
        """Remove a peer from the connected list."""
        if peer.peer_id in self.peers:
            del self.peers[peer.peer_id]
            if peer.ip in self._connected_ips:
                self._connected_ips.discard(peer.ip)
            try:
                await peer.close()
            except Exception:
                pass
            self._emit_local("peer_disconnected", peer)

    async def start_server(self):
        """Start the server to accept incoming connections."""
        self._own_ips = self._get_own_ips()
        self._running = True
        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            PORT
        )
        print(f"Multiplayer server started on port {PORT}")

    async def stop_server(self):
        """Stop the server and disconnect all peers."""
        self._running = False
        
        # Close all peer connections
        for peer in list(self.peers.values()):
            await self._remove_peer(peer)
        
        # Stop the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _try_connect_to_ip(self, ip: str) -> bool:
        """Try to connect to a peer at the given IP."""
        # Skip our own IPs
        if ip in self._own_ips:
            return False
        
        # Skip already connected IPs
        if ip in self._connected_ips:
            return False
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, PORT),
                timeout=2.0
            )
            
            try:
                # Request info
                info_request = {"type": "info_request", "peer_id": self.peer_id}
                writer.write((json.dumps(info_request) + "\n").encode())
                await writer.drain()
                
                # Get info response
                line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                if not line:
                    writer.close()
                    return False
                
                info = json.loads(line.decode().strip())
                
                # Check if compatible and accepting
                if (info.get("type") == "info_response" and
                    info.get("app_name") == self.app_name and
                    info.get("accepting", False) and
                    info.get("peer_id") != self.peer_id and
                    info.get("peer_id") not in self.peers):
                    
                    # Send connect request
                    connect_request = {
                        "type": "connect_request",
                        "peer_id": self.peer_id,
                        "app_name": self.app_name
                    }
                    writer.write((json.dumps(connect_request) + "\n").encode())
                    await writer.drain()
                    
                    # Wait for response
                    line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                    if not line:
                        writer.close()
                        return False
                    
                    response = json.loads(line.decode().strip())
                    
                    if response.get("type") == "connect_accept":
                        remote_peer_id = info.get("peer_id")
                        peer = Peer(remote_peer_id, ip, reader, writer)
                        self.peers[remote_peer_id] = peer
                        self._connected_ips.add(ip)
                        
                        self._emit_local("peer_connected", peer)
                        
                        # Start handling messages in background
                        asyncio.create_task(self._handle_peer_messages(peer))
                        
                        return True
                
                writer.close()
                return False
                
            except Exception as e:
                writer.close()
                return False
                
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            return False

    async def seek_peers(self, num_peers: int):
        """
        Seek and connect to the specified number of peers.
        Will scan all IPs in the configured range.
        """
        self.max_peers = num_peers
        self.seeking_peers = num_peers
        
        # Build list of IPs to try
        ips_to_try = [f"{IP_PREFIX}{i}" for i in range(1, NUM_IPS + 1)]
        
        # Keep trying until we have enough peers or give up
        attempts = 0
        max_attempts = 10
        
        while len(self.peers) < num_peers and attempts < max_attempts:
            attempts += 1
            
            # Try all IPs concurrently
            tasks = [self._try_connect_to_ip(ip) for ip in ips_to_try]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            if len(self.peers) >= num_peers:
                break
            
            # Wait a bit before retrying
            if len(self.peers) < num_peers and attempts < max_attempts:
                await asyncio.sleep(1.0)
        
        if len(self.peers) >= num_peers:
            self.seeking_peers = 0
            self._emit_local("all_peers_connected")
        else:
            self._emit_local("seek_timeout", len(self.peers), num_peers)

    @property
    def connected_peers(self) -> List[Peer]:
        """Get list of all connected peers."""
        return list(self.peers.values())

    @property
    def peer_count(self) -> int:
        """Get the number of connected peers."""
        return len(self.peers)