#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 download_images.py — 下载作者楼层图片到 archive/images/<reply_id>_<k>.<ext>
 依次尝试: 原图 → _max → _760w 变体; 已存在则跳过。
 用法: python3 tools/download_images.py [--max N] [--delay 1.5]
"""
import argparse
import json
import os
import random
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_DIR = os.path.join(REPO, "archive", "pages")
IMG_DIR = os.path.join(REPO, "archive", "images")

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")


def try_download(url, dest, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://m.tgb.cn/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < 1000:
        raise IOError("suspiciously small: %d bytes" % len(data))
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    os.makedirs(IMG_DIR, exist_ok=True)
    todo = []
    for fn in os.listdir(PAGES_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(PAGES_DIR, fn), encoding="utf-8") as f:
            doc = json.load(f)
        for fl in doc.get("floors", []):
            for k, im in enumerate(fl.get("images", []), 1):
                dest = os.path.join(IMG_DIR, "%s_%d.%s" % (fl["reply_id"], k, im["ext"]))
                if not os.path.exists(dest):
                    todo.append((im, dest))

    print("%d images to download" % len(todo), flush=True)
    ok = fail = 0
    for im, dest in todo:
        if args.max and ok >= args.max:
            break
        # 变体规则(实测): 后缀固定为 _max.png/_760w.png/_1100h.png, 追加在完整 base(含原扩展名)之后
        candidates = [im["base"],
                      im["base"] + "_max.png",
                      im["base"] + "_760w.png",
                      im["base"] + "_1100h.png"]
        got = False
        for url in candidates:
            try:
                try_download(url, dest)
                ok += 1
                got = True
                break
            except Exception:  # noqa: BLE001
                continue
        if not got:
            fail += 1
            print("FAIL %s" % im["base"], flush=True)
        time.sleep(args.delay + random.random() * 0.5)
    print("done ok=%d fail=%d" % (ok, fail), flush=True)


if __name__ == "__main__":
    main()
