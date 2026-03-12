# =============================================================
#   Chat-Connect — TCP Chat Application
#   Original Creator : Prajjwal
#   © 2025  All Rights Reserved.
#   Unauthorized copying or redistribution is strictly prohibited.
# =============================================================
"""
Chat-Connect Client
===================
Feature-rich CLI chat client with ANSI colors, message timestamps,
slash commands, secure password prompt, and graceful disconnect.

Usage:
    python clinet.py [OPTIONS]

Options:
    --host HOST         Server address      (default: 127.0.0.1)
    --port PORT         Server port         (default: 57815)
    --password PASS     Server password     (prompted securely if omitted)
    --username NAME     Your username       (prompted if omitted)
    --no-color          Disable colored output
    --version           Show version and exit

Slash commands (type inside the chat):
    /help               Show available commands
    /list               List online users
    /clear              Clear the terminal screen
    /quit               Disconnect and exit
"""

import socket
import threading
import sys
import os
import signal
import argparse
import getpass
from datetime import datetime

__version__ = "1.0.0"
__author__  = "Prajjwal"

# ── Watermark ─────────────────────────────────────────────────────────────────
WATERMARK = """
╔══════════════════════════════════════════════════════╗
║            C H A T - C O N N E C T                   ║
║         ──────────────────────────────               ║
║         Original Creator : Prajjwal                  ║
║         © 2025  All Rights Reserved                  ║
║  Unauthorized copying is strictly prohibited.        ║
╚══════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
  /help    Show this help message
  /list    List all online users
  /clear   Clear the terminal screen
  /quit    Disconnect and exit
"""

# ── ANSI colors ───────────────────────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

_use_color = True

def col(text, *codes):
    if not _use_color:
        return text
    return "".join(codes) + text + C.RESET

# ── Shared state ──────────────────────────────────────────────────────────────
_connected   = True
_input_lock  = threading.Lock()  # used to avoid interleaved output

# ── Output helpers ────────────────────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M")

def _print_above(line):
    """Print a line above the current input prompt without disturbing it."""
    with _input_lock:
        sys.stdout.write(f"\r{line}\n")
        sys.stdout.write("You: ")
        sys.stdout.flush()

def _print_info(msg):
    _print_above(col(msg, C.YELLOW))

def _print_err(msg):
    _print_above(col(f"[✗] {msg}", C.RED))

def _clear():
    os.system("cls" if os.name == "nt" else "clear")

# ── Receive loop (runs in background thread) ──────────────────────────────────
def _recv_loop(client):
    global _connected
    while _connected:
        try:
            raw = client.recv(2048)
        except Exception:
            if _connected:
                _print_err("Lost connection to server.")
            break

        if not raw:
            _print_info("Connection closed by server.")
            break

        msg = raw.decode("utf-8").strip()
        if not msg:
            continue

        if msg.startswith("MSG:"):
            # Format from server: MSG:HH:MM:username:content
            parts = msg.split(":", 4)
            if len(parts) == 5:
                _, hh, mm, sender, content = parts
                time_str = col(f"{hh}:{mm}", C.DIM)
                name_str = col(sender, C.CYAN)
                _print_above(f"{time_str} {name_str}{col(':', C.DIM)} {content}")
            else:
                _print_above(msg)

        elif msg.startswith("SYS:"):
            body  = msg[4:]
            parts = body.split(":", 2)
            # Timestamped SYS: HH:MM:text  (join/leave notifications)
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
                time_str = col(f"{parts[0]}:{parts[1]}", C.DIM)
                text_str = col(parts[2], C.YELLOW)
                _print_above(f"{time_str} {text_str}")
            else:
                _print_above(col(body, C.YELLOW))
        else:
            _print_above(col(f"[Server] {msg}", C.YELLOW))

    _connected = False

# ── Send loop (main thread) ───────────────────────────────────────────────────
def _send_loop(client):
    global _connected
    while _connected:
        try:
            with _input_lock:
                sys.stdout.write("You: ")
                sys.stdout.flush()
            msg = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            _quit(client)
            return

        if msg is None:
            break
        msg = msg.rstrip("\n").rstrip("\r")

        if not msg:
            continue

        lower = msg.lower()

        if lower == "/quit":
            _quit(client)
            return
        elif lower == "/help":
            print(col(HELP_TEXT, C.CYAN))
            continue
        elif lower == "/list":
            try:
                client.sendall("CMD:LIST".encode("utf-8"))
            except Exception:
                _print_err("Could not send command.")
            continue
        elif lower == "/clear":
            _clear()
            print(col(WATERMARK, C.CYAN))
            continue
        elif lower.startswith("/"):
            _print_info(f"Unknown command '{msg}'. Type /help for a list.")
            continue

        try:
            client.sendall(msg.encode("utf-8"))
        except Exception:
            _print_err("Could not send message. Connection lost.")
            _connected = False
            break

