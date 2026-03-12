# =============================================================
#   Chat-Connect — TCP Chat Application
#   Original Creator : Prajjwal
#   © 2025  All Rights Reserved.
#   Unauthorized copying or redistribution is strictly prohibited.
# =============================================================
"""
Chat-Connect Server
===================
Multi-client TCP chat server with authentication, rate-limiting,
colored structured logging, graceful shutdown, and full CLI support.

Usage:
    python server.py [OPTIONS]

Options:
    --host HOST         Bind address        (default: 127.0.0.1)
    --port PORT         Port number         (default: 57815)
    --password PASS     Server password     (default: prajjwal@chat)
    --limit N           Max connections     (default: 5)
    --log FILE          Also write logs to FILE
    --no-color          Disable colored output
    --version           Show version and exit
"""

import socket
import threading
import time
import re
import logging
import signal
import sys
import argparse
from datetime import datetime

__version__ = "1.0.0"
__author__  = "Prajjwal"

# ── Watermark ─────────────────────────────────────────────────────────────────
WATERMARK = """
╔══════════════════════════════════════════════════════╗
║            C H A T - C O N N E C T                  ║
║         ──────────────────────────────               ║
║         Original Creator : Prajjwal                  ║
║         © 2025  All Rights Reserved                  ║
║  Unauthorized copying is strictly prohibited.        ║
╚══════════════════════════════════════════════════════╝
"""

# ── ANSI color codes ──────────────────────────────────────────────────────────
class Color:
    RESET    = "\033[0m"
    RED      = "\033[91m"
    GREEN    = "\033[92m"
    YELLOW   = "\033[93m"
    CYAN     = "\033[96m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"

_use_color = True  # toggled by --no-color

def colorize(text, *codes):
    if not _use_color:
        return text
    return "".join(codes) + text + Color.RESET

# ── Colored console log formatter ─────────────────────────────────────────────
class _ColorFormatter(logging.Formatter):
    _MAP = {
        logging.DEBUG:    Color.DIM,
        logging.INFO:     Color.GREEN,
        logging.WARNING:  Color.YELLOW,
        logging.ERROR:    Color.RED,
        logging.CRITICAL: Color.RED + Color.BOLD,
    }
    def format(self, record):
        msg = super().format(record)
        if _use_color:
            return self._MAP.get(record.levelno, "") + msg + Color.RESET
        return msg

def _build_logger(log_file=None):
    logger = logging.getLogger("chat_server")
    logger.setLevel(logging.DEBUG)
    fmt = "%(asctime)s  %(levelname)-8s  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_ColorFormatter(fmt, datefmt=datefmt))
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        logger.addHandler(fh)

    return logger

# ── Security constants (values set from CLI args at startup) ──────────────────
MAX_MSG_LENGTH   = 500
RATE_LIMIT_SEC   = 1.0
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{2,20}$')

# ── Shared state ──────────────────────────────────────────────────────────────
_active_clients  = []           # list of (username, socket)
_clients_lock    = threading.Lock()
_last_msg_time   = {}           # socket.fileno() -> last-message monotonic time
_shutdown_event  = threading.Event()
log              = None         # assigned in main()

# ── Timestamp helper ──────────────────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M")

# ── Low-level send ────────────────────────────────────────────────────────────
def _send(sock, message):
    try:
        sock.sendall(message.encode("utf-8"))
    except Exception as e:
        log.debug(f"Send failed: {e}")

# ── Broadcast ─────────────────────────────────────────────────────────────────
def _broadcast(message, exclude=None):
    with _clients_lock:
        targets = [(u, s) for u, s in _active_clients if s != exclude]
    for _, sock in targets:
        _send(sock, message)

# ── Remove a client from the active list ─────────────────────────────────────
def _remove(username, sock):
    with _clients_lock:
        _active_clients[:] = [(u, s) for u, s in _active_clients if s != sock]
    _last_msg_time.pop(sock.fileno(), None)
    try:
        sock.close()
    except Exception:
        pass

# ── Online user list ──────────────────────────────────────────────────────────
def _online_users():
    with _clients_lock:
        return [u for u, _ in _active_clients]

# ── Per-client message loop ───────────────────────────────────────────────────
def _message_loop(username, client):
    fd = client.fileno()

    while not _shutdown_event.is_set():
        try:
            raw = client.recv(2048)
        except Exception:
            break

        if not raw:
            break

        text = raw.decode("utf-8").strip()
        if not text:
            continue

        # ── Rate limiting ─────────────────────────────────────────────────────
        now  = time.monotonic()
        last = _last_msg_time.get(fd, 0)
        if now - last < RATE_LIMIT_SEC:
            _send(client, "SYS:Slow down! You are sending messages too fast.")
            continue
        _last_msg_time[fd] = now

        # ── Slash commands from client ────────────────────────────────────────
        if text.startswith("CMD:"):
            cmd = text[4:].strip().upper()
            if cmd == "LIST":
                users = _online_users()
                _send(client, f"SYS:Online ({len(users)}): {', '.join(users)}")
            continue

        # ── Message length cap ────────────────────────────────────────────────
        if len(text) > MAX_MSG_LENGTH:
            _send(client, f"SYS:Message too long (max {MAX_MSG_LENGTH} chars).")
            continue

        # ── Broadcast to everyone else ────────────────────────────────────────
        log.info(f"{username}: {text}")
        _broadcast(f"MSG:{_ts()}:{username}:{text}", exclude=client)

    log.info(f"{username} disconnected.")
    _remove(username, client)
    _broadcast(f"SYS:{_ts()}:*** {username} has left the chat ***")

