#!/usr/bin/env python3
"""fakerun 主程序 — 校内道路轨迹伪造提交
用法: python3 -u forge2.py [--dry]
依赖: config.json(从 config.example.json 复制填写), token.txt, route_template.json
"""
import urllib.request, urllib.parse, json, gzip, time, random, math, sys, subprocess, os

DIR = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(DIR, "config.json")))
TOKEN = open(os.path.join(DIR, "token.txt")).read().strip()
UID = CFG["user_id"]
CLUB_ID = CFG.get("club_id", 0)
BRAND = CFG["brand"]
DEV = CFG["device_info"]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.59(0x18003733) NetType/WIFI Language/zh_CN")
BASE = "https://mini-club.codoon.com"

TARGET_M = CFG.get("target_m", 3300)
BASE_PACE = CFG.get("base_pace", 300)   # 秒/km
CADENCE = 2.62

POLY = [tuple(p) for p in json.load(open(os.path.join(DIR, "route_template.json")))]

def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 2*6371000*math.asin(math.sqrt(h))
ARCS = [0.0]
for k in range(len(POLY)-1):
    ARCS.append(ARCS[-1] + hav(POLY[k], POLY[k+1]))
TOTAL_POLY = ARCS[-1]

def at_arc(s):
    s = max(0.0, min(TOTAL_POLY, s))
    for k in range(len(ARCS)-1):
        if ARCS[k+1] >= s:
            f = (s - ARCS[k]) / (ARCS[k+1] - ARCS[k]) if ARCS[k+1] > ARCS[k] else 0
            return (POLY[k][0] + (POLY[k+1][0]-POLY[k][0])*f,
                    POLY[k][1] + (POLY[k+1][1]-POLY[k][1])*f)
    return POLY[-1]

def make_course(target_m):
    """两种模式: 全程单向+折返尾 / 随机起点往返"""
    need = target_m + 40
    if random.random() < 0.55:
        start = random.uniform(0, 60)
        course, desc = [start, TOTAL_POLY, start + need - TOTAL_POLY], "全程单向+折返尾"
    else:
        start = random.uniform(0, max(1, TOTAL_POLY - need/2))
        course, desc = [start, start + need/2, start], "随机起点往返"
    return course, desc

class Walker:
    def __init__(self, course):
        self.course = course; self.seg = 0; self.s = course[0]
    def step(self, d):
        target = self.course[self.seg + 1]
        direction = 1 if target >= self.course[self.seg] else -1
        self.s += direction * d
        if (direction > 0 and self.s >= target) or (direction < 0 and self.s <= target):
            if self.seg + 2 < len(self.course): self.seg += 1
            self.s = target
        return self.s

def call(method, path, body=None, extra=None):
    q = {"platform_source_type": 0, "platform_user_id": UID, "platform_language": "zh", "platform_app_brand": BRAND}
    if extra: q.update(extra)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path + "?" + urllib.parse.urlencode(q), data=data, method=method)
    req.add_header("Authorization", "Bearer " + TOKEN); req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://servicewechat.com/%s/942/page-frame.html" % CFG.get("appid", "wx2961574bbec73239"))
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        if raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
        return json.loads(raw) if raw else {}

def mkpoint(i, sim_s, lat, lon, cum, typ, ts, step_m):
    # 真实iPhone点位指纹——字段和取值域都经过服务端验证, 勿改
    return {"distance": round(step_m, 1), "elevation": round(20 + math.sin(i/8) + random.gauss(0, .3), 1),
            "latitude": round(lat, 7), "longitude": round(lon, 7),
            "v_accuracy": round(random.uniform(2.8, 3.3), 6), "h_accuracy": 0, "gyroscope": "",
            "time_stamp": int(ts * 1000), "to_start_dost_time": int(sim_s * 1000),
            "to_start_distance": round(cum * .97, 1), "type": typ,
            "time_str": time.strftime("%m.%d %H:%M:%S", time.localtime(ts))}

