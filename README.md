# ZJU gdty fake run

浙大「浙大体艺」（企业咕咚）校园跑自动打卡工具链。**协议级实现，支持 macOS 与 Windows**：不依赖手机、不需要越狱/辅助功能/虚拟定位，直接伪造小程序的跑步上传协议。

> 适用于：HarmonyOS NEXT / 无 root 安卓 / 任何装了桌面版微信（Mac 或 Windows）的场景（手机侧无解时换赛道打协议）。
> 风险自担：刷跑属于违反学校规定的行为，被认定通常导致体育成绩作废。本仓库仅供学习逆向与协议分析。

---

## 本文档的读法

**本文档写给 AI agent（Claude Code / Cursor / ZCode 等）直接执行。** 人类读者也可照做。agent 的任务：在用户的电脑（macOS 或 Windows）上完成环境搭建、凭据采集、配置生成，然后交给定时任务每日运行。协议细节、反检测红线、故障排查全部在文内，不需要额外上下文。

两平台共用同一套 Python 核心（`forge2.py` / `route_img.py` / `check_status.py` 跨平台零改动），差异只在**证书导入、代理开关、每日调度**三处：

| 环节 | macOS | Windows |
|---|---|---|
| 环境安装 | `brew install mitmproxy` + pillow | `pip install mitmproxy pillow` |
| 信任 CA（一次性） | `security add-trusted-cert` | `certutil -user -addstore ROOT` |
| 抓/续 token | `refresh.sh`（`networksetup` 切系统代理） | `refresh.ps1`（改 WinINET 注册表，结束必恢复原值） |
| 每日入口 | `daily_checkin.sh`（cron/launchd/agent 定时器触发） | `daily_checkin.ps1`（任务计划程序触发） |
| 状态查询 | `check_status.py dedup / remaining` | 同左 |

## 工作原理（一分钟版）

小程序（uni-app 编译包，appid `wx2961574bbec73239`）与后端 `mini-club.codoon.com` 通信，Bearer JWT 鉴权（25 小时有效）。跑步数据流程：

```
POST /v1/route/start_route            -> 拿 route_id
POST /v1/route/create_route_point     -> 逐批上传 GPS 点(进行中实时)
POST /v1/route/create_route_gyroscope_steps -> 步数上报(每间隔的增量)
POST /v1/route/completes_route        -> 完成(响应 route_id != 0 才是真成功)
GET  /v1/common/oss_signature         -> 轨迹图直传凭证
POST /v1/route/create_route_image_url -> 挂载轨迹图
```

本工具链：`forge2.py` 沿真实校内道路折线合成轨迹并实时提交；`route_img.py` 用腾讯地图瓦片画轨迹图传 OSS 挂载；`token_grab.py`+`refresh.sh`/`refresh.ps1` 解决 25 小时 token 续期；`daily_checkin.sh`/`daily_checkin.ps1` 是每日入口。

## 文件清单

| 文件 | 作用 |
|---|---|
| `forge2.py` | 主程序：合成轨迹并提交（`--dry` 只看几何不上传） |
| `route_img.py` | 轨迹图生成（腾讯瓦片底图+蓝线）+ OSS 直传 + 挂载 |
| `token_grab.py` | mitmproxy 插件，自动截获 auth/login 保存 token |
| `refresh.sh` | macOS 一键续期：开代理→等小程序打开→抓 token→关代理 |
| `refresh.ps1` | Windows 一键续期：临时代理（WinINET）→抓 token→恢复原代理 |
| `daily_checkin.sh` / `daily_checkin.ps1` | 每日入口（bash / PowerShell）：防重→随机延时→必要时续期→提交 |
| `check_status.py` | 跨平台状态查询（防重 / token 剩余），调度脚本共用 |
| `tests/test_step_reporting.py` | 离线回归测试（不需网络/配置/凭据） |
| `unpack.js` | wxapkg 解包器（研究协议用） |
| `route_template.json` | 校内道路折线模板（217 点/3018m，可替换） |
| `config.example.json` | 配置模板 |

## Agent 部署流程

第 0~2 步按当前平台二选一执行；第 3~4 步两平台完全一致；第 5 步按平台选调度方式。

### 第 0 步：环境

**macOS**
```bash
brew install mitmproxy cliclick   # cliclick 仅自动唤起微信时需要
python3 -c "import PIL" || pip3 install --user pillow
```

**Windows**（PowerShell，Python 3.8+；`python` 不在 PATH 时调度脚本自动回退 `py -3`）
```powershell
pip install mitmproxy pillow
```

