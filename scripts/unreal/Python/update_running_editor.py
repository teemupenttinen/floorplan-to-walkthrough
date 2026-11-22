"""
Update an OPEN editor after a new Blender export: textures, material instance parameters and meshes, without
rebuilding the level (the level keeps its actors; they show the re-imported meshes).

Send it to the editor with:
  python3 scripts/unreal/remote_run.py <abs>/Content/Python/update_running_editor.py
or run it with Tools > Execute Python Script.

New objects, deleted objects, doors, lights and instances need the full import (import_manifest.py) with the
editor closed.
"""

import json
import os
import unreal

_here = (os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals()
         else os.path.join(unreal.Paths.project_content_dir(), "Python"))
g = {"NO_MAIN": True, "__name__": "import_manifest"}
exec(open(os.path.join(_here, "import_manifest.py")).read(), g)


def main():
    man = json.load(open(os.path.join(g["EXPORT"], "manifest.json")))
    tex = g["import_textures"]()
    root = g["ROOT"] + "/Materials/"
    masters = {k: unreal.load_asset(root + n) for k, n in
               (("tex", "M_Textured"), ("flat", "M_Flat"), ("glass", "M_Glass"), ("leaf_tex", "M_LeafTex"))}
    if any(m is None for m in masters.values()):
        g["log"]("master materials missing: run import_manifest.py once with the editor closed")
        return
    # Existing instances are kept; they get their (possibly new) parent and all parameters again.
    mis = g["make_instances"](man.get("materials", {}), masters, tex)
    g["import_meshes"](man.get("meshes", []), mis, g["ROOT"] + "/Meshes")
    g["import_meshes"](man.get("doors", []), mis, g["ROOT"] + "/Doors")
    g["import_meshes"](list(man.get("protos", {}).values()), mis, g["ROOT"] + "/Protos")
    g["log"]("update done")


main()