# ── Clean disconnect ──────────────────────────────────────────────────────────
def _quit(client):
    global _connected
    _connected = False
    print(col("\n[✓] Disconnected. Goodbye!", C.GREEN))
    try:
        client.close()
    except Exception:
        pass
    sys.exit(0)

# ── Handshake: password + username ───────────────────────────────────────────
def _handshake(client, password, username_arg):
    # Step 1 — password
    client.sendall(password.encode("utf-8"))
    resp = client.recv(2048).decode("utf-8").strip()
    if resp != "AUTH_OK":
        print(col("[✗] Authentication failed. Wrong server password.", C.RED))
        client.close()
        sys.exit(1)
    print(col("[✓] Authenticated.", C.GREEN))

    # Step 2 — username
    pending = username_arg
    while True:
        if pending:
            name   = pending.strip()
            pending = None  # only use arg once; prompt after if rejected
        else:
            name = input("Username (2-20 chars, letters/numbers/_): ").strip()

        if not name:
            print(col("[!] Username cannot be empty.", C.YELLOW))
            continue

        client.sendall(name.encode("utf-8"))
        resp = client.recv(2048).decode("utf-8").strip()

        if resp == "USERNAME_OK":
            print(col(f"[✓] Welcome, {name}!", C.GREEN))
            return name
        elif resp == "USERNAME_TAKEN":
            print(col("[!] That username is already taken. Choose another.", C.YELLOW))
        elif resp == "USERNAME_INVALID":
            print(col("[!] Invalid username. Use 2-20 alphanumeric characters or underscores.", C.YELLOW))
        else:
            print(col(f"[✗] Unexpected server response: {resp}", C.RED))
            client.close()
            sys.exit(1)

# ── Argument parser ───────────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(
        prog="chat-connect",
        description="Chat-Connect  —  CLI chat client  (by Prajjwal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python clinet.py\n"
            "  python clinet.py --host 192.168.1.10 --port 9090 --username Alice\n"
            "  python clinet.py --no-color\n"
        ),
    )
    p.add_argument("--host",     default="127.0.0.1",  metavar="ADDR",
                   help="Server address (default: 127.0.0.1)")
    p.add_argument("--port",     default=57815, type=int, metavar="PORT",
                   help="Server port (default: 57815)")
    p.add_argument("--password", default=None,          metavar="PASS",
                   help="Server password (prompted securely if omitted)")
    p.add_argument("--username", default=None,          metavar="NAME",
                   help="Your chat username (prompted if omitted)")
    p.add_argument("--no-color", action="store_true",
                   help="Disable colored terminal output")
    p.add_argument("--version",  action="version",
                   version=f"Chat-Connect v{__version__} by {__author__}")
    return p.parse_args()

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    global _use_color

    args       = _parse_args()
    _use_color = not args.no_color

    _clear()
    print(col(WATERMARK, C.CYAN))

    # Securely prompt for password if not supplied via flag
    password = args.password or getpass.getpass("Server password: ")

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((args.host, args.port))
        print(col(f"[✓] Connected to {args.host}:{args.port}", C.GREEN))
    except ConnectionRefusedError:
        print(col(f"[✗] Connection refused — is the server running at {args.host}:{args.port}?", C.RED))
        sys.exit(1)
    except Exception as e:
        print(col(f"[✗] Cannot connect: {e}", C.RED))
        sys.exit(1)

    signal.signal(signal.SIGINT, lambda s, f: _quit(client))

    _handshake(client, password, args.username)

    print(col("─" * 54, C.DIM))
    print(col("  Type /help for commands  •  /quit to exit", C.DIM))
    print(col("─" * 54, C.DIM))

    threading.Thread(target=_recv_loop, args=(client,), daemon=True).start()
    _send_loop(client)


if __name__ == "__main__":
    main()
