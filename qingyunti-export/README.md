# How to 从青云梯极速版提取本地 Clash 配置

适用于自己的青云梯账号及本机客户端。目标是读取已经加载的节点配置，导出为 Clash Verge 可导入的 YAML。**导出结果是静态配置，不是可自动更新的订阅地址。**

## 网页操作

在本仓库运行 `python web.py`，打开 [梯子导出](http://127.0.0.1:18080/qingyunti)，点击「提取并预览」，成功后可下载或直接导入 Clash。网页服务需与梯子客户端运行在同一台 Windows 电脑上，提取和更新操作仅允许本机访问；新建导入地址自动使用本机局域网 IPv4，局域网设备持完整地址可下载订阅。提取结果保存在本机 `private_exports` 目录，包含节点凭据，请勿分享。新建配置使用独立地址；选择「更新已有」再提取时复用原地址，随后在导出预览点击「更新订阅」，无需再到 Clash 操作或重新导入。再次提取或重启服务不会使已保存的地址失效，下载和更新时需保持服务运行。旧版临时链接升级后需重新导入一次。

## 独立使用 Clash / Shadowrocket

Clash 导出完整 YAML，保留源节点、DNS、嗅探、规则及可迁移的 TUN 设置。按路径与 PID 校验读取运行内核 `-d` 目录中的数据库，将 GeoSite／GeoIP 分类等价改写为内嵌规则集，保留规则位置、出口与 `no-resolve`，不依赖或覆盖 Clash 的共享数据库；不使用安装目录的随附旧库冒充当前数据库。移除 API、监听地址、DNS 监听端口和客户端专属 TUN 设备/文件描述符，不再强制替换源 `proxy-server-nameserver`；节点实际 IP 仍写入 `hosts` 并开启 hosts 查询。导入后检查 Clash 的 TUN 开关、全局覆写和扩展脚本，避免它们改变最终配置，不要与青云梯同时接管系统代理/TUN。旧配置需重新提取。

Shadowrocket 分别提供两份文件：

- **节点订阅 `.txt`**：`qingyunti-shadowrocket.txt`，可上传服务器 VPN 后台更新节点。保留实际服务器 IP、UUID、TLS/SNI、Vision flow、证书校验和 UDP 参数，不携带 DNS 或分流规则，单独更新 TXT 不改变现有配置。多个服务器 IP 使用首个地址。
- **DNS 与分流 `.conf`**：`qingyunti-shadowrocket-rules.conf`，仅包含 `[General]`、`[Rule]`、`[Host]`，不包含节点定义或节点凭据。源代理出口统一映射为内置 `PROXY`（当前选中节点），保留直连/拦截，不复制自动选择或故障转移组。

**需要分别导入**：先用 TXT 导入/更新节点并选中一个可用节点，再在小火箭「配置」页导入并启用 CONF，将全局路由设为「配置」。启用新配置会切换当前 DNS 与分流，不自动合并旧规则；请先保留原配置，出现问题可切回。只想更新节点时无需导入 CONF。

新导出已内嵌所用 GeoSite／GeoIP 分类，生成 CONF 不再依赖原数据库；旧导出仍含 GeoSite 引用时，需要运行中的青云梯内核提供原始数据库。数据库缺失、DNS 内含暂不支持的 Geo 分类依赖或遇到不支持的规则时会报错，不静默丢弃。生成的文件已内嵌规则，日常连接不依赖原客户端、GeoSite 文件或网页服务。

锚定且可有限展开的域名正则（字符范围、简单分支、有界重复）精确转换为 `DOMAIN`／`DOMAIN-SUFFIX`，在原位置保留出口，适用于所有协议；每条最多展开 1024 个域名，避免配置膨胀。含逗号的单字符/字符类重复量词会安全改写，不再因配置分隔符而直接阻断导出。跨内核转换仍不能保证完全等价：其余正则近似转为 HTTP/HTTPS `URL-REGEX`，文件头标明数量，受小火箭 URL 识别能力限制，其他协议不能等价匹配；DNS 引导、Fake-IP 地址段、嗅探和规则优先级由小火箭处理，旧文件中的 GeoIP 引用还可能受小火箭数据库影响；多个 Host IP 只保留首个。差异也写在文件头，不自动开启 MITM。CONF 虽无节点凭据，仍可能包含私有 DNS 地址和 Host 映射，请勿公开。节点、IP 或源策略变化后重新提取并导入对应文件。

主备切换页面新增「现有策略 / 青云梯策略」。青云梯策略使用主用订阅的完整连接设置和分流顺序，把代理出口统一替换为所选主备节点，不混入 Loyalsoldier 规则或备用订阅的策略。先把完整青云梯 YAML 导入 Clash，再将它作为主用订阅；备用服务器域名单独使用其原订阅的节点 DNS（未指定则使用普通 DNS，再缺省为系统 DNS），不废弃青云梯专用 DNS，也不改变网站解析。IP 节点和已有 hosts 映射不增加例外；不支持的 DNS 依赖或冲突会明确拒绝，不影响 Loyalsoldier 策略。源配置和节点变化后重新生成并更新主备配置。

脚本也支持省略 PID 自动识别唯一的 ApexCore；`--stdout` 仅将 YAML 写到标准输出，不保存文件。下面保留手动指定 PID 的命令行流程。

## 已验证的环境与结果

2026-11-13，Windows，青云梯极速版 7.2.5，ApexCore v1.19.29，Clash Verge 内核 Mihomo v1.19.33，Python 3.11，已安装 PyYAML。

- 从 ApexCore 私有内存中的完整配置提取到 62 个 VLESS 节点，保留节点组和分流规则。
- 用 Clash Verge 内核通过配置检查。
- 修正 DNS 后，抽测香港-01、新加坡-01、日本-10连接成功；美国-01本次失败。没有测试全部节点，也没有替用户切换连接。
- 导出文件为本目录下的 `qingyunti-clash.yaml`，包含节点凭据，已由仓库忽略，不提交到 Git。
- 本目录的脚本从本次成功操作整理而来，增加了进程路径校验；离线测试覆盖解析和配置整理，整理后的脚本没有再次执行现场内存扫描。

2026-11-18 复查：ApexCore 与 Clash Verge 内核均为 v1.19.33。仅将节点 DNS 改为 `[system]` 不再可靠：系统 DNS 对节点服务器域名返回空结果或不可用地址，而 Apex 已建立的连接仍正常。现在导出时按节点端口读取 Apex 已建立 TCP 连接的实际 IP，并写入配置的 `hosts`，保留节点域名、TLS servername 和凭据。香港-01、新加坡-01、日本-10在隔离 Mihomo 中连接成功；美国-01在 Apex 自身也测试失败。离线回归测试及实际提取流程已通过。

## 准备条件

1. 保持青云梯已登录并连接节点，在 Apex 代理下打开网页，保持连接到提取结束。脚本需要已建立的节点连接来获取实际服务器地址；目前同一服务器域名下的节点只需连接其中一个。
2. 核实内核路径为 `D:\Users\long\AppData\Local\Programs\青云梯-极速版\ApexCore.exe`。脚本会校验 PID 对应路径，避免误读其他程序；迁移安装目录后需先更新 `utils/qingyunti_geodata.py` 中的 `APEX_CORE`。数据库目录从该内核的 `-d` 参数读取，不从安装目录猜测。
3. 使用本机已安装的 Python：`C:\Python311\python.exe`。可运行以下命令确认依赖，本次无需安装新依赖：

```powershell
& 'C:\Python311\python.exe' -c "import yaml; print(yaml.__version__)"
```

该操作仅以查询和读取权限访问 ApexCore，不注入代码、不修改内存，不保存完整内存转储。读取过程中可能接触敏感数据，最终只写出解析通过的配置；YAML 本身包含节点凭据，不能公开分享。权限受限时只在明确授权后使用提升权限的终端；不要关闭系统安全防护。

## 三步提取

### 1. 确认当前 PID

在 PowerShell 中运行：

```powershell
Get-Process -Name ApexCore | Select-Object Id, Path
```

确认路径对应上述青云梯安装目录。PID 每次启动可能改变，**不要照抄历史 PID**；多个内核同时运行时逐个核实路径和所属实例。

### 2. 执行只读提取

下面命令会自动获取唯一的 ApexCore 进程。多个实例时会停止，请先确认要提取哪个实例。

```powershell
$apexProcesses = @(Get-Process -Name ApexCore -ErrorAction Stop)
if ($apexProcesses.Count -ne 1) { throw '存在多个 ApexCore，请先核实目标实例' }
& 'C:\Python311\python.exe' -X utf8 'F:\web\clash-ip-checker\qingyunti-export\extract.py' $apexProcesses[0].Id
```

成功时显示节点数及输出文件路径。输出固定为本目录下的 `qingyunti-clash.yaml`，**重复执行会覆盖本目录中的上一次导出**；需要保留旧节点时先复制备份。

脚本自动完成以下整理：

- 删除青云梯运行时使用的控制地址、API 密钥、监听端口和网卡绑定字段；TUN 保留启用状态、协议栈、路由及 DNS 劫持等可迁移设置，移除专属设备名及文件描述符，Clash Verge 的开关和覆写仍可能影响实际运行。
- 保留源 DNS（移除其本地 `listen`），并将 Apex 已建立节点连接的实际 IP 写入配置的 `hosts`、开启 hosts 查询，避免节点域名解析失败；保留节点、节点组、嗅探和分流规则。
- 地址映射是静态快照，服务商更换服务器 IP 后需要重新连接 Apex 并提取；不修改 Windows hosts 或系统 DNS。
- 不输出完整节点内容、UUID、订阅令牌或密码。

### 3. 导入并验证

在 Clash Verge 的订阅页导入本地文件：

```text
F:\web\clash-ip-checker\qingyunti-export\qingyunti-clash.yaml
```

选择节点测试。切换系统代理时避免两个客户端同时反复接管；确认 Clash 可用后再退出青云梯。重新提取需要再次启动青云梯并加载最新节点。

## 配置检查与离线测试

检查脚本的解析和整理逻辑，不读取进程：

```powershell
Set-Location -LiteralPath 'F:\web\clash-ip-checker\qingyunti-export'
& 'C:\Python311\python.exe' -X utf8 -m unittest -v test_extract.py
```

可使用独立的本地目录进行配置检查，例如已有的 `F:\web\temp\qingyunti-clash-check`；该目录不随仓库分发，不要使用正在运行的 Clash 数据目录：

```powershell
& 'D:\Program Files\Clash Verge\verge-mihomo.exe' -t -d 'F:\web\temp\qingyunti-clash-check' -f 'F:\web\clash-ip-checker\qingyunti-export\qingyunti-clash.yaml'
```

看到 `test is successful` 表示配置可解析，**不代表节点已经联网成功**。新导出已内嵌所用 GeoSite／GeoIP 分类，无需为这些规则复制数据库。旧文件仍依赖共享 Geo 数据库时，应重新提取以固化当前运行内核的数据，不要用安装目录的随附数据库代替。

## 现场联网验证的做法

本次启动了一个临时的标准 Mihomo 测试进程，仅绑定两个空闲的 `127.0.0.1` 端口，未修改 Windows 系统代理和系统 DNS，也未使用青云梯的 7892 / 7275 端口。

测试配置仅包含 4 个被测节点、一个 select 组、`MATCH` 规则，以及修正后的 DNS；通过临时控制接口 `/proxies/{节点名}/delay` 检查对 `https://cp.cloudflare.com/generate_204` 的连接，超时设置为 10000 毫秒。节点名称需进行 URL 编码。测试结束后终止临时进程，删除临时凭据配置和日志。

本次记录保存在本机 `F:\web\temp\qingyunti-clash-check\test-results.json`，不随仓库分发。普通使用可以直接在 Clash Verge 中测试，无需重建临时测试接口。

## 常见问题

| 现象 | 原因或处理 |
| --- | --- |
| `Access is denied` / 访问被拒绝 | 当前用户无读取权限或被沙箱限制。明确授权后再提升执行权限；不能借其他工具绕过拒绝。 |
| 自动审批拒绝内存读取 | 本次曾因扫描可能接触无关敏感数据而被拦截；停止操作、说明范围与风险，并获得用户明确同意后才重新申请执行。后续授权仍不能保证审批通过。 |
| `PID does not belong...` | PID 已变化、选错实例或安装目录变化。重新查询进程路径，不要跳过校验。 |
| `No complete config found...` | 节点尚未加载、配置被垃圾回收或客户端布局变化。保持连接再试；仍失败需重新分析版本，不要把失败输出当有效配置。 |
| 配置检查成功，节点测试失败 | 重新连接 Apex 并打开网页后提取，确认导出包含节点服务器的 `hosts` 地址映射。仅有 `[system]` DNS 设置不能保证连接成功。单个节点失败也可能是节点本身故障。 |
| 提示未找到活动连接或无法唯一匹配节点地址 | 保持 Apex 有网页流量后重试。各服务器域名需要对应的活动节点连接；若不同域名使用相同端口，脚本会拒绝猜测地址，需要适配客户端。 |
| GeoSite / GeoIP 数据读取或固化失败 | 保持已核实的青云梯内核运行并重新提取；检查其 `-d` 数据目录和分类是否完整，不替换 Clash 共享数据库。 |
| 下次节点失效、套餐或节点变更 | 静态文件不会更新。让青云梯加载当前配置后重新提取，并重新导入 Clash。 |

## 为什么不直接找订阅链接

已检查过的本地偏好文件位于：

```text
C:\Users\long\AppData\Roaming\com.qytapp.clients.apex\青云梯-极速版\shared_preferences.json
```

其中 `flutter.xboard_domain_subscription.subscribeUrl` 与配置中的 profile URL 使用 `apex-url-v2:` 加密封装。它不是可直接导入 Clash 的 HTTPS 链接。本次用当前 Windows 用户的安全存储解开过封装，但其中是 `test.example.com` 占位地址，不是有效订阅服务器。不能仅凭字段名宣称拿到了真实订阅。

ApexCore 的启动参数包含 `-f -`，配置从标准输入加载；本地没有现成的节点 YAML。控制接口需要认证，因此最终有效的迁移方式是读取运行中已加载的完整配置，并移除客户端运行时字段。

## 适用范围

这是本次版本和机器上验证过的流程。脚本只检查小于等于 256 MiB 的已提交私有内存区域：读取完整的空字节分隔 YAML／JSON，或在配置标记附近 2 MB 范围内按 JSON 边界恢复完整对象，最多检查 512 个对象起点。客户端升级、配置跨越内存区域或内存回收仍可能使提取失效。

不要将脚本用于未经授权的其他进程；它也不会自动获取、续期或生成新的订阅。
