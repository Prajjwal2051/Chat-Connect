# =============================================================
#   Chat-Connect — TCP Chat Application
#   Original Creator : Prajjwal
#   © 2025  All Rights Reserved.
#   Unauthorized copying or redistribution is strictly prohibited.
# =============================================================
"""
Chat-Connect Client v2.0.0
===========================
Advanced CLI chat client with rooms, DMs, /me, auto-reconnect, and more.

New in v2.0.0:
  • Rooms/channels     — /join <room>, /rooms
  • Private messages   — /msg <user> <text>
  • /me actions        — * Alice waves *
  • Server stats       — /stats
  • Input history      — ↑/↓ arrows (via readline)
  • Auto-reconnect     — exponential back-off (--no-reconnect to disable)
  • @mention highlight — your name glows in messages
  • Dynamic prompt     — [#general] You:
  • Heartbeat keepalive

Usage:
    python clinet.py [OPTIONS]

Slash commands:
    /help              Show this help
    /list              Users in your current room
    /listall           All online users
    /rooms             All rooms with member counts
    /join <room>       Join or create a room
    /msg <user> <txt>  Send a private message
    /me <text>         Action message (* Alice waves *)
    /stats             Server statistics
    /clear             Clear the screen
    /quit              Disconnect and exit
"""

import socket
import threading
import sys
import os
import signal
import argparse
import getpass
import time
from datetime import datetime

try:
    import readline as _rl
    _rl.set_history_length(500)
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False

__version__ = "2.0.0"
__author__  = "Prajjwal"

# ── Watermark ─────────────────────────────────────────────────────────────────
WATERMARK = """
╔══════════════════════════════════════════════════════╗
║            C H A T - C O N N E C T                  ║
║                    v 2 . 0 . 0                       ║
║         ──────────────────────────────               ║
║         Original Creator : Prajjwal                  ║
║         © 2025  All Rights Reserved                  ║
║  Unauthorized copying is strictly prohibited.        ║
╚══════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
  /help              Show this help
  /list              Users in your current room
  /listall           All online users
  /rooms             All rooms with member counts
  /join <room>       Join or create a room
  /msg <user> <txt>  Send a private message
  /me <text>         Action message  (* Alice waves *)
  /stats             Server statistics (uptime, users, messages)
  /clear             Clear the screen
  /quit              Disconnect and exit
"""

# ── ANSI colors ───────────────────────────────────────────────────────────────
class C:
    RESET    = "\033[0m"
    RED      = "\033[91m"
    GREEN    = "\033[92m"
    YELLOW   = "\033[93m"
    BLUE     = "\033[94m"
    MAGENTA  = "\033[95m"
    CYAN     = "\033[96m"
    WHITE    = "\033[97m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"
    ITALIC   = "\033[3m"
    BG_BLACK = "\033[40m"

_use_color = True
_username  = ""        # own username — set after handshake
_cur_room  = "general" # current room — updated on SYS messages

def col(text, *codes):
    if not _use_color:
        return text
    return "".join(codes) + text + C.RESET

# ── Shared state ──────────────────────────────────────────────────────────────
_connected  = True
_print_lock = threading.Lock()

# ── Low-level send ────────────────────────────────────────────────────────────
def _sendmsg(client, text: str):
    global _connected
    try:
        client.sendall((text + "\n").encode("utf-8"))
    except Exception:
        _print_line(col("[✗] Send failed — connection lost.", C.RED))
        _connected = False

# ── Display helpers ───────────────────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M")

def _clear():
    os.system("cls" if os.name == "nt" else "clear")

def _prompt():
    if _use_color:
        return f"{C.DIM}[#{_cur_room}]{C.RESET} {C.BOLD}You:{C.RESET} "
    return f"[#{_cur_room}] You: "

def _print_line(rendered: str):
    """Erase the current input line, print a message, reprint the prompt."""
    with _print_lock:
        sys.stdout.write(f"\r\033[K{rendered}\n")
        sys.stdout.write(_prompt())
        sys.stdout.flush()

def _highlight_mention(text: str) -> str:
    if _username and f"@{_username}" in text:
        return text.replace(f"@{_username}",
                            col(f"@{_username}", C.BG_BLACK, C.YELLOW, C.BOLD))
    return text

