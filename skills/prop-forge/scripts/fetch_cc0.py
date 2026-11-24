#!/usr/bin/env python3
"""fetch_cc0: find and download CC0 textures and reference models (plain Python 3, no Blender needed).

  python fetch_cc0.py search WORD [WORD ...] [--models] [--limit 20]
  python fetch_cc0.py texture POLYHAVEN_ID [--res 2k] [--out DIR]
  python fetch_cc0.py model POLYHAVEN_ID [--res 1k] [--out DIR]
  python fetch_cc0.py ambientcg ASSET_ID [--res 2K] [--out DIR]

Sources: Poly Haven (polyhaven.com) and ambientCG (ambientcg.com). Everything they publish is CC0: free for any use,
no attribution needed for the assets. Poly Haven's API terms ask that tools name it as the source, which this
script prints with every result.

`texture` writes DIR/<id>/ with the colour, OpenGL normal and ARM (occlusion, roughness, metal) maps plus info.json,
whose "metres" is the real width one repeat of the photo covers: pass it to forge.pbr(metres=...).
`model` writes DIR/<id>/<id>.gltf with its textures, for use as a measured reference (check.py gives its size,
silhouette.py compares outlines) or, being CC0, as a part.
"""
import argparse
import io
import json
import os
import sys
import urllib.request
import zipfile

UA = {"User-Agent": "prop-forge-skill/0.1"}
PH = "https://api.polyhaven.com"
CREDIT = "Source: Poly Haven (polyhaven.com), CC0"


def get(url, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        data = r.read()
    return data if raw else json.loads(data)


def save(url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    data = get(url, raw=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def search(words, models, limit):
    kind = "models" if models else "textures"
    assets = get("%s/assets?t=%s" % (PH, kind))
    words = [w.lower() for w in words]
    hits = []
    for pid, a in assets.items():
        text = " ".join([pid, a.get("name", "")] + a.get("tags", []) + a.get("categories", [])).lower()
        if all(w in text for w in words):
            hits.append((a.get("download_count", 0), pid, a))
    hits.sort(reverse=True)
    for _, pid, a in hits[:limit]:
        dims = a.get("dimensions")
        size = (" %.2f x %.2f m" % (dims[0] / 1000, dims[1] / 1000)) if dims and kind == "textures" else ""
        print("%-32s %-34s%s  [%s]" % (pid, a.get("name", "")[:34], size, ", ".join(a.get("categories", [])[:3])))
    print("%d match%s. %s" % (len(hits), "" if len(hits) == 1 else "es", CREDIT))


def texture(pid, res, out):
    files = get("%s/files/%s" % (PH, pid))
    info = get("%s/info/%s" % (PH, pid))
    d = os.path.join(out, pid)
    got = {}
    for key, kind in (("Diffuse", "diff"), ("nor_gl", "nor_gl"), ("arm", "arm"), ("Rough", "rough")):
        if key == "Rough" and "arm" in got:
            continue
        try:
            url = files[key][res]["jpg"]["url"]
        except KeyError:
            continue
        got[kind] = save(url, os.path.join(d, "%s_%s_%s.jpg" % (pid, kind, res)))
    dims = info.get("dimensions") or [1000, 1000]
    meta = {"id": pid, "name": info.get("name"), "metres": dims[0] / 1000.0, "metres_v": dims[1] / 1000.0,
            "license": "CC0", "source": "https://polyhaven.com/a/" + pid, "files": got}
    with open(os.path.join(d, "info.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print(json.dumps({"ok": True, "folder": d, "metres": meta["metres"], "maps": sorted(got)}))
    print(CREDIT)


def model(pid, res, out):
    files = get("%s/files/%s" % (PH, pid))
    g = files["gltf"][res]["gltf"]
    d = os.path.join(out, pid)
    path = save(g["url"], os.path.join(d, os.path.basename(g["url"])))
    for rel, f in g.get("include", {}).items():
        target = os.path.normpath(os.path.join(d, rel))
        if not target.startswith(os.path.normpath(d) + os.sep):
            raise ValueError("unsafe path in listing: " + rel)
        save(f["url"], target)
    with open(os.path.join(d, "info.json"), "w") as f:
        json.dump({"id": pid, "license": "CC0", "source": "https://polyhaven.com/a/" + pid, "gltf": path}, f, indent=1)
    print(json.dumps({"ok": True, "gltf": path}))
    print(CREDIT)


def ambientcg(aid, res, out):
    data = get("https://ambientcg.com/get?file=%s_%s-JPG.zip" % (aid, res), raw=True)
    d = os.path.join(out, aid)
    os.makedirs(d, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            base = os.path.basename(n)
            if not base or not base.lower().endswith((".jpg", ".png")):
                continue
            with open(os.path.join(d, base), "wb") as f:     # basename only: nothing lands outside d
                f.write(z.read(n))
    with open(os.path.join(d, "info.json"), "w") as f:
        json.dump({"id": aid, "license": "CC0", "source": "https://ambientcg.com/view?id=" + aid,
                   "metres": None, "note": "ambientCG lists no physical size; judge it from the photo"}, f, indent=1)
    print(json.dumps({"ok": True, "folder": d, "files": sorted(os.listdir(d))}))
    print("Source: ambientCG (ambientcg.com), CC0")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("words", nargs="+")
    s.add_argument("--models", action="store_true")
    s.add_argument("--limit", type=int, default=20)
    for name, res in (("texture", "2k"), ("model", "1k"), ("ambientcg", "2K")):
        q = sub.add_parser(name)
        q.add_argument("id")
        q.add_argument("--res", default=res)
        q.add_argument("--out", default="cc0")
    a = p.parse_args()
    if a.cmd == "search":
        search(a.words, a.models, a.limit)
    else:
        {"texture": texture, "model": model, "ambientcg": ambientcg}[a.cmd](a.id, a.res, a.out)


if __name__ == "__main__":
    sys.exit(main())
