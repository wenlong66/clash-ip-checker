# How to 从青云梯极速版提取本地 Clash 配置

适用于自己的青云梯账号及本机客户端。目标是读取已经加载的节点配置，导出为 Clash Verge 可导入的 YAML。**导出结果是静态配置，不是可自动更新的订阅地址。**

## 网页操作

在本仓库运行 `python web.py`，打开 [梯子导出](http://127.0.0.1:18080/qingyunti)，点击「提取并预览」，成功后可下载或直接导入 Clash。网页服务需与梯子客户端运行在同一台 Windows 电脑上，且仅允许本机访问。提取结果只保存在服务内存中，不写文件；再次提取或重启服务后，旧导入链接失效。

脚本也支持省略 PID 自动识别唯一的 ApexCore；`--stdout` 仅将 YAML 写到标准输出，不保存文件。下面保留手动指定 PID 的命令行流程。

## 已验证的环境与结果

2026-11-13，Windows，青云梯极速版 7.2.5，ApexCore v1.19.29，Clash Verge 内核 Mihomo v1.19.33，Python 3.11，已安装 PyYAML。

- 从 ApexCore 私有内存中的完整配置提取到 62 个 VLESS 节点，保留节点组和分流规则。
- 用 Clash Verge 内核通过配置检查。
- 修正 DNS 后，抽测香港-01、新加坡-01、日本-10连接成功；美国-01本次失败。没有测试全部节点，也没有替用户切换连接。
- 导出文件为本目录下的 `qingyunti-clash.yaml`，包含节点凭据，已由仓库忽略，不提交到 Git。
- 本目录的脚本从本次成功操作整理而来，增加了进程路径校验；离线测试覆盖解析和配置整理，整理后的脚本没有再次执行现场内存扫描。

## 准备条件

1. 保持青云梯已登录、节点已加载，最好保持连接；先不要卸载或退出。
2. 核实内核路径为 `D:\Program Files (x86)\青云梯-极速版\ApexCore.exe`。脚本会校验 PID 对应路径，避免误读其他程序；迁移安装目录后需先更新脚本内 `APEX_CORE`。
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

- 删除青云梯运行时使用的控制地址、API 密钥、监听端口、TUN 和网卡绑定字段，让 Clash Verge 使用自己的设置。
- 将 `dns.proxy-server-nameserver` 改为 `[system]`；保留其余 DNS 设置、节点、节点组和分流规则。
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

本次已在 `F:\web\temp\qingyunti-clash-check` 目录备好 GeoSite.dat 和 geoip.metadb，可用于配置检查；该本地目录不随仓库分发：

```powershell
& 'D:\Program Files\Clash Verge\verge-mihomo.exe' -t -d 'F:\web\temp\qingyunti-clash-check' -f 'F:\web\clash-ip-checker\qingyunti-export\qingyunti-clash.yaml'
```

看到 `test is successful` 表示配置可解析，**不代表节点已经联网成功**。如果检查数据目录丢失，本次使用的数据源位于：

```text
D:\Program Files (x86)\青云梯-极速版\data\flutter_assets\assets\data\GeoSite.dat
D:\Program Files (x86)\青云梯-极速版\data\flutter_assets\assets\data\geoip.metadb
```

把这两个文件复制到检查数据目录后再运行，不要修改正在使用的 Clash 数据目录。

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
| 配置检查成功，节点测试失败 | 检查专用 DNS 是否仍残留，确认 `[system]` 修正，然后更换节点实测。单个节点失败不代表整个导出失败。 |
| GeoSite / GEOIP 数据加载失败 | 补齐检查目录中的数据文件，或检查 Clash 自己的数据文件是否可用。 |
| 下次节点失效、套餐或节点变更 | 静态文件不会更新。让青云梯加载当前配置后重新提取，并重新导入 Clash。 |

## 为什么不直接找订阅链接

已检查过的本地偏好文件位于：

```text
C:\Users\long\AppData\Roaming\com.qytapp.clients.apex\青云梯-极速版\shared_preferences.json
```

其中 `flutter.xboard_domain_subscription.subscribeUrl` 与配置中的 profile URL 使用 `apex-url-v2:` 加密封装。它不是可直接导入 Clash 的 HTTPS 链接。本次用当前 Windows 用户的安全存储解开过封装，但其中是 `test.example.com` 占位地址，不是有效订阅服务器。不能仅凭字段名宣称拿到了真实订阅。

ApexCore 的启动参数包含 `-f -`，配置从标准输入加载；本地没有现成的节点 YAML。控制接口需要认证，因此最终有效的迁移方式是读取运行中已加载的完整配置，并移除客户端运行时字段。

## 适用范围

这是本次版本和机器上验证过的流程。脚本依赖一段完整、以空字节分隔的 UTF-8 YAML/JSON 仍留在单个已提交私有内存区域中，只检查小于等于 256 MiB 的区域与配置标记附近 2 MB 的候选数据。客户端升级或内存回收可能使它失效。

不要将脚本用于未经授权的其他进程；它也不会自动获取、续期或生成新的订阅。
