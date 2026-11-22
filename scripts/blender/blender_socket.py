"""
Run Python inside an open Blender session through the Blender MCP add-on's socket, without an MCP client.

  python3 blender_socket.py snippet.py            run a file; prints the 'result' dict it sets
  python3 blender_socket.py -c "result = {'n': len(bpy.data.objects)}"

The add-on listens on 127.0.0.1:9876 (default). Protocol: send JSON {"type": "execute", "code": <python>,
"strict_json": false} followed by a NUL byte; read until a trailing NUL and parse the JSON reply. The code must
set a dict named `result`. Other MCP add-ons use other message types: check yours (e.g. "execute_code").

Use it for small things in the session the user is looking at (select, frame, render one view). Do builds and
exports headless (`blender -b ... --python`), never in the open session: someone may be working in it, and a
long script freezes the UI.
"""

import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9876


def run(code, host=HOST, port=PORT, timeout=600):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(json.dumps({"type": "execute", "code": code, "strict_json": False}).encode() + b"\0")
        buf = b""
        while not buf.endswith(b"\0"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.rstrip(b"\0").decode())


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "-c":
        src = sys.argv[2]
    elif len(sys.argv) >= 2:
        src = open(sys.argv[1]).read()
    else:
        sys.exit(__doc__)
    print(json.dumps(run(src), indent=1))
