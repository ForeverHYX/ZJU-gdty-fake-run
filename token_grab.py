"""mitmproxy 插件: 拦截 auth/login 响应自动保存新 token
用法: mitmdump -s token_grab.py --allow-hosts 'codoon|igofit' ...
捕获成功后写 token.txt 并落 token.fresh 标记文件
"""
import json, gzip, os

DIR = os.path.dirname(os.path.abspath(__file__))

def response(flow):
    if "auth/login" in flow.request.pretty_url and flow.response:
        raw = flow.response.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            d = json.loads(raw)
            tok = d.get("token", {}).get("access_token")
            if tok:
                with open(os.path.join(DIR, "token.txt"), "w") as f:
                    f.write(tok)
                with open(os.path.join(DIR, "token.fresh"), "w") as f:
                    f.write("1")
                print("[+] token 已捕获并保存")
        except Exception:
            pass
