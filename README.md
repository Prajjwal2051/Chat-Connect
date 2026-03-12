# Chat-Connect

> **Original Creator: Prajjwal  |  © 2025 All Rights Reserved**
> Unauthorized copying or redistribution is strictly prohibited.

A full-featured, real-time **CLI chat application** built entirely with the Python standard library (no third-party packages needed). Supports multiple simultaneous users, server-side authentication, ANSI colors, message timestamps, slash commands, and graceful shutdown.

---

## Features

| Category | Details |
|---|---|
| **Networking** | TCP sockets, multi-threaded (one thread per client) |
| **Security** | Server password auth, duplicate username prevention, regex username validation, rate limiting (1 msg/sec), 500-char message cap |
| **UI** | ANSI colors, HH:MM timestamps on every message, join/leave notifications |
| **CLI** | `argparse` on both server and client — full `--help`, `--version`, `--host`, `--port`, etc. |
| **Slash commands** | `/help`, `/list`, `/clear`, `/quit` |
| **Logging** | Colored structured logging on the server; optional file logging via `--log` |
| **Shutdown** | `Ctrl+C` on the server notifies all clients and closes sockets cleanly |

---

## Requirements

- Python **3.8+**
- No third-party libraries — pure standard library

---

## Quick Start

### 1. Start the server

```bash
python server.py
```

### 2. Connect a client (in a new terminal)

```bash
python clinet.py
```

You will be prompted for the server password (`prajjwal@chat` by default) and a username.

---

## Server — Full CLI Reference

```
python server.py [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--host ADDR` | `127.0.0.1` | Address to bind the server to |
| `--port PORT` | `57815` | TCP port to listen on |
| `--password PASS` | `prajjwal@chat` | Password clients must supply to connect |
| `--limit N` | `5` | Maximum simultaneous clients |
| `--log FILE` | *(none)* | Also write structured logs to a file |
| `--no-color` | — | Disable ANSI color output |
| `--version` | — | Print version and exit |
| `--help` | — | Show help and exit |

**Examples:**

```bash
# Default run
python server.py

# Custom port, password, and file logging
python server.py --port 9090 --password s3cr3t --limit 10 --log chat.log

# Accept connections from any machine on the network
python server.py --host 0.0.0.0 --port 9090
```

---

## Client — Full CLI Reference

```
python clinet.py [OPTIONS]
```

| Flag | Default | Description |
|---|---|---|
| `--host ADDR` | `127.0.0.1` | Server address to connect to |
| `--port PORT` | `57815` | Server port |
| `--password PASS` | *(prompted)* | Server password (hidden prompt if omitted) |
| `--username NAME` | *(prompted)* | Your display name |
| `--no-color` | — | Disable ANSI color output |
| `--version` | — | Print version and exit |
| `--help` | — | Show help and exit |

**Examples:**

```bash
# Default run
python clinet.py

# Connect to a remote server with a pre-set username
python clinet.py --host 192.168.1.10 --port 9090 --username Alice
```

---

## In-Chat Slash Commands

| Command | Description |
|---|---|
| `/help` | Show available commands |
| `/list` | List all currently online users |
| `/clear` | Clear your terminal screen |
| `/quit` | Disconnect gracefully and exit |

---

## Finding a Free Port

If `57815` is already in use on your machine, run:

```bash
python to_find_a_free_port.py
```

Then pass the printed number with `--port` on both the server and all clients.

---

## Project Structure

```
Chat-Connect/
├── server.py               # Multi-client TCP server
├── clinet.py               # CLI chat client
├── to_find_a_free_port.py  # Utility: find a free OS port
├── requirements.txt        # Dependency notes (stdlib only)
└── README.md               # This file
```

---

## Communication Sequence

![Chat Server Communication Sequence](./chat_server_communication_sequence.png)

---

## License

© 2025 Prajjwal. All Rights Reserved.
Unauthorized copying, redistribution, or modification of this project is strictly prohibited.
