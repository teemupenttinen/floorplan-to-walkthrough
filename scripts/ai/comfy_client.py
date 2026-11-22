"""
Minimal ComfyUI API client: upload inputs, queue a graph, wait, download the outputs. No dependencies.

  COMFY=http://127.0.0.1:8188 python3 comfy_client.py graph.json [--out out/]

graph.json is a ComfyUI "API format" graph (Workflow > Export (API) in the ComfyUI menu). Values of the form
"@upload:<local path>" are uploaded first and replaced by the server's file name, so one graph file can carry its
local inputs.

Remote GPU (cloud pod) notes:
- Prefer an SSH tunnel over the provider's HTTP proxy:  ssh -f -N -L 8188:127.0.0.1:8188 root@<pod ip> -p <port>
  then COMFY=http://127.0.0.1:8188. Some HTTP proxies have a ~100 MB upload limit, block non-browser user agents
  (send "curl/8.0") or expose no ports at all.
- If the pod has no SSH server: apt-get install -y openssh-server < /dev/null (commands that read stdin eat the rest
  of a piped script), put your public key in /root/.ssh/authorized_keys, ssh-keygen -A, mkdir -p /run/sshd,
  /usr/sbin/sshd. A container-disk-only pod loses this (and uploaded models) on restart.
- A GPU can get stuck in an "illegal memory access" state after a crash; only a pod restart clears it.

Use it as a library for jobs that build the graph in Python (see h3_job_example.py):
  from comfy_client import Comfy
  c = Comfy()
  name = c.upload("start.png")
  outputs = c.run(graph)
  c.download_all(outputs, "out/", prefix="shot1")
"""

import json
import mimetypes
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid

UA = {"User-Agent": "curl/8.0"}


class Comfy:
    def __init__(self, base=None):
        self.base = (base or os.environ.get("COMFY", "http://127.0.0.1:8188")).rstrip("/")

    def _req(self, path, data=None, headers=None, timeout=120):
        h = dict(UA, **(headers or {}))
        req = urllib.request.Request(self.base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return f.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP %d on %s: %s" % (e.code, path, e.read().decode(errors="replace")[:2000]))

    def api(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        hdr = {"Content-Type": "application/json"} if payload is not None else None
        return json.loads(self._req(path, data, hdr))

    def upload(self, path, subfolder="kit", kind="image"):
        """Upload an image or video into ComfyUI's input folder. Returns the name to use in LoadImage/LoadVideo."""
        boundary = uuid.uuid4().hex
        fname = os.path.basename(path)
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        parts = []
        for k, v in (("subfolder", subfolder), ("overwrite", "true"), ("type", "input")):
            parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                      % (boundary, fname, ctype)).encode() + open(path, "rb").read() + b"\r\n")
        parts.append(("--%s--\r\n" % boundary).encode())
        res = json.loads(self._req("/upload/image", b"".join(parts),
                                   {"Content-Type": "multipart/form-data; boundary=" + boundary}, timeout=600))
        return (res["subfolder"] + "/" + res["name"]) if res.get("subfolder") else res["name"]

    def resolve_uploads(self, graph):
        """Replace "@upload:<path>" values in a graph with uploaded names."""
        for node in graph.values():
            for k, v in list(node.get("inputs", {}).items()):
                if isinstance(v, str) and v.startswith("@upload:"):
                    node["inputs"][k] = self.upload(v[len("@upload:"):])
        return graph

    def run(self, graph, poll=10):
        """Queue a graph and wait. Returns the outputs dict of the history entry."""
        pid = self.api("/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})["prompt_id"]
        print("queued", pid, flush=True)
        t0 = time.time()
        while True:
            time.sleep(poll)
            h = self.api("/history/" + pid)
            if pid in h:
                st = h[pid]["status"]
                if st.get("status_str") == "error":
                    raise RuntimeError(json.dumps(st, indent=1)[:4000])
                if st.get("completed"):
                    print("done in %.0f s" % (time.time() - t0), flush=True)
                    return h[pid]["outputs"]

    def download_all(self, outputs, out_dir, prefix=""):
        """Save every file in the outputs (images, gifs/videos from VideoCombine nodes)."""
        os.makedirs(out_dir, exist_ok=True)
        saved = []
        for node_id, o in outputs.items():
            for key in ("images", "gifs", "videos"):
                for f in o.get(key, []):
                    q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f["subfolder"], "type": f["type"]})
                    dst = os.path.join(out_dir, (prefix + "_" if prefix else "") + f["filename"].split("/")[-1])
                    open(dst, "wb").write(self._req("/view?" + q, timeout=600))
                    saved.append(dst)
                    print("saved", dst)
        return saved


class Graph:
    """Build an API-format graph in Python: g.node(id, "ClassName", input=value, other=[node_ref])."""

    def __init__(self):
        self.g = {}

    def node(self, i, cls, **inputs):
        self.g[str(i)] = {"class_type": cls, "inputs": inputs}
        return [str(i), 0]

    @staticmethod
    def out(ref, index):
        return [ref[0], index]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out_dir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "out"
    c = Comfy()
    graph = c.resolve_uploads(json.load(open(sys.argv[1])))
    c.download_all(c.run(graph), out_dir, prefix=os.path.splitext(os.path.basename(sys.argv[1]))[0])
