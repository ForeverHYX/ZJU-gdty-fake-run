# ZJU gdty fake run

浙大「浙大体艺」（企业咕咚）校园跑自动打卡工具链。**纯 Mac 端协议级实现**：不依赖手机、不需要越狱/辅助功能/虚拟定位，直接伪造小程序的跑步上传协议。

> 适用于：HarmonyOS NEXT / 无 root 安卓 / 任何装了 Mac 微信的场景（手机侧无解时换赛道打协议）。
> 风险自担：刷跑属于违反学校规定的行为，被认定通常导致体育成绩作废。本仓库仅供学习逆向与协议分析。

---

## 本文档的读法

**本文档写给 AI agent（Claude Code / Cursor / ZCode 等）直接执行。** 人类读者也可照做。agent 的任务：在用户的 Mac 上完成环境搭建、凭据采集、配置生成，然后交给定时任务每日运行。协议细节、反检测红线、故障排查全部在文内，不需要额外上下文。

## 工作原理（一分钟版）

小程序（uni-app 编译包，appid `wx2961574bbec73239`）与后端 `mini-club.codoon.com` 通信，Bearer JWT 鉴权（25 小时有效）。跑步数据流程：

```
POST /v1/route/start_route            -> 拿 route_id
POST /v1/route/create_route_point     -> 逐批上传 GPS 点(进行中实时)
POST /v1/route/create_route_gyroscope_steps -> 步数上报
POST /v1/route/completes_route        -> 完成(响应 route_id != 0 才是真成功)
GET  /v1/common/oss_signature         -> 轨迹图直传凭证
POST /v1/route/create_route_image_url -> 挂载轨迹图
```

本工具链：`forge2.py` 沿真实校内道路折线合成轨迹并实时提交；`route_img.py` 用腾讯地图瓦片画轨迹图传 OSS 挂载；`token_grab.py`+`refresh.sh` 解决 25 小时 token 续期；`daily_checkin.sh` 是每日入口。

## 文件清单

| 文件 | 作用 |
|---|---|
| `forge2.py` | 主程序：合成轨迹并提交（`--dry` 只看几何不上传） |
| `route_img.py` | 轨迹图生成（腾讯瓦片底图+蓝线）+ OSS 直传 + 挂载 |
| `token_grab.py` | mitmproxy 插件，自动截获 auth/login 保存 token |
| `refresh.sh` | 一键续期：开代理→等小程序打开→抓 token→关代理 |
| `daily_checkin.sh` / `daily_checkin.ps1` | 每日入口（bash / PowerShell）：防重→随机延时→必要时续期→提交 |
| `refresh.ps1` | Windows 版 token 续期（双栈代理开关） |
| `check_status.py` | 跨平台状态查询（防重/ token 剩余），调度脚本共用 |
| `unpack.js` | wxapkg 解包器（研究协议用） |
| `route_template.json` | 校内道路折线模板（217 点/3018m，可替换） |
| `config.example.json` | 配置模板 |

## Agent 部署流程

### 第 0 步：环境

```bash
brew install mitmproxy cliclick   # cliclick 仅自动唤起微信时需要
python3 -c "import PIL" || pip3 install --user pillow
```

小程序包缓存位置（研究/排错用）：
`~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/users/<微信内部哈希>/applet/packages/<appid>/`

Mac 微信缓存的 wxapkg 是 `V1MMWX` 加密（安卓同款）：偏移 0x400 起整段 XOR 0x33 即可重建文件索引，`node unpack.js <file.wxapkg> <outdir>` 解包。

### 第 1 步：信任 mitmproxy 证书（一次性）

```bash
mitmdump --set confdir=$PWD/mitmca &   # 生成 CA 后 Ctrl+C
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain $PWD/mitmca/mitmproxy-ca-cert.pem
```
（用户钥匙串亦可：`security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db ...`）

### 第 2 步：抓首次 token + 用户参数

1. 启动抓包：
```bash
mitmdump -s token_grab.py --listen-port 8080 \
  --set confdir=$PWD/mitmca --set block_global=false \
  --allow-hosts 'codoon|igofit' &
networksetup -setwebproxy "Wi-Fi" 127.0.0.1 8080
networksetup -setsecurewebproxy "Wi-Fi" 127.0.0.1 8080
```
2. 让用户在 **Mac 微信**打开一次「企业咕咚」小程序（搜索或 侧边栏→发现→小程序）。小程序登录时 `token_grab.py` 自动写 `token.txt`。
3. 抓完后立刻关代理：
```bash
networksetup -setwebproxystate "Wi-Fi" off
networksetup -setsecurewebproxystate "Wi-Fi" off
pkill -f mitmdump
```
4. 从抓包记录里取用户参数（也可解包 wxapkg 后让用户跑一次真跑抓包对照）：
   - `user_id`：所有请求 query 里的 `platform_user_id`（UUID）
   - `club_id`：请求 query 里的 `club_id`（浙大为 48472）
5. 生成配置：`cp config.example.json config.json` 并填写。

### 第 3 步：路线模板

`route_template.json` 是 `[[lat,lon],...]` 折线（总长 ≥3km）。默认为玉泉校区某真实道路环线。获取自己学校的：在 detail 接口 `GET /v1/open/get_user_gps_info/detail?route_id=<任一真实记录>` 响应的 `point_list_view` 里提取坐标即可（该接口有负载均衡抖动，取空了重试几次）。

