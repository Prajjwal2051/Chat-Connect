# =============================================================
#   Chat-Connect — TCP Chat Application
#   Original Creator : Prajjwal
#   © 2025  All Rights Reserved.
#   Unauthorized copying or redistribution is strictly prohibited.
# =============================================================
"""
Chat-Connect Server v2.0.0
==========================
Advanced multi-client TCP chat server with rooms, private messaging,
message history, admin controls, heartbeat, and per-IP limits.

New in v2.0.0:
  • Rooms/channels    — /join <room>, default #general
  • Private messages  — /msg <user> <text> routed server-side
  • /me actions       — * Alice waves *
  • Message history   — last N msgs replayed on room join
  • Admin commands    — /kick, /ban, /unban, /broadcast
  • Server stats      — /stats (uptime, users, messages)
  • Heartbeat         — dead-connection cleanup every 30 s
  • Per-IP limits     — --max-per-ip flag

Usage:
    python server.py [OPTIONS]

Options:
    --host HOST         Bind address          (default: 127.0.0.1)
    --port PORT         Port number           (default: 57815)
    --password PASS     Server password       (default: prajjwal@chat)
    --limit N           Max total connections (default: 10)
    --max-per-ip N      Max per-IP connects   (default: 3)
    --history N         History messages      (default: 20)
    --log FILE          Write logs to FILE
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
from collections import deque
from dataclasses import dataclass, field

__version__ = "2.0.0"
__author__  = "Prajjwal"

# ── Watermark ─────────────────────────────────────────────────────────────────
WATERMARK = """
╔══════════════════════════════════════════════════════╗
║            C H A T - C O N N E C T                   ║
║                    v 2 . 0 . 0                       ║
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

# ── Colored log formatter ─────────────────────────────────────────────────────
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
    logger  = logging.getLogger("chat_server")
    logger.setLevel(logging.DEBUG)
    fmt     = "%(asctime)s  %(levelname)-8s  %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_ColorFormatter(fmt, datefmt=datefmt))
    logger.addHandler(ch)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
        logger.addHandler(fh)
    return logger

# ── Security ──────────────────────────────────────────────────────────────────
MAX_MSG_LENGTH   = 500
RATE_LIMIT_SEC   = 1.0
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{2,20}$')
DEFAULT_ROOM     = "general"

# ── Per-user data ─────────────────────────────────────────────────────────────
@dataclass
class User:
    username:  str
    sock:      object
    ip:        str
    room:      str   = DEFAULT_ROOM
    join_time: float = field(default_factory=time.monotonic)
    msg_count: int   = 0
    last_msg:  float = 0.0

# ── Global state ──────────────────────────────────────────────────────────────
_users:       dict  = {}                               # username -> User
_rooms:       dict  = {DEFAULT_ROOM: set()}            # room -> set of usernames
_history:     dict  = {DEFAULT_ROOM: deque(maxlen=20)} # room -> deque of MSG strings
_ip_count:    dict  = {}                               # ip -> int
_banned_ips:  set   = set()
_state_lock         = threading.Lock()
_shutdown_event     = threading.Event()
_start_time:  float = 0.0
_total_msgs:  int   = 0
log                 = None  # set in main()

# ── Helpers ──────────────────────────────────────────────────────────────────
def _ts():
    return datetime.now().strftime("%H:%M")

def _send(sock, message: str):
    """Send a newline-terminated message."""
    try:
        sock.sendall((message + "\n").encode("utf-8"))
    except Exception:
        pass

def _broadcast_room(room: str, message: str, exclude=None):
    with _state_lock:
        members = [u for u in _rooms.get(room, set()) if u != exclude]
        targets  = {u: _users[u].sock for u in members if u in _users}
    for sock in targets.values():
        _send(sock, message)

def _broadcast_all(message: str):
    with _state_lock:
        socks = [u.sock for u in _users.values()]
    for sock in socks:
        _send(sock, message)

def _remove_user(username: str):
    with _state_lock:
        user = _users.pop(username, None)
        if user:
            _rooms.get(user.room, set()).discard(username)
            _ip_count[user.ip] = max(0, _ip_count.get(user.ip, 1) - 1)
            try:
                user.sock.close()
            except Exception:
                pass
    return user

def _online_in_room(room: str):
    with _state_lock:
        return sorted(_rooms.get(room, set()))

def _all_online():
    with _state_lock:
        return sorted(_users.keys())

