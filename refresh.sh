#!/bin/bash
# token 续期: 开代理 -> 等用户打开小程序(或唤起已开窗口) -> 抓新 token -> 关代理
# 前提: mitmproxy CA 已加入系统钥匙串并信任(见 README)
cd "$(dirname "$0")" || exit 1
rm -f token.fresh
pkill -f "mitmdump.*token_grab" 2>/dev/null; sleep 1
(mitmdump -s "$PWD/token_grab.py" --listen-port 8080 --set block_global=false \
  --set confdir="$PWD/mitmca" --allow-hosts 'codoon|igofit' > mitm_refresh.log 2>&1 &)
sleep 3
pgrep -f "mitmdump.*token_grab" > /dev/null || { echo "mitmdump 启动失败"; exit 1; }
networksetup -setwebproxy "Wi-Fi" 127.0.0.1 8080
networksetup -setsecurewebproxy "Wi-Fi" 127.0.0.1 8080
echo ">>> 代理已开(只截获 *.codoon.com, 其他直通)。请打开一次【企业咕咚】小程序等首页加载..."
# 先尝试唤起已开的小程序窗口(若在); 不行就等用户手动打开
osascript <<'AS' 2>/dev/null
tell application "WeChat" to activate
delay 1
tell application "System Events" to tell process "WeChat"
  repeat with w in windows
    try
      if (name of w as text) contains "咕咚" then
        perform action "AXRaise" of w
        exit repeat
      end if
    end try
  end repeat
end tell
AS
for i in $(seq 1 120); do
  [ -f token.fresh ] && break
  sleep 1
done
networksetup -setwebproxystate "Wi-Fi" off
networksetup -setsecurewebproxystate "Wi-Fi" off
pkill -f "mitmdump.*token_grab" 2>/dev/null
if [ -f token.fresh ]; then
  rm -f token.fresh
  echo ">>> token 续期完成(25小时有效), 代理已关闭"
else
  echo ">>> 120秒内没抓到登录——请确认小程序已打开且 token 已过期(没过期不会重新登录)"
fi
