#!/usr/bin/env python3
"""
Web SSH Terminal Server (Windows Compatible)
=============================================
A FastAPI server that bridges SSH sessions to the browser via WebSocket.
Uses Paramiko for SSH, so it works on Windows, macOS, and Linux.

Usage:
    python server.py --host 0.0.0.0 --port 8765

Then open http://localhost:8765 in your browser.
"""

import asyncio
import argparse
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import paramiko
import uvicorn


app = FastAPI(title="Web SSH Terminal")


class SSHSession:
    """
    Manages an SSH connection using Paramiko.
    Works on Windows, macOS, and Linux.
    """
    
    def __init__(self):
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None
        self.connected = False
        
    def connect(self, host: str, port: int, username: str, password: str) -> tuple[bool, str]:
        """
        Connect to SSH server.
        
        Returns:
            (success, message) tuple
        """
        try:
            self.client = paramiko.SSHClient()
            # Auto-add unknown host keys (like ssh -o StrictHostKeyChecking=no)
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            self.client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=10,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Get an interactive shell channel
            self.channel = self.client.invoke_shell(
                term='xterm-256color',
                width=80,
                height=24
            )
            self.channel.setblocking(0)  # Non-blocking reads
            self.connected = True
            
            return True, "Connected"
            
        except paramiko.AuthenticationException:
            return False, "Authentication failed - check username/password"
        except paramiko.SSHException as e:
            return False, f"SSH error: {e}"
        except Exception as e:
            return False, f"Connection failed: {e}"
    
    def resize(self, width: int, height: int) -> None:
        """Resize the terminal."""
        if self.channel:
            try:
                self.channel.resize_pty(width=width, height=height)
            except:
                pass
    
    def read(self) -> bytes:
        """Read available output from SSH channel (non-blocking)."""
        if not self.channel:
            return b""
        try:
            if self.channel.recv_ready():
                return self.channel.recv(4096)
            return b""
        except:
            return b""
    
    def write(self, data: bytes) -> None:
        """Write input to SSH channel."""
        if self.channel:
            try:
                self.channel.send(data)
            except:
                pass
    
    def close(self) -> None:
        """Close the SSH connection."""
        self.connected = False
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
        if self.client:
            try:
                self.client.close()
            except:
                pass
        self.channel = None
        self.client = None


@app.get("/", response_class=HTMLResponse)
async def get_terminal_page():
    """Serve the terminal UI."""
    return HTMLResponse(content=open("static/index.html").read())


@app.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket):
    """
    WebSocket endpoint that bridges the browser to an SSH session.
    
    Protocol:
        - Client sends JSON: {"type": "connect", "host": "...", "port": 22, "username": "...", "password": "..."}
        - Client sends JSON: {"type": "input", "data": "..."} for keystrokes
        - Client sends JSON: {"type": "resize", "cols": N, "rows": M} for resize
        - Server sends JSON: {"type": "output", "data": "..."} for terminal output
        - Server sends JSON: {"type": "error", "message": "..."} for errors
        - Server sends JSON: {"type": "connected"} on successful connection
    """
    await websocket.accept()
    
    ssh_session = SSHSession()
    
    async def read_ssh_output():
        """Continuously read from SSH and send to browser."""
        while ssh_session.connected:
            await asyncio.sleep(0.02)  # Small delay to batch output
            data = ssh_session.read()
            if data:
                try:
                    # Send as text (base64 or decoded)
                    await websocket.send_json({
                        "type": "output",
                        "data": data.decode('utf-8', errors='replace')
                    })
                except:
                    break
    
    output_task = None
    
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")
            
            if msg_type == "connect":
                # New connection request
                host = message.get("host", "localhost")
                port = message.get("port", 22)
                username = message.get("username", "pi")
                password = message.get("password", "")
                
                success, msg = ssh_session.connect(host, port, username, password)
                
                if success:
                    await websocket.send_json({"type": "connected"})
                    # Start reading output
                    output_task = asyncio.create_task(read_ssh_output())
                else:
                    await websocket.send_json({"type": "error", "message": msg})
                
            elif msg_type == "input":
                # User typed something
                data = message.get("data", "")
                ssh_session.write(data.encode())
                
            elif msg_type == "resize":
                # Terminal resized
                cols = message.get("cols", 80)
                rows = message.get("rows", 24)
                ssh_session.resize(cols, rows)
                
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if output_task:
            output_task.cancel()
        ssh_session.close()


def main():
    parser = argparse.ArgumentParser(description="Web SSH Terminal Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              Web SSH Terminal (Windows Compatible)           ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://localhost:{args.port:<5}                    ║
║                                                              ║
║  Open in browser and enter your SSH connection details.      ║
║  Press Ctrl+C to stop the server.                            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