### 第 4 步：试跑与验收

```bash
python3 forge2.py --dry        # 看合成几何/坐标范围
python3 -u forge2.py           # 真实提交(约17分钟实时, 中途勿断)
```
验收（小程序内）：记录详情页应有 **地图+蓝色轨迹线**（数据源 `point_list_view`）和 **轨迹图**（分享图）。再核对本列表接口：
```bash
curl -H "Authorization: Bearer $(cat token.txt)" \
"https://mini-club.codoon.com/v1/statistic/get_user_gps_info/list?club_id=<CLUB_ID>&platform_user_id=<UID>&platform_source_type=0&platform_language=zh&platform_app_brand=<BRAND>&cursor=0&limit=3&sports_type=1"
```
新记录 `is_fraud` 应为 `false`。

### 第 5 步：每日自动化

由 agent 的定时能力（或 cron）在目标时段触发：
```bash
bash daily_checkin.sh    # 防重→随机延时60~2159s→必要时续期→提交
```
token 续期依赖**用户在 Mac 微信里打开一次小程序**（token 过期后小程序会自动重新登录并被截获）。agent 可在续期时唤起已打开的小程序窗口（AppleScript AXRaise，需辅助功能授权 osascript），或提示用户手动打开。

## Windows 部署

Windows 版入口：`refresh.ps1`（续期）与 `daily_checkin.ps1`（每日打卡），共享 `check_status.py` 做状态查询。

### 环境

```powershell
pip install mitmproxy pillow
```

### 证书（管理员，一次性）

先生成 CA（运行一次 refresh.ps1 失败退出即可生成 `mitmca\`），然后：
```powershell
certutil -addstore -f ROOT mitmca\mitmproxy-ca-cert.cer
```

### 抓首次 token / 续期

```powershell
powershell -ExecutionPolicy Bypass -File refresh.ps1
```
脚本会开双栈代理（WinINET 注册表 + winhttp），提示时**在 Windows 微信打开一次企业咕咚小程序**，捕获后自动关代理。

### 每日自动化（任务计划程序）

```powershell
schtasks /create /tn "gdty-checkin" /tr "powershell -ExecutionPolicy Bypass -File C:\path\to\daily_checkin.ps1" /sc daily /st 14:00
```

### Windows 注意事项

1. **待实测项**：Windows 微信的小程序流量是否吃系统代理并信任用户 CA（macOS 版实测均吃；若小程序转圈=代理指到了死端口，先关代理放行）
2. `forge2.py`/`route_img.py` 跨平台无改动；字体自动探测（雅黑/苹方/系统字体）
3. 触发时电脑需开机且微信保持登录；续期时需要有人点开一次小程序（或用 UIAutomation 自动化，自行取舍）

## 反检测红线（重要，违反会被静默丢点或标作弊）

点位指纹——`mkpoint()` 的字段取值经过服务端实测验证，**不要"优化"**：

1. `distance` 是**本段位移**(8~16m)，不是累计里程
2. `h_accuracy` 恒为 0；`v_accuracy` 是 ≈3.0 的**浮点**
3. 必须带 `"gyroscope": ""` 字段；普通点 `type`=0、首点=1、收尾点=5
4. 点间隔 **3~7 秒随机**（真实 iPhone 约 4~8 秒一个点；精确 1000ms 的 1Hz 是机器人指纹，会被整条丢弃、完成时报"数据太少"）
5. 提交必须**实时**（点的时间戳与 HTTP 到达时间对齐，跑多久挂多久）
6. 坐标噪声单位是**米**，要除以 111320（纬）/85200（经）转度；直接加"度"会变成百公里级瞬移
7. 配速贴近用户真实历史；步频 ~157spm 持续上报
8. `location` 字段是**字符串**（空串）；GET 类接口要带 `club_id`

其他纪律：每天最多 1 条有效（≥3km 且单公里配速 <10 分钟）；别每天同一时刻固定刷；`completes_route` 响应 `ok:true` 且 `route_id:0` 是**失败**。

## 故障排查

| 症状 | 原因/处理 |
|---|---|
| 完成时报"数据太少" | 点被服务端丢弃——检查时间戳抖动/批量随机性（红线 4） |
| 详情页地图空白 | 点位指纹不对，`point_list_view` 没生成——核对红线 1~3 |
| 列表里查不到新记录 | `complete` 响应 route_id 是 0，未真完成；重试 completes_route |
| 详情接口返回空 | 该接口负载均衡抖动，重试即可 |
| token 401 | 已过期（25h）；跑 `./refresh.sh` 让用户开一次小程序 |
| 小程序打开转圈 | 代理指向了死掉的 mitmdump——`networksetup -setsecurewebproxystate "Wi-Fi" off` 放行后修 mitm（注意用绝对路径启动 `-s`） |
| 删除记录 | 进行中：`completes_route {is_delete:true}`；已完成：`POST /v1/statistic/delete_user_route {"id":<数字记录ID>,"club_id":<CLUB_ID>}` |

## 免责声明

本项目仅用于网络安全与小程序协议研究学习。使用者因使用本工具产生的一切后果（包括但不限于学校处分）自负。
