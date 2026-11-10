#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 build_floor_index.py — 汇总 pages/*.json 为两个视图:
   archive/floors_all.jsonl      作者楼层全量(时间升序), 含页码/回复ID/时间/文字/图片/点赞
   archive/progress.json         爬取覆盖情况统计
"""
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(REPO, "archive", "pages")

DT_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{2}) ")


def norm_dt(s):
    """26-11-09 20:48 -> 2026-11-09 20:48"""
    m = DT_RE.match(s or "")
    if not m:
        return s
    y, mo, d = m.groups()
    return "20%s-%s-%s%s" % (y, mo, d, (s or "")[8:])


def main():
    floors, pages = [], 0
    tmin, tmax = None, None
    for fn in os.listdir(PAGES_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(PAGES_DIR, fn), encoding="utf-8") as f:
            doc = json.load(f)
        pages += 1
        if doc.get("error"):
            continue
        for fl in doc.get("floors", []):
            fl2 = dict(fl)
            fl2["page"] = doc["page"]
            fl2["datetime"] = norm_dt(fl.get("datetime"))
            floors.append(fl2)
        r = doc.get("time_range") or [None, None]
        for t in r:
            if t:
                t2 = norm_dt(t)
                tmin = t2 if tmin is None or t2 < tmin else tmin
                tmax = t2 if tmax is None or t2 > tmax else tmax

    floors.sort(key=lambda x: (x.get("datetime") or "", x.get("reply_id") or ""))
    out = os.path.join(REPO, "archive", "floors_all.jsonl")
    with open(out, "w", encoding="utf-8") as f:
        for fl in floors:
            f.write(json.dumps(fl, ensure_ascii=False) + "\n")

    n_img = sum(len(f.get("images", [])) for f in floors)
    prog = {"pages_archived": pages, "author_floors": len(floors),
            "author_images": n_img, "time_covered": [tmin, tmax]}
    with open(os.path.join(REPO, "archive", "progress.json"), "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=1)
    print(json.dumps(prog, ensure_ascii=False))


if __name__ == "__main__":
    main()
