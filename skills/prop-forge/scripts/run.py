#!/usr/bin/env python3
"""run: start headless Blender on a script and print only its result lines (plain Python 3).

  python run.py SCRIPT.py [-- script args]      e.g. python run.py review.py -- prop.glb --out sheet.png
  python run.py --which                         the Blender it would use

Finds Blender from $BLENDER_EXE, then PATH, then the usual install folders (newest version wins). Scripts named
without a folder are looked up beside this file. Prints the script's @@JSON@@ lines without the marker; when the
script fails and printed none, the last lines of Blender's output. Exit code 0 ok, 1 failed, 2 no Blender.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

MARK = "@@JSON@@"
HERE = os.path.dirname(os.path.abspath(__file__))


def blender():
    env = os.environ.get("BLENDER_EXE")
    if env and os.path.isfile(env):
        return env
    hit = shutil.which("blender")
    if hit:
        return hit
    pats = {"win32": [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                      os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
                      r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"],
            "darwin": ["/Applications/Blender*.app/Contents/MacOS/Blender"]}.get(
        sys.platform, ["/usr/bin/blender", "/opt/blender*/blender", "/snap/bin/blender",
                       os.path.expanduser("~/blender*/blender")])
    found = [p for pat in pats for p in glob.glob(pat) if os.path.isfile(p)]

    def ver(p):
        m = re.search(r"(\d+)\.(\d+)", p)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return max(found, key=ver) if found else None


def main():
    a = sys.argv[1:]
    exe = blender()
    if not exe:
        print('{"ok": false, "error": "Blender not found; set BLENDER_EXE"}')
        return 2
    if a[:1] == ["--which"]:
        print(exe)
        return 0
    if not a:
        print(__doc__)
        return 1
    script, rest = a[0], a[1:]
    if not os.path.exists(script) and os.path.exists(os.path.join(HERE, script)):
        script = os.path.join(HERE, script)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "1", "-P", script, "--"] + rest
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = [ln[len(MARK):] for ln in p.stdout.splitlines() if ln.startswith(MARK)]
    for ln in out:
        print(ln)
    if p.returncode != 0 and not out:
        tail = (p.stdout + "\n" + p.stderr).strip().splitlines()[-25:]
        print("\n".join(tail))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