def dry():
    course, desc = make_course(TARGET_M)
    w = Walker(course); cum = 0.0; pts = []
    while cum < TARGET_M:
        pace = max(280, min(330, BASE_PACE + 10*math.sin(cum/500) + random.gauss(0, 5)))
        dt = random.uniform(3.0, 7.0)
        step_m = 1000.0/pace * dt
        s = w.step(step_m); la, lo = at_arc(s); cum += step_m
        pts.append((la + random.gauss(0, 1.5)/111320, lo + random.gauss(0, 1.5)/85200))
    print(f"模式: {desc} | {len(pts)}点 {cum:.0f}m 折线总长{TOTAL_POLY:.0f}m")
    la=[p[0] for p in pts]; lo=[p[1] for p in pts]
    print(f"坐标范围: lat {min(la):.5f}~{max(la):.5f} lon {min(lo):.5f}~{max(lo):.5f}")

def run():
    course, desc = make_course(TARGET_M)
    print(f"[*] 路线模式: {desc}", flush=True)
    w = Walker(course)
    r = call("POST", "/v1/route/start_route", {"is_in_room": 0, "sports_type": 1, "location": "",
                                               "source": 2, "device_info": DEV})
    rid = r.get("route_id")
    print("start ->", rid, flush=True)
    if not rid: return
    wall0 = time.time(); ts_cursor = wall0
    cum = 0.0; i = 0; steps = 0; last_steps = 0.0
    pending = []; all_pts = []
    while cum < TARGET_M:
        sim = time.time() - wall0
        i += 1
        pace = BASE_PACE + 10 * math.sin(sim / 170) + random.gauss(0, 5)
        if 560 < (sim % 900) < 595: pace += 25
        pace = max(280, min(330, pace))
        dt = random.uniform(3.0, 7.0)              # 真实GPS回调间隔3~7秒
        step_m = 1000.0 / pace * dt
        s = w.step(step_m)
        la, lo = at_arc(s)
        lat = la + random.gauss(0, 1.5) / 111320   # 噪声单位是米, 必须除以每度米数
        lon = lo + random.gauss(0, 1.5) / 85200
        cum += step_m
        ts_cursor += dt
        pending.append(mkpoint(i, sim + dt, lat, lon, cum, 0 if i > 1 else 1, ts_cursor, step_m))
        if len(pending) >= random.randint(2, 4):
            all_pts.extend(pending)
            rr = call("POST", "/v1/route/create_route_point", {"points": pending, "route_id": rid})
            if rr.get("ok") is not True: print("  BATCH FAIL:", rr, flush=True)
            pending = []
        if sim - last_steps >= 45:
            d = sim - last_steps
            steps += int(d * CADENCE * random.uniform(.94, 1.06))
            call("POST", "/v1/route/create_route_gyroscope_steps",
                 {"route_id": rid, "type": 6, "cur_steps": steps, "upload_time": int(time.time()), "dur": int(d)})
            last_steps = sim
        time.sleep(dt)
    sim = time.time() - wall0; i += 1; cum += 3.0; ts_cursor += random.uniform(3, 6)
    s = w.step(3.0); la, lo = at_arc(s)
    pending.append(mkpoint(i, sim, la, lo, cum, 5, ts_cursor, 3.0))
    all_pts.extend(pending)
    print("final:", call("POST", "/v1/route/create_route_point", {"points": pending, "route_id": rid}), flush=True)
    time.sleep(1.5)
    for attempt in range(3):
        comp = call("POST", "/v1/route/completes_route", {"is_delete": False, "route_id": rid, "device_info": DEV})
        print(f"complete#{attempt} ->", comp, flush=True)
        if comp.get("route_id") not in (0, None, ""):
            print(f"[OK] 记录ID {comp['route_id']}, {i}点 {cum:.0f}m {sim/60:.1f}min 步数{steps}", flush=True)
            json.dump([{"latitude": p["latitude"], "longitude": p["longitude"]} for p in all_pts],
                      open(f"/tmp/points_{rid[:8]}.json", "w"))
            try:
                subprocess.run(["python3", os.path.join(DIR, "route_img.py"), rid,
                                f"/tmp/points_{rid[:8]}.json", f"{cum/1000:.2f}", f"{sim/60:.1f}"],
                               timeout=300, capture_output=True)
                print("[OK] 轨迹图已生成并挂到记录", flush=True)
            except Exception as e:
                print("[!] 挂图失败:", e, flush=True)
            break
        time.sleep(5)
    else:
        print("[FAIL] 完成失败; 进行中的路线可用 completes_route is_delete=true 清理后重试", flush=True)

if __name__ == "__main__":
    if "--dry" in sys.argv: dry()
    else: run()
