#!/usr/bin/env python3
"""
Web SSH Terminal Server
=======================
A FastAPI server that bridges SSH sessions to the browser via WebSocket.

Architecture:
- Spawns a PTY (pseudo-terminal) running SSH
- WebSocket connects browser to PTY
- xterm.js on frontend renders the terminal

Usage:
    python server.py --host 0.0.0.0 --port 8765

Then open http://localhost:8765 in your browser.
"""

import asyncio
import argparse
import fcntl
import os
import pty
import signal
import struct
import termios
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


app = FastAPI(title="Web SSH Terminal")


class PTYProcess:
    """
    Manages a pseudo-terminal process (like SSH).
    
    The PTY gives us a "fake" terminal that the SSH process thinks
    is a real terminal, so it behaves normally with colors, cursor
    movement, etc.
    """
    
    def __init__(self):
        self.fd: Optional[int] = None  # File descriptor for the PTY
        self.pid: Optional[int] = None  # Process ID of the child
        
    def spawn(self, command: list[str]) -> bool:
        """
        Spawn a new process in a PTY.
        
        Args:
            command: Command to run, e.g., ["ssh", "user@host"]
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Fork a new process with a PTY
            # - pid: 0 in child, child's PID in parent
            # - fd: file descriptor for the PTY master side
            self.pid, self.fd = pty.fork()
            
            if self.pid == 0:
                # We're in the child process - execute the command
                os.execvp(command[0], command)
            else:
                # We're in the parent - set non-blocking IO
                flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
                fcntl.fcntl(self.fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                return True
                
        except Exception as e:
            print(f"Failed to spawn PTY: {e}")
            return False
    
    def resize(self, rows: int, cols: int) -> None:
        """
        Resize the PTY to match the browser terminal size.
        
        This is important! Without this, programs like vim or htop
        won't know how big the terminal is and will render incorrectly.
        """
        if self.fd is not None:
            # TIOCSWINSZ = "Terminal IO Control - Set WINdow SiZe"
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
    
    def read(self) -> bytes:
        """Read available output from the PTY (non-blocking)."""
        if self.fd is None:
            return b""
        try:
            return os.read(self.fd, 4096)
        except BlockingIOError:
            return b""
        except OSError:
            return b""
    
    def write(self, data: bytes) -> None:
        """Write input to the PTY (what the user types)."""
        if self.fd is not None:
            try:
                os.write(self.fd, data)
            except OSError:
                pass
    
    def terminate(self) -> None:
        """Clean up the PTY and child process."""
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGTERM)
                os.waitpid(self.pid, 0)
            except (OSError, ChildProcessError):
                pass
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = None
        self.pid = None


# Store active PTY sessions (in production, you'd want session management)
active_sessions: dict[str, PTYProcess] = {}


@app.get("/", response_class=HTMLResponse)
async def get_terminal_page():
    """Serve the terminal UI."""
    return HTMLResponse(content=open("static/index.html").read())


@app.websocket("/ws/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    host: str = "localhost",
    user: str = "pi",
    port: int = 22
):
    """
    WebSocket endpoint that bridges the browser to an SSH session.
    
    Query params:
        host: SSH host to connect to
        user: SSH username
        port: SSH port (default 22)
    
    Protocol:
        - Client sends JSON: {"type": "input", "data": "..."} for keystrokes
        - Client sends JSON: {"type": "resize", "rows": N, "cols": M} for resize
        - Server sends raw terminal output as binary
    """
    await websocket.accept()
    
    # Create and spawn the PTY with SSH
    pty_process = PTYProcess()
    ssh_command = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(port), f"{user}@{host}"]
    
    if not pty_process.spawn(ssh_command):
        await websocket.send_text('{"error": "Failed to spawn SSH process"}')
        await websocket.close()
        return
    
    session_id = str(id(websocket))
    active_sessions[session_id] = pty_process
    
    async def read_pty_output():
        """Continuously read from PTY and send to browser."""
        while True:
            await asyncio.sleep(0.01)  # Small delay to batch output
            data = pty_process.read()
            if data:
                try:
                    await websocket.send_bytes(data)
                except:
                    break
    
    # Start the output reader task
    output_task = asyncio.create_task(read_pty_output())
    
    try:
        while True:
            # Receive input from browser
            message = await websocket.receive_json()
            
            if message.get("type") == "input":
                # User typed something - send to PTY
                data = message.get("data", "")
                pty_process.write(data.encode())
                
            elif message.get("type") == "resize":
                # Browser terminal resized - update PTY
                rows = message.get("rows", 24)
                cols = message.get("cols", 80)
                pty_process.resize(rows, cols)
                
    except WebSocketDisconnect:
        print(f"Client disconnected: {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Clean up
        output_task.cancel()
        pty_process.terminate()
        active_sessions.pop(session_id, None)


def main():
    parser = argparse.ArgumentParser(description="Web SSH Terminal Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on")
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    Web SSH Terminal                          ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{args.host}:{args.port:<5}                      ║
║                                                              ║
║  Open in browser and enter your SSH connection details.      ║
║  Press Ctrl+C to stop the server.                            ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
