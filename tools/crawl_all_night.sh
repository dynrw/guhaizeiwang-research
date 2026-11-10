#!/usr/bin/env bash
# 过夜连续爬取: 每轮 60 分钟, 直到 state.json 的 done 覆盖 1..13406 或连续 3 轮无进展
cd "$(dirname "$0")/.." || exit 1
rounds=0
stall=0
prev=0
while true; do
  rounds=$((rounds+1))
  python3 tools/crawl_replies.py --max-minutes 60
  done_n=$(python3 -c "import json;print(len(json.load(open('archive/state.json',encoding='utf-8'))['done']))")
  echo "[wrapper] round $rounds done=$done_n $(date +%H:%M:%S)"
  if [ "$done_n" -le "$prev" ]; then stall=$((stall+1)); else stall=0; fi
  prev=$done_n
  if [ "$stall" -ge 3 ]; then echo "[wrapper] stalled 3 rounds, exiting"; break; fi
  # 剩余为 0 则收尾
  left=$(python3 - <<'EOF'
import json, os
st = json.load(open('archive/state.json', encoding='utf-8'))
done = set(st['done'])
last = 13406
while last > 1 and last in done: last -= 1
print(0 if all(p in done for p in range(1, 13407)) else 1)
EOF
)
  if [ "$left" = "0" ]; then echo "[wrapper] all pages done"; break; fi
  sleep 5
done
