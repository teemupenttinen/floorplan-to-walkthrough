"""
Serve a folder (the viewer's web/ output, or the floor picker) on localhost without caching.

  python3 serve.py [folder] [port] [--no-browser]
  python3 serve.py web 8768
  python3 serve.py floorpicker 8770 --no-browser

Browsers kept old model and frame files when the server allowed caching (the file names stay the same
after a new export), so every response says Cache-Control: no-cache. Binds to 127.0.0.1 only.
"""

import http.server
import os
import sys
import webbrowser

args = [a for a in sys.argv[1:] if not a.startswith("--")]
DIR = os.path.abspath(next((a for a in args if not a.isdigit()), os.path.dirname(os.path.abspath(__file__))))
PORT = int(next((a for a in args if a.isdigit()), "8768"))

TYPES = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".ktx2": "image/ktx2", ".wasm": "application/wasm",
         ".webp": "image/webp", ".mp4": "video/mp4", ".json": "application/json", ".js": "text/javascript",
         ".mjs": "text/javascript", ".hdr": "application/octet-stream", ".exr": "application/octet-stream"}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *a):
        if "/frames/" not in self.path:          # frame sequences would flood the log
            super().log_message(fmt, *a)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = "http://localhost:%d/" % PORT
    print("serving", DIR, "on", url)
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
