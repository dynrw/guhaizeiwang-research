#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 crawl_replies.py — 抓取淘股吧主帖《不管有多苦（超短实盘）》全部回复页，
 只归档作者（股海贼王, userID=308803）的楼层。

 数据源（免登录可用，见 HANDOFF.md 探测结论）:
   https://m.tgb.cn/getNearlyReply?topicID=1424851&pageNo=<N>   每页 10 楼, 页码升序=时间倒序

 输出:
   archive/pages/<N>.json   页 N 内作者楼层 + 页级元数据
   archive/state.json       断点续传状态

 用法:
   python3 tools/crawl_replies.py                  # 从断点继续, 老页(页码大)优先
   python3 tools/crawl_replies.py --max-pages 500  # 本次最多处理 500 页后退出
   python3 tools/crawl_replies.py --max-minutes 80 # 或按时间预算退出
   python3 tools/crawl_replies.py --retry-failed   # 重试此前失败页
"""
import argparse
import html as htmllib
import json
import os
import random
import re
import sys
import time
import urllib.request
import urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE = os.path.join(REPO, "archive")
PAGES_DIR = os.path.join(ARCHIVE, "pages")
STATE_PATH = os.path.join(ARCHIVE, "state.json")

TOPIC_ID = 1424851
AUTHOR_USERID = "308803"
THREAD_CODE = "1ykAFNDujlw"  # 短链码, 楼层直链用
BASE_URL = "https://m.tgb.cn/getNearlyReply?topicID=%d&pageNo=%%d" % TOPIC_ID

# 已知首尾页（探测于 2026-11-09; 页码会随新回复增长, 脚本自动向上探测）
FIRST_PAGE = 1            # 最新
KNOWN_LAST_PAGE = 13406   # 最老 (2016-02-21 开帖附近)

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

AVATAR_HASHES = {"ml4zw7orgmhw"}  # 作者头像
IMG_RE = re.compile(r"image\.tgb\.cn/img/(\d{4}/\d{2}/\d{2}/([a-z0-9]+))\.(png|jpg|jpeg|gif)", re.I)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "failed": {}, "tail_probe": None}


def save_state(st):
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, STATE_PATH)


def fetch(url, timeout=15, retries=3):
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(3 * (i + 1) + random.random() * 2)
    raise last_err


BLOCK_RE = re.compile(r'<div class="plItem"\s+list-userID="(\d+)"', re.S)


def parse_page(page_html):
    """返回 (items, author_floors)。items=整页全部楼层的轻量记录, author_floors=作者楼层全量。"""
    starts = list(BLOCK_RE.finditer(page_html))
    items, authors = [], []
    for idx, m in enumerate(starts):
        end = starts[idx + 1].start() if idx + 1 < len(starts) else len(page_html)
        block = page_html[m.start():end]
        uid = m.group(1)

        rid_m = re.search(r'contentid="(\d+)"', block)
        reply_id = rid_m.group(1) if rid_m else None
        time_m = re.search(r'<p class="pl_time">([^<]+)</p>', block)
        dt = time_m.group(1).strip() if time_m else None

        lite = {"user_id": uid, "reply_id": reply_id, "datetime": dt}

        if uid != AUTHOR_USERID:
            items.append(lite)
            continue

        # 文字: pl_text 起至 pl_line2 止, 先反转义再剥标签（截图楼层常以转义 img 形式嵌在正文里）
        tx_m = re.search(r'<div class="pl_text"[^>]*>([\s\S]*?)<div class="pl_line', block)
        text = ""
        if tx_m:
            raw = htmllib.unescape(tx_m.group(1))
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()

        # 图片: 原始块 + 反转义块里所有 image.tgb.cn 引用, 去掉头像/尺寸后缀
        scan = block + "\n" + htmllib.unescape(block)
        seen, images = set(), []
        for path, h, ext in IMG_RE.findall(scan):
            if h in AVATAR_HASHES or h in seen:
                continue
            seen.add(h)
            images.append({"base": "https://image.tgb.cn/img/%s.%s" % (path, ext),
                           "hash": h, "ext": ext.lower()})
        likes_m = re.search(r'<span class="plzan_num" id="\d+">(\d+)</span>', block)

        authors.append({
            "reply_id": reply_id,
            "url": ("https://www.tgb.cn/a/%s/%s#%s" % (THREAD_CODE, reply_id, reply_id)
                    if reply_id else None),
            "datetime": dt,
            "text": text,
            "images": images,
            "likes": int(likes_m.group(1)) if likes_m else None,
        })
        items.append(lite)
    return items, authors


def write_page(page_no, items, authors, err=None):
    doc = {
        "page": page_no,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "total_items": len(items),
        "author_floors": len(authors),
        "time_range": ([i["datetime"] for i in items if i["datetime"]][-1],
                       [i["datetime"] for i in items if i["datetime"]][0])
        if any(i["datetime"] for i in items) else [None, None],
        "error": err,
        "floors": authors,
    }
    p = os.path.join(PAGES_DIR, "%d.json" % page_no)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=0)
    ap.add_argument("--max-minutes", type=float, default=0)
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args()

    os.makedirs(PAGES_DIR, exist_ok=True)
    st = load_state()
    done = set(st["done"])
    failed = dict(st["failed"])

    # 尾页自动上探（新回复会增加总页数; 只在从最新端继续时才有意义, 此处爬老端不受影响）
    last_page = KNOWN_LAST_PAGE

    # 待办队列: 老页优先(页码降序) —— 2016-2021 高价值数据最先落袋
    if args.retry_failed and failed:
        todo = sorted((int(k) for k in failed), reverse=True)
    else:
        todo = [p for p in range(last_page, FIRST_PAGE - 1, -1) if p not in done and str(p) not in failed]

    t0 = time.time()
    processed = 0
    log = lambda msg: print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

    log("todo=%d pages (done=%d failed=%d), from page %s" %
        (len(todo), len(done), len(failed), todo[0] if todo else "-"))

    for page in todo:
        if args.max_pages and processed >= args.max_pages:
            log("reached --max-pages, exit")
            break
        if args.max_minutes and (time.time() - t0) / 60 >= args.max_minutes:
            log("reached --max-minutes, exit")
            break
        try:
            body = fetch(BASE_URL % page)
            items, authors = parse_page(body)
            write_page(page, items, authors)
            done.add(page)
            failed.pop(str(page), None)
            processed += 1
            if processed % 20 == 0 or authors:
                log("page %d: %d items, %d author floors%s" %
                    (page, len(items), len(authors),
                     (" :: " + "; ".join("%s [%s] imgs=%d %s" % (
                         a["datetime"], a["reply_id"], len(a["images"]),
                         (a["text"][:40] or "(无文字)")) for a in authors)) if authors else ""))
        except Exception as e:  # noqa: BLE001
            failed[str(page)] = str(e)
            log("page %d FAILED: %s" % (page, e))
        st["done"] = sorted(done)
        st["failed"] = failed
        save_state(st)
        time.sleep(args.delay + random.random() * 0.6)

    log("session done: processed=%d, total done=%d/%d, failed=%d" %
        (processed, len(done), last_page, len(failed)))


if __name__ == "__main__":
    main()