# ── Message renderer ──────────────────────────────────────────────────────────
def _render(raw: str):
    """Return a color-formatted display line, or None to skip."""
    if raw.startswith("MSG:"):
        # MSG:HH:MM:room:sender:content
        parts = raw.split(":", 5)
        if len(parts) == 6:
            _, hh, mm, room, sender, content = parts
            content  = _highlight_mention(content)
            time_str = col(f"[{hh}:{mm}]", C.DIM)
            room_str = col(f"#{room}", C.DIM)
            name_str = col(sender, C.GREEN, C.BOLD) if sender == _username \
                       else col(sender, C.CYAN, C.BOLD)
            return f"{time_str} {room_str} {name_str}{col(':', C.DIM)} {content}"

    elif raw.startswith("DM:"):
        # DM:HH:MM:sender_or_→target:content
        parts = raw.split(":", 4)
        if len(parts) == 5:
            _, hh, mm, sender, content = parts
            content  = _highlight_mention(content)
            time_str = col(f"[{hh}:{mm}]", C.DIM)
            if sender.startswith("→"):
                label = col(f"DM → {sender[1:]}", C.MAGENTA, C.BOLD)
            else:
                label = col(f"DM ✉  {sender}", C.MAGENTA, C.BOLD)
            return f"{time_str} {label}{col(':', C.DIM)} {content}"

    elif raw.startswith("ACTION:"):
        # ACTION:HH:MM:room:username:text
        parts = raw.split(":", 5)
        if len(parts) == 6:
            _, hh, mm, _, uname, text = parts
            return (col(f"[{hh}:{mm}]", C.DIM) + " " +
                    col(f"* {uname} {text}", C.ITALIC, C.YELLOW))

    elif raw.startswith("SYS:"):
        body  = raw[4:]
        parts = body.split(":", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            return col(f"[{parts[0]}:{parts[1]}]", C.DIM) + " " + col(parts[2], C.YELLOW)
        return col(f"  {body}", C.YELLOW)

    elif raw in ("PING", "PONG"):
        return None   # handled silently

    return col(f"  {raw}", C.DIM)

# ── Receive loop (background thread) ─────────────────────────────────────────
def _recv_loop(client, initial_buf: str = ""):
    global _connected, _cur_room
    buf = initial_buf
    while _connected:
        try:
            chunk = client.recv(4096).decode("utf-8")
        except Exception:
            if _connected:
                _print_line(col("[✗] Lost connection to server.", C.RED))
            break
        if not chunk:
            _print_line(col("[✗] Server closed the connection.", C.RED))
            break
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            # Respond to server heartbeat
            if line == "PING":
                try: client.sendall("PONG\n".encode("utf-8"))
                except Exception: pass
                continue
            # Track current room changes
            if "You are now in #" in line:
                _cur_room = line.split("You are now in #", 1)[1].strip()
            rendered = _render(line)
            if rendered:
                _print_line(rendered)
    _connected = False

# ── Send loop (main thread) ───────────────────────────────────────────────────
def _send_loop(client):
    global _connected, _cur_room
    while _connected:
        try:
            with _print_lock:
                sys.stdout.write(_prompt())
                sys.stdout.flush()
            line = sys.stdin.readline()
        except (EOFError, KeyboardInterrupt):
            _quit(client)
            return
        if line is None:
            break
        msg   = line.rstrip("\n").rstrip("\r").strip()
        words = msg.split()
        low   = msg.lower()
        if not msg:
            continue

        if   low == "/quit":            _quit(client);  return
        elif low == "/help":            print(col(HELP_TEXT, C.CYAN))
        elif low == "/clear":           _clear(); print(col(WATERMARK, C.CYAN))
        elif low == "/list":            _sendmsg(client, "CMD:LIST")
        elif low == "/listall":         _sendmsg(client, "CMD:LISTALL")
        elif low == "/rooms":           _sendmsg(client, "CMD:LISTROOMS")
        elif low == "/stats":           _sendmsg(client, "CMD:STATS")
        elif low.startswith("/join"):
            if len(words) >= 2:
                _sendmsg(client, f"CMD:JOIN:{words[1].lstrip('#')}")
            else:
                _print_line(col("[!] Usage: /join <room>", C.YELLOW))
        elif low.startswith("/msg"):
            if len(words) >= 3:
                _sendmsg(client, f"DM:{words[1]}:{' '.join(words[2:])}")
            else:
                _print_line(col("[!] Usage: /msg <username> <message>", C.YELLOW))
        elif low.startswith("/me"):
            action = msg[3:].strip()
            if action:
                _sendmsg(client, f"ME:{action}")
            else:
                _print_line(col("[!] Usage: /me <action>", C.YELLOW))
        elif msg.startswith("/"):
            _print_line(col(f"[!] Unknown command '{words[0]}'. Type /help.", C.YELLOW))
        else:
            _sendmsg(client, msg)

# ── Keepalive thread ──────────────────────────────────────────────────────────
def _keepalive(client):
    """Send CMD:PING every 25 s to keep the connection alive."""
    while _connected:
        time.sleep(25)
        if _connected:
            try: client.sendall("CMD:PING\n".encode("utf-8"))
            except Exception: break

# ── Clean exit ────────────────────────────────────────────────────────────────
def _quit(client):
    global _connected
    _connected = False
    print(col("\n[✓] Disconnected. Goodbye!", C.GREEN))
    try: client.close()
    except Exception: pass
    sys.exit(0)

# ── Handshake ─────────────────────────────────────────────────────────────────
def _handshake(client, password: str, username_arg):
    """Returns (username, leftover_buf) on success."""
    global _username
    buf = ""

    def _readline():
        nonlocal buf
        while "\n" not in buf:
            chunk = client.recv(2048).decode("utf-8")
            if not chunk:
                raise ConnectionError("Server disconnected during handshake")
            buf += chunk
        line, buf = buf.split("\n", 1)
        return line.strip()

    # Step 1 — password
    client.sendall((password + "\n").encode("utf-8"))
    resp = _readline()
    if resp != "AUTH_OK":
        print(col("[✗] Authentication failed. Wrong server password.", C.RED))
        client.close();  sys.exit(1)
    print(col("[✓] Authenticated.", C.GREEN))

    # Step 2 — username
    pending = username_arg
    while True:
        if pending:
            name    = pending.strip()
            pending = None
        else:
            name = input("Username (2-20 chars, letters/numbers/_): ").strip()
        if not name:
            print(col("[!] Username cannot be empty.", C.YELLOW));  continue
        client.sendall((name + "\n").encode("utf-8"))
        resp = _readline()
        if resp == "USERNAME_OK":
            print(col(f"[✓] Welcome, {name}!", C.GREEN))
            _username = name
            return name, buf
        elif resp == "USERNAME_TAKEN":
            print(col("[!] That username is already taken. Choose another.", C.YELLOW))
        elif resp == "USERNAME_INVALID":
            print(col("[!] Invalid. Use 2-20 alphanumeric chars or underscores.", C.YELLOW))
        else:
            print(col(f"[✗] Unexpected response: {resp}", C.RED))
            client.close();  sys.exit(1)

# ── Connect with exponential back-off ─────────────────────────────────────────
def _connect(host: str, port: int, no_reconnect: bool):
    delay = 1;  attempt = 0
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            return sock
        except ConnectionRefusedError:
            if no_reconnect:
                print(col(f"[✗] Connection refused — is the server running at {host}:{port}?", C.RED))
                sys.exit(1)
            attempt += 1
            delay = min(delay * 2, 30)
            print(col(f"[↺] Retrying in {delay}s…  (attempt {attempt})", C.YELLOW))
            time.sleep(delay)
        except Exception as e:
            print(col(f"[✗] Cannot connect: {e}", C.RED));  sys.exit(1)

# ── Argument parser ───────────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(
        prog="chat-connect",
        description="Chat-Connect v2.0.0  —  Advanced CLI chat client  (by Prajjwal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python clinet.py\n"
            "  python clinet.py --host 192.168.1.10 --port 9090 --username Alice\n"
            "  python clinet.py --no-reconnect --no-color\n"
        ),
    )
    p.add_argument("--host",         default="127.0.0.1",  metavar="ADDR",
                   help="Server address (default: 127.0.0.1)")
    p.add_argument("--port",         default=57815, type=int, metavar="PORT",
                   help="Server port (default: 57815)")
    p.add_argument("--password",     default=None,          metavar="PASS",
                   help="Server password (prompted securely if omitted)")
    p.add_argument("--username",     default=None,          metavar="NAME",
                   help="Your chat username (prompted if omitted)")
    p.add_argument("--no-reconnect", action="store_true",
                   help="Exit instead of retrying on connection failure")
    p.add_argument("--no-color",     action="store_true",
                   help="Disable ANSI color output")
    p.add_argument("--version",      action="version",
                   version=f"Chat-Connect v{__version__} by {__author__}")
    return p.parse_args()

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    global _use_color, _connected, _cur_room

    args       = _parse_args()
    _use_color = not args.no_color

    _clear()
    print(col(WATERMARK, C.CYAN))

    password = args.password or getpass.getpass("Server password: ")

    print(col(f"[→] Connecting to {args.host}:{args.port}…", C.DIM))
    client = _connect(args.host, args.port, args.no_reconnect)
    print(col(f"[✓] Connected to {args.host}:{args.port}", C.GREEN))

    signal.signal(signal.SIGINT, lambda s, f: _quit(client))

    _, leftover = _handshake(client, password, args.username)

    print(col("─" * 56, C.DIM))
    print(col("  Type /help for commands  •  /quit to exit", C.DIM))
    if _HAS_READLINE:
        print(col("  ↑/↓ arrows for input history", C.DIM))
    print(col("─" * 56, C.DIM))

    threading.Thread(target=_recv_loop,  args=(client, leftover), daemon=True).start()
    threading.Thread(target=_keepalive,  args=(client,),           daemon=True).start()
    _send_loop(client)


if __name__ == "__main__":
    main()


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