# ── Room join ──────────────────────────────────────────────────────────────────
def _join_room(user: User, new_room: str, history_count: int):
    old_room = user.room
    with _state_lock:
        _rooms.get(old_room, set()).discard(user.username)
        if new_room not in _rooms:
            _rooms[new_room]   = set()
            _history[new_room] = deque(maxlen=20)
        _rooms[new_room].add(user.username)
        user.room = new_room
        hist = list(_history[new_room])[-history_count:]
    if old_room != new_room:
        _broadcast_room(old_room, f"SYS:{_ts()}:*** {user.username} left #{old_room} ***")
    if hist:
        _send(user.sock, f"SYS:{_ts()}:--- Last {len(hist)} messages in #{new_room} ---")
        for h in hist:
            _send(user.sock, h)
        _send(user.sock, f"SYS:{_ts()}:--- End of history ---")
    _send(user.sock, f"SYS:{_ts()}:You are now in #{new_room}")
    _broadcast_room(new_room, f"SYS:{_ts()}:*** {user.username} joined #{new_room} ***",
                    exclude=user.username)

# ── Command dispatcher ───────────────────────────────────────────────────────────
def _handle_cmd(user: User, raw: str, history_count: int):
    """Handle CMD:<verb>[:<args>] packets from the client."""
    parts = raw.split(":", 2)
    verb  = parts[1].strip().upper() if len(parts) > 1 else ""
    args  = parts[2].strip()        if len(parts) > 2 else ""

    if verb == "LIST":
        members = _online_in_room(user.room)
        _send(user.sock,
              f"SYS:{_ts()}:Online in #{user.room} ({len(members)}): {', '.join(members)}")
    elif verb == "LISTALL":
        everyone = _all_online()
        _send(user.sock,
              f"SYS:{_ts()}:All online ({len(everyone)}): {', '.join(everyone)}")
    elif verb == "LISTROOMS":
        with _state_lock:
            info = sorted((r, len(m)) for r, m in _rooms.items())
        rooms_str = "  ".join(f"#{r}({n})" for r, n in info)
        _send(user.sock, f"SYS:{_ts()}:Rooms: {rooms_str}")
    elif verb == "JOIN":
        room = re.sub(r'[^A-Za-z0-9_]', '', args)[:20] or DEFAULT_ROOM
        _join_room(user, room, history_count)
    elif verb == "STATS":
        up = int(time.monotonic() - _start_time)
        h, r = divmod(up, 3600); m, s = divmod(r, 60)
        with _state_lock:
            nu = len(_users); nr = len(_rooms)
        _send(user.sock,
              f"SYS:{_ts()}:Server stats — uptime: {h:02d}:{m:02d}:{s:02d}  "
              f"|  users: {nu}  |  rooms: {nr}  |  messages: {_total_msgs}")
    elif verb == "PING":
        _send(user.sock, "PONG")
    elif verb == "KICK":
        target = args.strip()
        with _state_lock:
            tu = _users.get(target)
        if tu:
            _send(tu.sock, "SYS:You have been kicked by an admin.")
            room = tu.room
            _remove_user(target)
            _broadcast_room(room, f"SYS:{_ts()}:*** {target} was kicked ***")
            log.warning(f"KICK: {user.username} kicked {target}")
        else:
            _send(user.sock, f"SYS:{_ts()}:User '{target}' not found.")
    elif verb == "BAN":
        target = args.strip()
        with _state_lock:
            tu = _users.get(target)
        if tu:
            _banned_ips.add(tu.ip)
            _send(tu.sock, "SYS:You have been banned from this server.")
            room = tu.room
            _remove_user(target)
            _broadcast_room(room, f"SYS:{_ts()}:*** {target} was banned ***")
            log.warning(f"BAN: {user.username} banned {target} ({tu.ip})")
        else:
            _send(user.sock, f"SYS:{_ts()}:User '{target}' not found.")
    elif verb == "UNBAN":
        ip = args.strip()
        _banned_ips.discard(ip)
        _send(user.sock, f"SYS:{_ts()}:IP {ip} has been unbanned.")
        log.info(f"UNBAN: {user.username} unbanned {ip}")
    elif verb == "BROADCAST":
        if args:
            _broadcast_all(f"SYS:{_ts()}:[BROADCAST] {args}")
            log.info(f"BROADCAST by {user.username}: {args}")
        else:
            _send(user.sock, "SYS:Usage: /broadcast <message>")
    else:
        _send(user.sock, f"SYS:{_ts()}:Unknown command. Type /help.")