# ── Client handshake (password + username) ────────────────────────────────────
def _handshake(client, server_password):
    # Step 1 — password
    try:
        pw = client.recv(2048).decode("utf-8").strip()
        if pw != server_password:
            _send(client, "AUTH_FAIL")
            log.warning(f"Rejected wrong password from {client.getpeername()}")
            client.close()
            return None
        _send(client, "AUTH_OK")
        log.info(f"Authenticated {client.getpeername()}")
    except Exception as e:
        log.error(f"Auth error: {e}")
        client.close()
        return None

    # Step 2 — username
    while True:
        try:
            name = client.recv(2048).decode("utf-8").strip()
        except Exception as e:
            log.error(f"Username recv error: {e}")
            client.close()
            return None

        if not name:
            _send(client, "USERNAME_EMPTY")
            continue
        if not USERNAME_PATTERN.match(name):
            _send(client, "USERNAME_INVALID")
            continue
        with _clients_lock:
            if any(u.lower() == name.lower() for u, _ in _active_clients):
                _send(client, "USERNAME_TAKEN")
                continue
            _active_clients.append((name, client))
        _send(client, "USERNAME_OK")
        log.info(f"{name} joined the chat.  Active users: {len(_active_clients)}")
        return name

# ── Thread entry point for each new connection ────────────────────────────────
def _client_thread(client, server_password):
    username = _handshake(client, server_password)
    if username is None:
        return
    _broadcast(f"SYS:{_ts()}:*** {username} has joined the chat ***", exclude=client)
    _message_loop(username, client)

# ── Graceful shutdown ─────────────────────────────────────────────────────────
def _shutdown(server_sock, *_):
    log.info("Shutting down — notifying all clients…")
    _shutdown_event.set()
    _broadcast("SYS:Server is shutting down. Goodbye!")
    with _clients_lock:
        for _, sock in _active_clients:
            try:
                sock.close()
            except Exception:
                pass
    try:
        server_sock.close()
    except Exception:
        pass
    log.info("Server stopped.")
    sys.exit(0)

# ── CLI argument parser ───────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(
        prog="chat-connect-server",
        description="Chat-Connect  —  TCP chat server  (by Prajjwal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python server.py\n"
            "  python server.py --port 9090 --password s3cr3t --limit 10\n"
            "  python server.py --host 0.0.0.0 --log server.log\n"
        ),
    )
    p.add_argument("--host",     default="127.0.0.1",    metavar="ADDR",
                   help="Bind address (default: 127.0.0.1)")
    p.add_argument("--port",     default=57815, type=int, metavar="PORT",
                   help="Port number (default: 57815)")
    p.add_argument("--password", default="prajjwal@chat", metavar="PASS",
                   help="Server password clients must supply (default: prajjwal@chat)")
    p.add_argument("--limit",    default=5, type=int,    metavar="N",
                   help="Max simultaneous connections (default: 5)")
    p.add_argument("--log",      default=None,           metavar="FILE",
                   help="Also write structured logs to FILE")
    p.add_argument("--no-color", action="store_true",
                   help="Disable colored terminal output")
    p.add_argument("--version",  action="version",
                   version=f"Chat-Connect v{__version__} by {__author__}")
    return p.parse_args()

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    global _use_color, log

    args     = _parse_args()
    _use_color = not args.no_color
    log      = _build_logger(args.log)

    print(WATERMARK)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    signal.signal(signal.SIGINT,  lambda s, f: _shutdown(server, s, f))
    signal.signal(signal.SIGTERM, lambda s, f: _shutdown(server, s, f))

    try:
        server.bind((args.host, args.port))
    except OSError as e:
        log.critical(f"Cannot bind to {args.host}:{args.port} — {e}")
        sys.exit(1)

    server.listen(args.limit)
    log.info(f"Listening on {args.host}:{args.port}  (max clients: {args.limit})")
    log.info(f"Password protection: {'enabled' if args.password else 'disabled'}")
    if args.log:
        log.info(f"Logging to file: {args.log}")
    log.info("Press Ctrl+C to stop.\n")

    while not _shutdown_event.is_set():
        try:
            client, address = server.accept()
            log.info(f"New connection from {address[0]}:{address[1]}")
            threading.Thread(
                target=_client_thread,
                args=(client, args.password),
                daemon=True,
            ).start()
        except OSError:
            break
        except Exception as e:
            log.error(f"Accept error: {e}")


if __name__ == "__main__":
    main()