克隆后先跑离线自检（验证步数增量上报逻辑，不需网络与任何配置）：
```bash
python3 -m unittest discover -s tests
```

**小程序包缓存（仅研究/排错用，部署不需要）**
- macOS：`~/Library/Containers/com.tencent.xinWeChat/Data/Documents/app_data/radium/users/<微信内部哈希>/applet/packages/<appid>/`。Mac 微信缓存的 wxapkg 是 `V1MMWX` 加密（安卓同款）：偏移 0x400 起整段 XOR 0x33 即可重建文件索引，`node unpack.js <file.wxapkg> <outdir>` 解包。
- Windows：微信 3.x 缓存在 `Documents\WeChat Files\Applet\<appid>\`，wxapkg 通常未加密、可直接 `node unpack.js`；4.x 目录结构有变动，按需摸索。

### 第 1 步：信任 mitmproxy 证书（一次性）

**macOS**
```bash
mitmdump --set confdir=$PWD/mitmca &   # 生成 CA 后 kill %1
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain $PWD/mitmca/mitmproxy-ca-cert.pem
```
（用户钥匙串亦可：`security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db ...`）

**Windows**（导入当前用户信任区，不需管理员）。先生成 CA：
```powershell
$p = Start-Process mitmdump -ArgumentList @('--set', "confdir=$PWD\mitmca") -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 5; Stop-Process -Id $p.Id
```
（等价做法：直接跑一次 `refresh.ps1`，120 秒超时退出时 `mitmca\` 已生成。）然后导入：
```powershell
certutil -user -addstore -f ROOT mitmca\mitmproxy-ca-cert.cer
```

### 第 2 步：抓首次 token + 用户参数

**macOS**
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

**Windows**
```powershell
powershell -ExecutionPolicy Bypass -File refresh.ps1
```
脚本自动完成 macOS 版 1~3 步：启动 mitmdump（同参数，日志落 `mitm_refresh.log` / `mitm_refresh.err.log`）→ 临时把当前用户 WinINET 代理指向 `127.0.0.1:8080` → 提示时**在 Windows 微信打开一次「企业咕咚」小程序**（`token_grab.py` 截获 auth/login 写 `token.txt` 并落 `token.fresh` 标记）→ 恢复原代理。**无论成功、超时还是出错，finally 里都会恢复原代理设置**；不碰 WinHTTP。120 秒没抓到 token 抛错退出。

**用户参数（两平台一致）**，从抓包记录里取（macOS 看运行 mitmdump 的终端，Windows 看 `mitm_refresh.log`；也可解包 wxapkg 后让用户跑一次真跑抓包对照）：
- `user_id`：所有请求 query 里的 `platform_user_id`（UUID）
- `club_id`：请求 query 里的 `club_id`（浙大为 48472）

生成配置：`cp config.example.json config.json`（Windows `copy config.example.json config.json`）并填写。

### 第 3 步：路线模板

`route_template.json` 是 `[[lat,lon],...]` 折线（总长 ≥3km）。默认为玉泉校区某真实道路环线。获取自己学校的：在 detail 接口 `GET /v1/open/get_user_gps_info/detail?route_id=<任一真实记录>` 响应的 `point_list_view` 里提取坐标即可（该接口有负载均衡抖动，取空了重试几次）。

### 第 4 步：试跑与验收

```bash
python3 forge2.py --dry        # Windows: python forge2.py --dry
python3 -u forge2.py           # 真实提交(约17分钟实时, 中途勿断)
```
验收（小程序内）：记录详情页应有 **地图+蓝色轨迹线**（数据源 `point_list_view`）和 **轨迹图**（分享图）。再核对本列表接口：
```bash
curl -H "Authorization: Bearer $(cat token.txt)" \
"https://mini-club.codoon.com/v1/statistic/get_user_gps_info/list?club_id=<CLUB_ID>&platform_user_id=<UID>&platform_source_type=0&platform_language=zh&platform_app_brand=<BRAND>&cursor=0&limit=3&sports_type=1"
```
新记录 `is_fraud` 应为 `false`。

### 第 5 步：每日自动化

**macOS**：由 agent 的定时能力（或 cron/launchd）在目标时段触发：
```bash
bash daily_checkin.sh    # 防重→随机延时60~2159s→必要时续期→提交
```
token 续期依赖**用户在 Mac 微信里打开一次小程序**（token 过期后小程序会自动重新登录并被截获）。agent 可在续期时唤起已打开的小程序窗口（AppleScript AXRaise，需辅助功能授权 osascript），或提示用户手动打开。

**Windows**：任务计划程序：
```powershell
schtasks /create /tn "gdty-checkin" /tr "powershell -ExecutionPolicy Bypass -File C:\path\to\daily_checkin.ps1" /sc daily /st 14:00
```
`daily_checkin.ps1` 流程：`check_status.py remaining` 读 token 剩余（不足 2 小时先跑 `refresh.ps1`，续期失败直接中止，不拿残 token 硬提交）→ `check_status.py dedup` 防重（今日已有 ≥3km 记录则跳过）→ 随机延时 60~2160s → 提交前再校验剩余 >25 分钟 → `python -u forge2.py`。全程 Start-Transcript 落 `daily_YYYYMMDD.log`，任一环节失败即抛错退出。

**Windows 注意事项**
1. 触发时电脑需开机且微信保持登录；续期时需要有人点开一次小程序（或用 UIAutomation 自动化，自行取舍）
2. `refresh.ps1` 的代理恢复在 finally 里；若 PowerShell 进程本身被强杀（断电/任务管理器结束进程），代理可能停留在 `127.0.0.1:8080`——手动关掉（设置→网络→代理→关，或 `Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Value 0`）再排查
3. `forge2.py` / `route_img.py` 跨平台无改动；字体自动探测（雅黑/苹方/系统字体）；轨迹点临时文件走 `tempfile.gettempdir()`

## 反检测红线（重要，违反会被静默丢点或标作弊）

点位指纹——`mkpoint()` 的字段取值经过服务端实测验证，**不要"优化"**：

1. `distance` 是**本段位移**(8~16m)，不是累计里程
2. `h_accuracy` 恒为 0；`v_accuracy` 是 ≈3.0 的**浮点**
3. 必须带 `"gyroscope": ""` 字段；普通点 `type`=0、首点=1、收尾点=5
4. 点间隔 **3~7 秒随机**（真实 iPhone 约 4~8 秒一个点；精确 1000ms 的 1Hz 是机器人指纹，会被整条丢弃、完成时报"数据太少"）
5. 提交必须**实时**（点的时间戳与 HTTP 到达时间对齐，跑多久挂多久）
6. 坐标噪声单位是**米**，要除以 111320（纬）/85200（经）转度；直接加"度"会变成百公里级瞬移
7. 配速贴近用户真实历史；步频 ~157spm（2.62 步/秒）持续上报。`create_route_gyroscope_steps` 的 `cur_steps` 是**本上报间隔的增量步数**（≈ `dur`×2.62，`dur` 为间隔秒数），不是累计值——有离线回归测试守护（`tests/test_step_reporting.py`）
8. `location` 字段是**字符串**（空串）；GET 类接口要带 `club_id`

其他纪律：每天最多 1 条有效（≥3km 且单公里配速 <10 分钟）；别每天同一时刻固定刷；`completes_route` 响应 `ok:true` 且 `route_id:0` 是**失败**。

## 故障排查

| 症状 | 原因/处理 |
|---|---|
| 完成时报"数据太少" | 点被服务端丢弃——检查时间戳抖动/批量随机性（红线 4） |
| 详情页地图空白 | 点位指纹不对，`point_list_view` 没生成——核对红线 1~3 |
| 列表里查不到新记录 | `complete` 响应 route_id 是 0，未真完成；重试 completes_route |
| 详情接口返回空 | 该接口负载均衡抖动，重试即可 |
| token 401 | 已过期（25h）；macOS 跑 `./refresh.sh`、Windows 跑 `refresh.ps1`，让用户开一次小程序 |
| 小程序打开转圈 | 代理指向了死掉的 mitmdump——macOS：`networksetup -setsecurewebproxystate "Wi-Fi" off`；Windows：把 `ProxyEnable` 置 0（见 Windows 注意事项 2）。放行后修 mitm（注意用绝对路径启动 `-s`） |
| Windows 全网断连 | `refresh.ps1` 被强杀导致代理停在 8080 死端口——按 Windows 注意事项 2 关掉代理即恢复 |
| 删除记录 | 进行中：`completes_route {is_delete:true}`；已完成：`POST /v1/statistic/delete_user_route {"id":<数字记录ID>,"club_id":<CLUB_ID>}` |

## 免责声明

本项目仅用于网络安全与小程序协议研究学习。使用者因使用本工具产生的一切后果（包括但不限于学校处分）自负。