# ── Per-client message loop ─────────────────────────────────────────────────────
def _message_loop(user: User, history_count: int):
    global _total_msgs
    buf = ""
    while not _shutdown_event.is_set():
        try:
            chunk = user.sock.recv(4096).decode("utf-8")
        except Exception:
            break
        if not chunk:
            break
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            text = line.strip()
            if not text:
                continue
            if text.startswith("CMD:"):
                _handle_cmd(user, text, history_count)
                continue
            # DM:<target>:<content>
            if text.startswith("DM:"):
                parts = text.split(":", 2)
                if len(parts) == 3:
                    tgt, content = parts[1].strip(), parts[2].strip()
                    with _state_lock:
                        tu = _users.get(tgt)
                    if tu and content:
                        _send(tu.sock,   f"DM:{_ts()}:{user.username}:{content}")
                        _send(user.sock, f"DM:{_ts()}:→{tgt}:{content}")
                        log.info(f"DM {user.username}→{tgt}: {content}")
                    elif not tu:
                        _send(user.sock, f"SYS:{_ts()}:'{tgt}' is not online.")
                continue
            # ME:<action>
            if text.startswith("ME:"):
                content = text[3:].strip()
                if content and len(content) <= MAX_MSG_LENGTH:
                    pkt = f"ACTION:{_ts()}:{user.room}:{user.username}:{content}"
                    with _state_lock:
                        _history[user.room].append(pkt)
                    _broadcast_room(user.room, pkt)
                continue
            # Rate limit
            now = time.monotonic()
            if now - user.last_msg < RATE_LIMIT_SEC:
                _send(user.sock, f"SYS:{_ts()}:Slow down — wait before sending again.")
                continue
            user.last_msg = now
            # Length cap
            if len(text) > MAX_MSG_LENGTH:
                _send(user.sock, f"SYS:{_ts()}:Message too long (max {MAX_MSG_LENGTH} chars).")
                continue
            # Broadcast to whole room (including sender for consistent timestamped display)
            user.msg_count += 1
            with _state_lock:
                _total_msgs += 1
            pkt = f"MSG:{_ts()}:{user.room}:{user.username}:{text}"
            with _state_lock:
                _history[user.room].append(pkt)
            log.info(f"[#{user.room}] {user.username}: {text}")
            _broadcast_room(user.room, pkt)

    log.info(f"{user.username} disconnected. (sent {user.msg_count} msgs)")
    room = user.room
    _remove_user(user.username)
    _broadcast_room(room, f"SYS:{_ts()}:*** {user.username} has left #{room} ***")

# ── Handshake ──────────────────────────────────────────────────────────────────
def _handshake(client, addr, server_password, max_per_ip, history_count):
    ip  = addr[0]
    buf = ""

    def _readline():
        nonlocal buf
        while "\n" not in buf:
            chunk = client.recv(2048).decode("utf-8")
            if not chunk:
                raise ConnectionError("Client disconnected")
            buf += chunk
        line, buf = buf.split("\n", 1)
        return line.strip()

    if ip in _banned_ips:
        _send(client, "AUTH_FAIL");  log.warning(f"Banned IP rejected: {ip}");  client.close();  return None
    with _state_lock:
        if _ip_count.get(ip, 0) >= max_per_ip:
            _send(client, "AUTH_FAIL");  log.warning(f"IP {ip} over limit");  client.close();  return None

    try:
        pw = _readline()
        if pw != server_password:
            _send(client, "AUTH_FAIL");  log.warning(f"Wrong password from {ip}");  client.close();  return None
        _send(client, "AUTH_OK")
        log.info(f"Authenticated {ip}:{addr[1]}")
    except Exception as e:
        log.error(f"Auth error {ip}: {e}");  client.close();  return None

    while True:
        try:
            name = _readline()
        except Exception as e:
            log.error(f"Username error {ip}: {e}");  client.close();  return None
        if not name:                              _send(client, "USERNAME_EMPTY");  continue
        if not USERNAME_PATTERN.match(name):      _send(client, "USERNAME_INVALID"); continue
        with _state_lock:
            if name.lower() in {u.lower() for u in _users}:
                _send(client, "USERNAME_TAKEN"); continue
            user = User(username=name, sock=client, ip=ip)
            _users[name] = user
            _rooms[DEFAULT_ROOM].add(name)
            _ip_count[ip] = _ip_count.get(ip, 0) + 1
        _send(client, "USERNAME_OK")
        log.info(f"{name} joined.  Active: {len(_users)}")
        with _state_lock:
            hist = list(_history[DEFAULT_ROOM])[-history_count:]
        if hist:
            _send(client, f"SYS:{_ts()}:--- Last {len(hist)} messages in #{DEFAULT_ROOM} ---")
            for h in hist: _send(client, h)
            _send(client, f"SYS:{_ts()}:--- End of history ---")
        return user

