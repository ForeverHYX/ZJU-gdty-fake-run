#!/usr/bin/env python3
"""共享状态检查工具(跨平台), 供调度脚本调用
用法:
  python check_status.py dedup      -> 今日已有>=3km记录输出 YES, 否则 NO
  python check_status.py remaining  -> 输出 token 剩余秒数
"""
import sys, os, json, base64, time, gzip, urllib.request, urllib.parse

DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DIR)
CFG = json.load(open("config.json"))

def load_token():
    try:
        return open("token.txt").read().strip()
    except FileNotFoundError:
        return ""

def remaining():
    tok = load_token()
    if not tok:
        print(-1); return
    try:
        p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
        print(int(json.loads(base64.urlsafe_b64decode(p))["exp"] - time.time()))
    except Exception:
        print(-1)

def dedup():
    tok = load_token()
    if not tok:
        print("NO"); return
    q = {"club_id": CFG.get("club_id", 0), "platform_source_type": 0, "platform_user_id": CFG["user_id"],
         "platform_language": "zh", "platform_app_brand": CFG["brand"],
         "cursor": "0", "limit": "5", "sports_type": "1"}
    req = urllib.request.Request("https://mini-club.codoon.com/v1/statistic/get_user_gps_info/list?" + urllib.parse.urlencode(q))
    req.add_header("Authorization", "Bearer " + tok)
    import datetime
    try:
        r = urllib.request.urlopen(req, timeout=20); raw = r.read()
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        today = datetime.date.today()
        hit = any(datetime.date.fromtimestamp(it["start_time"]) == today and it["total_length"] >= 3000
                  for it in json.loads(raw).get("list", []))
        print("YES" if hit else "NO")
    except Exception:
        print("NO")   # 查询失败不拦截打卡

if __name__ == "__main__":
    {"dedup": dedup, "remaining": remaining}[sys.argv[1]]()
