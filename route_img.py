#!/usr/bin/env python3
"""轨迹图生成+OSS直传+挂载
用法: python3 route_img.py <route_id> <points_json_file> [里程km] [时长min]
依赖: config.json, token.txt, Pillow
"""
import json, math, random, sys, urllib.request, urllib.parse, uuid, gzip, io, os

DIR = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(DIR, "config.json")))
TOKEN = open(os.path.join(DIR, "token.txt")).read().strip()
UID = CFG["user_id"]
BRAND = CFG["brand"]
BASE = "https://mini-club.codoon.com"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.59(0x18003733) NetType/WIFI Language/zh_CN")

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

def mercator(lat, lon, zoom=17):
    n = 2 ** zoom
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y

def fetch_tile(tx, ty, zoom):
    # 腾讯矢量瓦片(微信小程序同款), 256px, y轴TMS反转
    yt = 2 ** zoom - 1 - ty
    for server in range(4):
        url = (f"https://rt{server}.map.gtimg.com/realtimerender?"
               f"z={zoom}&x={tx}&y={yt}&type=vector&style=0&v=1")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = r.read()
                if len(data) > 3000:
                    return data
        except Exception:
            continue
    return None

def build_image(points, km_text, dur_text, out="/tmp/route_img.png"):
    from PIL import Image, ImageDraw, ImageFont
    zoom = 17
    proj = [mercator(p["latitude"], p["longitude"], zoom) for p in points]
    xs = [p[0] for p in proj]; ys = [p[1] for p in proj]
    TW = 256
    W, H = 750, 560
    cx = (max(xs) + min(xs)) / 2; cy = (max(ys) + min(ys)) / 2
    span_x = max(xs) - min(xs); span_y = max(ys) - min(ys)
    tiles_x = max(2, int(span_x * 1.2) + 2); tiles_y = max(2, int(span_y * 1.2) + 2)
    tx0 = math.floor(cx - tiles_x / 2); ty0 = math.floor(cy - tiles_y / 2)
    canvas = Image.new("RGB", (tiles_x * TW, tiles_y * TW), (233, 233, 231))
    for i in range(tiles_x):
        for j in range(tiles_y):
            data = fetch_tile(tx0 + i, ty0 + j, zoom)
            if data:
                try:
                    tile = Image.open(io.BytesIO(data)).convert("RGB")
                    if tile.size != (TW, TW): tile = tile.resize((TW, TW))
                    canvas.paste(tile, (i * TW, j * TW))
                except Exception:
                    pass
    def to_canvas(p):
        return ((p[0] - tx0) * TW, (p[1] - ty0) * TW)
    cp = [to_canvas(p) for p in proj]
    cxs = [p[0] for p in cp]; cys = [p[1] for p in cp]
    pad = 60
    left = max(0, min(cxs) - pad); right = min(canvas.width, max(cxs) + pad)
    top = max(0, min(cys) - pad); bottom = min(canvas.height, max(cys) + pad)
    aspect = W / H
    w = right - left; h = bottom - top
    if w / h < aspect:
        want = aspect * h; left = max(0, (left + right) / 2 - want / 2); right = left + want
    else:
        want = w / aspect; top = max(0, (top + bottom) / 2 - want / 2); bottom = top + want
    img = canvas.crop((int(left), int(top), int(right), int(bottom))).resize((W * 2, H * 2), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    pts2 = [((x - left) * (W * 2 / (right - left)), (y - top) * (H * 2 / (bottom - top))) for x, y in cp]
    d.line(pts2, fill=(255, 255, 255), width=14, joint="curve")
    d.line(pts2, fill=(86, 158, 245), width=9, joint="curve")
    d.ellipse([pts2[0][0]-10, pts2[0][1]-10, pts2[0][0]+10, pts2[0][1]+10], fill=(64, 196, 106))
    d.ellipse([pts2[-1][0]-10, pts2[-1][1]-10, pts2[-1][0]+10, pts2[-1][1]+10], fill=(240, 90, 90))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 40)
    except Exception:
        font = ImageFont.load_default()
    d.text((30, img.height - 90), f"{km_text} km", fill=(60, 60, 60), font=font)
    d.text((30, img.height - 46), f"{dur_text} min", fill=(120, 120, 120), font=font)
    img.save(out)
    return out

def upload_oss(png_path):
    sig = call("GET", "/v1/common/oss_signature", extra={"source": ""})
    host = sig["host"]; dirp = sig["dir"]
    fname = f"{uuid.uuid4()}.png"
    key = f"{dirp}/{fname}"
    fields = {
        "key": key,
        "policy": sig["policy"],
        "x-oss-signature-version": sig["x_oss_signature_version"],
        "x-oss-credential": sig["x_oss_credential"],
        "x-oss-date": sig["x_oss_date"],
        "x-oss-security-token": sig["x_oss_security_token"],
        "x-oss-signature": sig["signature"],
    }
    b = bytearray()
    for k, v in fields.items():
        b += f"--miniupload\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    b += f"--miniupload\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\nContent-Type: image/png\r\n\r\n".encode()
    b += open(png_path, "rb").read() + b"\r\n--miniupload--\r\n"
    req = urllib.request.Request(host, data=bytes(b), method="POST")
    req.add_header("Content-Type", "multipart/form-data; boundary=miniupload")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    return f"{sig['domain']}/{key}"

if __name__ == "__main__":
    rid = sys.argv[1]
    pts = json.load(open(sys.argv[2]))
    km = sys.argv[3] if len(sys.argv) > 3 else "3.30"
    dur = sys.argv[4] if len(sys.argv) > 4 else "16.5"
    png = build_image(pts, km, dur)
    url = upload_oss(png)
    print("OSS URL:", url)
    r = call("POST", "/v1/route/create_route_image_url", {"route_id": rid, "image_url": url})
    print("create_route_image_url ->", json.dumps(r, ensure_ascii=False)[:200])
