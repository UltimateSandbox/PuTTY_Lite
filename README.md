# Web SSH Terminal

A browser-based SSH terminal using Python, FastAPI, and xterm.js.

## What It Does

Opens an SSH session in your browser instead of a terminal window. Perfect for:
- Monitoring Raspberry Pi clusters without juggling terminal windows
- Class demos where you want SSH visible in a browser tab
- Building dashboards that need embedded terminal access

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────┐      SSH       ┌─────────────┐
│   Browser   │◄──────────────────►│   FastAPI   │◄──────────────►│  Remote Pi  │
│  (xterm.js) │                    │   Server    │                │             │
└─────────────┘                    │   + PTY     │                └─────────────┘
                                   └─────────────┘
```

- **PTY (Pseudo-Terminal)**: Tricks SSH into thinking it's running in a real terminal
- **WebSocket**: Bidirectional pipe between browser and PTY
- **xterm.js**: Full terminal emulator in the browser (colors, cursor, the works)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python server.py --port 8765
```

### 3. Open Browser

Navigate to `http://localhost:8765`, enter your SSH details, and connect!

## Usage

### Connection Parameters

- **User**: SSH username (default: `pi`)
- **Host**: IP address or hostname of the target machine
- **Port**: SSH port (default: `22`)

### Keyboard Shortcuts

Standard terminal shortcuts work:
- `Ctrl+C` - Interrupt current process
- `Ctrl+D` - Send EOF / logout
- `Ctrl+L` - Clear screen
- Arrow keys, tab completion, etc.

## Configuration

### Running on a Different Port

```bash
python server.py --port 9000
```

### Binding to All Interfaces

The server binds to `0.0.0.0` by default, making it accessible from other machines on your network.

```bash
python server.py --host 127.0.0.1  # Localhost only
python server.py --host 0.0.0.0   # All interfaces (default)
```

## Security Notes

⚠️ **This is designed for local network use only!**

- No authentication on the web interface
- SSH credentials are passed via WebSocket (use on trusted networks)
- For production use, add:
  - HTTPS/WSS
  - Web interface authentication
  - Rate limiting

## How the PTY Magic Works

The interesting bit is the `PTYProcess` class in `server.py`:

1. `pty.fork()` creates a pseudo-terminal and forks a child process
2. Child process runs `ssh user@host`
3. Parent process reads/writes to the PTY file descriptor
4. WebSocket bridges PTY ↔ browser

The PTY is what makes SSH think it's in a real terminal, so you get:
- Proper color codes (ANSI escape sequences)
- Cursor movement (for vim, htop, etc.)
- Terminal resizing
- Interactive password prompts

## Extending This

### Multiple Sessions (Future)

The code already tracks sessions in `active_sessions` dict. To support multiple terminals:
1. Add session ID to WebSocket URL
2. Create dashboard UI with multiple `<div id="terminal-N">` elements
3. Each connects to its own WebSocket endpoint

### For Red Blue Sun Tzu

This could become the "Valerie" monitoring interface:
- 5 terminal panes (Red Zu, Blue Zu, Melissa, Abed, Controller)
- Real-time game log streaming
- CSS Grid layout for the dashboard

## Dependencies

- **FastAPI**: Modern Python web framework
- **uvicorn**: ASGI server
- **xterm.js**: Terminal emulator for browsers (loaded from CDN)
- **xterm-addon-fit**: Auto-resize terminal to container
- **xterm-addon-web-links**: Clickable URLs in terminal

## License

Apache 2.0 (same as Red Blue Sun Tzu project)
