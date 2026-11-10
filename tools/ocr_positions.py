#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 ocr_positions.py — 批量 OCR 作者楼层截图 (持仓页/同花顺资产页) -> archive/ocr/<rid>_<k>.json

 需要: 环境变量 ZAI_API_KEY (智谱开放平台 key, https://open.bigmodel.cn)
 用法: python3 tools/ocr_positions.py [--only-holdings] [--max N]
   --only-holdings  只处理每个交易日收盘楼层(约15:00-16:00发帖)的第1张图(持仓页概率最高)
"""
import argparse
import base64
import json
import os
import re
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(REPO, "archive", "images")
OCR_DIR = os.path.join(REPO, "archive", "ocr")
FLOORS = os.path.join(REPO, "archive", "floors_all.jsonl")

API = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
MODEL = "glm-4v-plus"   # 如需更换改这里
PROMPT = (
    "这是股票交易相关截图。请提取：1) 页面类型（券商持仓页/委托记录页/同花顺资产分析页/其他）；"
    "2) 若为持仓页: 人民币余额、可用、可取、参考市值、资产（总资产）、盈亏，"
    "以及每只股票的 代码/名称/证券数量/成本价/当前价/最新市值/浮动盈亏/盈亏比例；"
    "3) 若为同花顺资产分析页: 区间、收益率、盈亏金额、总资产；"
    "4) 若为委托页: 仅输出页面类型和'委托记录页'。"
    "读不清的字段输出 null，不要猜。以JSON输出: {\"type\":..., \"cash\":..., \"total_assets\":..., "
    "\"market_value\":..., \"day_pnl\":..., \"return_pct\":..., \"period\":..., "
    "\"holdings\":[{\"code\":...,\"name\":...,\"shares\":...,\"cost\":...,\"price\":...,\"mv\":...,\"pnl\":...,\"pnl_pct\":...}]}"
)

CLOSE_RE = re.compile(r" 1[45]:\d\d$")


def call_vision(img_path, api_key):
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    ext = "jpeg" if img_path.lower().endswith((".jpg", ".jpeg")) else "png"
    body = json.dumps({
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/%s;base64,%s" % (ext, b64)}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer %s" % api_key,
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode())
    text = resp["choices"][0]["message"]["content"]
    m = re.search(r"\{[\s\S]*\}", text)
    return json.loads(m.group(0)) if m else {"type": "unparsed", "raw": text}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-holdings", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    args = ap.parse_args()

    key = os.environ.get("ZAI_API_KEY") or os.environ.get("ZHIPUAI_API_KEY")
    if not key:
        raise SystemExit("缺少 ZAI_API_KEY 环境变量（智谱开放平台 key）")

    # 楼层元数据: reply_id -> (datetime, text, k)
    meta = {}
    with open(FLOORS, encoding="utf-8") as f:
        for line in f:
            fl = json.loads(line)
            for k in range(1, len(fl.get("images", [])) + 1):
                meta["%s_%d" % (fl["reply_id"], k)] = (fl["datetime"], fl.get("text") or "")

    os.makedirs(OCR_DIR, exist_ok=True)
    todo = []
    for fn in sorted(os.listdir(IMG_DIR)):
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in (".png", ".jpg", ".jpeg") or stem.endswith("_x"):
            continue
        if os.path.exists(os.path.join(OCR_DIR, stem + ".json")):
            continue
        if args.only_holdings:
            dt, _ = meta.get(stem, ("", ""))
            if not CLOSE_RE.search(dt) or not stem.endswith("_1"):
                continue
        todo.append(fn)

    print("%d to OCR" % len(todo), flush=True)
    done = fail = 0
    for fn in todo:
        if args.max and done >= args.max:
            break
        stem = os.path.splitext(fn)[0]
        dt, ftext = meta.get(stem, (None, None))
        try:
            parsed = call_vision(os.path.join(IMG_DIR, fn), key)
            doc = {"image": "archive/images/" + fn,
                   "floor_url": "https://www.tgb.cn/a/1ykAFNDujlw/%s#%s" % (stem.split("_")[0], stem.split("_")[0]),
                   "datetime": dt, "floor_text": ftext,
                   "ocr_engine": MODEL, "parsed": parsed}
            json.dump(doc, open(os.path.join(OCR_DIR, stem + ".json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            done += 1
            print("ok", stem, parsed.get("type"), parsed.get("total_assets") or parsed.get("return_pct"), flush=True)
        except Exception as e:  # noqa: BLE001
            fail += 1
            print("FAIL", stem, e, flush=True)
        time.sleep(1.0)
    print("done=%d fail=%d" % (done, fail), flush=True)


if __name__ == "__main__":
    main()