# ── Client thread ─────────────────────────────────────────────────────────────────
def _client_thread(client, addr, server_password, max_per_ip, history_count):
    user = _handshake(client, addr, server_password, max_per_ip, history_count)
    if user is None:
        return
    _broadcast_room(DEFAULT_ROOM,
                    f"SYS:{_ts()}:*** {user.username} has joined #{DEFAULT_ROOM} ***",
                    exclude=user.username)
    _message_loop(user, history_count)

# ── Server heartbeat ───────────────────────────────────────────────────────────────
def _heartbeat():
    """Ping all clients every 30 s; prune dead sockets."""
    while not _shutdown_event.is_set():
        time.sleep(30)
        with _state_lock:
            snapshot = list(_users.values())
        for user in snapshot:
            try:
                user.sock.sendall("PING\n".encode("utf-8"))
            except Exception:
                log.info(f"Heartbeat pruned dead connection: {user.username}")
                _remove_user(user.username)

# ── Graceful shutdown ─────────────────────────────────────────────────────────────
def _shutdown(server_sock, *_):
    log.info("Shutting down — notifying all clients…")
    _shutdown_event.set()
    _broadcast_all("SYS:Server is shutting down. Goodbye!")
    with _state_lock:
        for u in list(_users.values()):
            try: u.sock.close()
            except Exception: pass
    try: server_sock.close()
    except Exception: pass
    log.info("Server stopped.")
    sys.exit(0)

# ── CLI argument parser ──────────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(
        prog="chat-connect-server",
        description="Chat-Connect v2.0.0  —  Advanced TCP chat server  (by Prajjwal)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python server.py\n"
            "  python server.py --port 9090 --password s3cr3t --limit 20\n"
            "  python server.py --host 0.0.0.0 --log server.log --history 30\n"
        ),
    )
    p.add_argument("--host",       default="127.0.0.1",    metavar="ADDR",
                   help="Bind address (default: 127.0.0.1)")
    p.add_argument("--port",       default=57815, type=int, metavar="PORT",
                   help="Port number (default: 57815)")
    p.add_argument("--password",   default="prajjwal@chat", metavar="PASS",
                   help="Server password (default: prajjwal@chat)")
    p.add_argument("--limit",      default=10, type=int,   metavar="N",
                   help="Max simultaneous connections (default: 10)")
    p.add_argument("--max-per-ip", default=3,  type=int,   metavar="N",
                   help="Max connections per IP (default: 3)")
    p.add_argument("--history",    default=20, type=int,   metavar="N",
                   help="Messages to replay on room join (default: 20)")
    p.add_argument("--log",        default=None,            metavar="FILE",
                   help="Also write structured logs to FILE")
    p.add_argument("--no-color",   action="store_true",
                   help="Disable colored terminal output")
    p.add_argument("--version",    action="version",
                   version=f"Chat-Connect v{__version__} by {__author__}")
    return p.parse_args()

# ── Entry point ─────────────────────────────────────────────────────────────────
def main():
    global _use_color, log, _start_time

    args        = _parse_args()
    _use_color  = not args.no_color
    log         = _build_logger(args.log)
    _start_time = time.monotonic()

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
    log.info(f"Listening on {args.host}:{args.port}  "
             f"(max: {args.limit}, per-IP: {args.max_per_ip})")
    log.info(f"Default room: #{DEFAULT_ROOM}  |  History: {args.history} msgs/room")
    log.info(f"Password: {'set' if args.password else 'none'}  |  Press Ctrl+C to stop.\n")

    threading.Thread(target=_heartbeat, daemon=True).start()

    while not _shutdown_event.is_set():
        try:
            client, address = server.accept()
            log.info(f"New connection from {address[0]}:{address[1]}")
            threading.Thread(
                target=_client_thread,
                args=(client, address, args.password, args.max_per_ip, args.history),
                daemon=True,
            ).start()
        except OSError:
            break
        except Exception as e:
            log.error(f"Accept error: {e}")


if __name__ == "__main__":
    main()
