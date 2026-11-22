"""
Run a Python file inside the OPEN Unreal editor through Python remote execution (localhost only):

  UE_ROOT="/Users/Shared/Epic Games/UE_5.x" python3 scripts/unreal/remote_run.py <abs path to script.py>

Needs, in the project's DefaultEngine.ini (see Config/DefaultEngine.snippet.ini):
  [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
  bRemoteExecution=True
  RemoteExecutionMulticastBindAddress=0.0.0.0

Bind 0.0.0.0, not 127.0.0.1: macOS does not deliver the discovery multicast to a socket bound to the loopback
address, so the client never finds the editor. TTL 0 keeps the traffic on this machine.
"""

import os
import sys
import time

UE_ROOT = os.environ.get("UE_ROOT", "/Users/Shared/Epic Games/UE_5.5")
sys.path.insert(0, os.path.join(UE_ROOT, "Engine", "Plugins", "Experimental", "PythonScriptPlugin", "Content", "Python"))
try:
    import remote_execution as rex
except ImportError:
    sys.exit("remote_execution.py not found under UE_ROOT=%s (set UE_ROOT to the engine folder)" % UE_ROOT)

if len(sys.argv) < 2:
    sys.exit("usage: remote_run.py <script.py>")
path = os.path.abspath(sys.argv[1])

cfg = rex.RemoteExecutionConfig()
cfg.multicast_bind_address = "0.0.0.0"
remote = rex.RemoteExecution(cfg)
remote.start()
for _ in range(50):                     # discovery takes a moment
    if remote.remote_nodes:
        break
    time.sleep(0.2)
if not remote.remote_nodes:
    remote.stop()
    sys.exit("no editor found (is it open, with remote execution on?)")
remote.open_command_connection(remote.remote_nodes[0]["node_id"])
res = remote.run_command(path, exec_mode=rex.MODE_EXEC_FILE, unattended=True)
for line in res.get("output", []):
    print(line.get("output", "").rstrip())
print("success:", res.get("success"), res.get("result", ""))
remote.stop()
sys.exit(0 if res.get("success") else 1)
