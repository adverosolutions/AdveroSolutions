"""Hard network tripwire: any egress off loopback raises and is recorded."""
import socket, atexit, sys
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
BLOCKED = []
def _is_local(addr):
    try:
        host = addr[0] if isinstance(addr, tuple) else addr
    except Exception:
        return False
    if not isinstance(host, str):
        return False
    return host.startswith("127.") or host in ("::1", "localhost", "0.0.0.0", "")
def _guard(self, addr):
    if not _is_local(addr):
        BLOCKED.append(addr)
        raise OSError("NETGUARD blocked egress to %r" % (addr,))
    return _orig_connect(self, addr)
def _guard_ex(self, addr):
    if not _is_local(addr):
        BLOCKED.append(addr)
        raise OSError("NETGUARD blocked egress to %r" % (addr,))
    return _orig_connect_ex(self, addr)
socket.socket.connect = _guard
socket.socket.connect_ex = _guard_ex
@atexit.register
def _report():
    sys.stderr.write("\nNETGUARD: %d blocked egress attempts\n" % len(BLOCKED))
    for a in BLOCKED[:20]:
        sys.stderr.write("  ATTEMPT -> %r\n" % (a,))
