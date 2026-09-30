#!/bin/bash
# 每日自动打卡: 防重检查 -> 随机延时 -> 必要时续期token -> forge2 提交
# 建议由 cron/launchd/agent 定时器在目标时段触发
cd "$(dirname "$0")" || exit 1
LOG="daily_$(date +%Y%m%d).log"
exec >> "$LOG" 2>&1
echo "===== $(date '+%F %T') 自动打卡启动 ====="

CFG_JSON=$(python3 -c "import json;print(json.dumps(json.load(open('config.json'))))")
CLUB_ID=$(python3 -c "import json;print(json.load(open('config.json')).get('club_id',0))")

# 0) 防重: 今日已有>=3km完成记录则跳过
DONE_TODAY=$(python3 - <<'PY'
import urllib.request, urllib.parse, json, gzip, datetime, os
cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath("config.json")), "config.json")))
try:
    TOKEN = open("token.txt").read().strip()
except FileNotFoundError:
    print("NOFILE"); raise SystemExit
q = {"club_id": cfg.get("club_id", 0), "platform_source_type": 0, "platform_user_id": cfg["user_id"],
     "platform_language": "zh", "platform_app_brand": cfg["brand"],
     "cursor": "0", "limit": "5", "sports_type": "1"}
req = urllib.request.Request("https://mini-club.codoon.com/v1/statistic/get_user_gps_info/list?" + urllib.parse.urlencode(q))
req.add_header("Authorization", "Bearer " + TOKEN)
try:
    r = urllib.request.urlopen(req, timeout=20); raw = r.read()
    if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
    today = datetime.date.today()
    for it in json.loads(raw).get("list", []):
        if datetime.date.fromtimestamp(it["start_time"]) == today and it["total_length"] >= 3000:
            print("YES"); break
except Exception:
    pass
PY
)
if [ "$DONE_TODAY" = "YES" ]; then
  echo "[=] 今日已有>=3km完成记录, 跳过本次打卡"
  exit 0
fi

# 1) 随机延时(默认60~2159秒, 按需调整)
DELAY=$((60 + RANDOM % 2100))
echo "[*] 随机延时 ${DELAY}s"
sleep "$DELAY"

# 2) token 剩余不足1小时则续期(续期失败不中止, 剩余>25分钟仍可跑)
REM=$(python3 - <<'PY'
import base64, json, time
try:
    tok = open("token.txt").read().strip()
    p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
    print(int(json.loads(base64.urlsafe_b64decode(p))["exp"] - time.time()))
except Exception:
    print(-1)
PY
)
echo "[*] token 剩余 ${REM}s"
if [ "$REM" -lt 3600 ]; then
  ./refresh.sh || echo "[!] 续期失败, 继续尝试用现有 token"
  REM=$(python3 - <<'PY'
import base64, json, time
try:
    tok = open("token.txt").read().strip()
    p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
    print(int(json.loads(base64.urlsafe_b64decode(p))["exp"] - time.time()))
except Exception:
    print(-1)
PY
)
fi
if [ "$REM" -lt 1500 ]; then
  echo "[!] token 剩余不足, 中止。请打开一次企业咕咚小程序后重试 ./refresh.sh"
  exit 2
fi

# 3) 提交(约17分钟)
echo "[*] 开始提交 $(date '+%T')"
python3 -u forge2.py
RC=$?
echo "===== $(date '+%F %T') 完成 rc=$RC ====="
exit $RC
