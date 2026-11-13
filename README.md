# 🚀 Clash Node IP CHECKER

[中文](README.md) | [English](README_EN.md) | [官网](https://tombcato.github.io/clash-ip-checker/) | [Docker部署](https://github.com/tombcato/clash-ip-checker/tree/docker)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
[![Twitter](https://img.shields.io/badge/Twitter-%40hibearss-1DA1F2?style=flat&logo=twitter&logoColor=white)](https://x.com/hibearss)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk9OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTk4IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/tombcato/clash-ip-checker)




一个针对 **Clash** (及兼容核心) 的自动化节点工具。它会自动遍历你的代理节点，通过 [IPPure](https://ippure.com/)或者[Ping0](https://ping0.cc/) 检测 IP 纯净度和相关属性，并重命名节点，添加实用的指标（IP 纯净度、Bot 比例(或共享人数)、IP属性/IP来源状态）`【🟢🟡 住宅|原生】`。
效果展示：
![图片描述](assets/clash-node-checked.png)
Web可视化配置检测：
![alt text](assets/clash-web-check.png)
## 📅 更新日志 (Changelog)

### v2.0.0 (2026-01-11)
- **Web UI**: 全新推出 Web 可视化界面，操作更便捷。
- **多源检测**: 新增 `Ping0` 检测源 支持共享人数，与 `ippure` 互补，并设为默认（速度与信息量平衡更佳）。
- **智能降级**: 新增 `Fallback` 机制，例如：Ping0 失败时自动切换至 IPPure。
- **极速默认**: 极速模式 (`fast_mode`) 默认开启，大幅提升批量检测效率。
- **单点重测**: Web 界面支持对单个节点进行重新检测，方便复核。
- **导出增强**: 支持检测结果的实时预览、编辑和一键导出，一键导入Clash
- **体验优化**: 自动清理 IP 缓存，防止结果残留；优化了端口检测和冲突处理。


## ✨ 功能特点

- **🖥️ Web 可视化界面 (新!)**: 提供现代化的 Web 界面，支持可视化配置，检测可查看实时进度显示、单点重测、结果编辑和导出预览，支持一键跳转导入Clash。
- **极速模式**: 默认 **开启**，通过 IPPure API 或者 Ping0 直接检测，速度比浏览器模式更快！可在config.yaml中设置`fast_mode = False`关闭。
- **极速模式多数据源支持**: 支持 `ping0` (默认) 和 `ippure` 两种检测源，支持自动降级 (Fallback) 机制，当 ping0 失败时自动切换到 ippure。**ippure缺少 Bot 比例分析，Ping0有共享人数数据**
- **自动切换**: 自动遍历并切换你的 Clash 代理节点。
- **深度 IP 分析**: 检测 IP 纯净度分数、Bot 比例、IP 属性 (原生/机房) 以及归属地。
- **高拟真检测 (可选)**: 在浏览器模式下使用 **Playwright** 进行高拟真检测，包含 Bot 比例分析。支持无头模式 (Headless) 配置。
- **智能过滤**: 自动跳过无效节点 (如 "到期", "流量重置", "官网" 等)。
- **配置注入**: 生成一个新的 Clash 配置文件 (`_checked.yaml`)，在节点名称后追加 Emoji 和状态信息。
- **强制全局模式**: 临时将 Clash 强制切换为全局模式以确保测试准确性。

##  ⚡新增Docker部署 [详情见Docker分支](https://github.com/tombcato/clash-ip-checker/tree/docker)
相对于主分支而言，Docker部署后代理切换不影响本地网络（部署NAS或者云服务器），且能直接输入订阅链接输出新订阅链接，没有繁琐的使用步骤，**一键替换订阅url检测！**
**云部署Demo地址：https://tombcat.space/ipcheck** 

## 🛠️ 前置要求

- **Python 3.10+**
- **Clash Verge** (或其他开启了 External Controller 的 Clash 客户端)

## 📦 安装说明

1.  **克隆仓库**
    ```bash
    git clone git@github.com:tombcato/clash-ip-checker.git
    cd clash-ip-checker
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    # 非极速模式需要
    playwright install chromium
    # 如果 install chromium 运行失败说明 playwright 没添加环境变量，可以用：
    # python -m playwright install chromium
    ```

3.  **启动 Web 界面 (新版推荐)**
    ```bash
    python web.py
    ```
    访问 http://127.0.0.1:8080 即可使用图形化界面进行配置和检测。
    
4.  **命令行模式 (旧版)**
    - 修改 `config.yaml.example` 删除后缀重命名为 `config.yaml`。
    - 编辑 `config.yaml` 填入配置（Web 界面中也可直接设置）：
        - `yaml_path`: 你的 Clash 配置文件 (**.yaml**) 的绝对路径。
        - `clash_api_secret`: 你的 API 密钥 (如果有的话)。
        - `fast_mode`: ⚡ 是否使用极速模式 (True/False)。
        - `source`: 检测源，可选 `ping0` 或 `ippure` (默认 ping0)。
        - `fallback`: 是否开启自动降级 (True/False)。
    - 运行 `python clash_automator.py`。

## Web 界面使用方法 (新版推荐)

### 梯子导出并导入 Clash

在安装梯子客户端的 Windows 电脑上运行 `python web.py`，打开 [梯子导出页面](http://127.0.0.1:18080/qingyunti)。先登录客户端并加载节点，点击「提取并预览」，成功后填写导入名称，再点击「导入 Clash」或下载 YAML。导入完成前保持网页服务运行，随后在 Clash 中启用新配置。

网页会自动识别唯一的 ApexCore 实例，并保留脚本的安装路径校验；安装位置不同时需修改 `qingyunti-export/extract.py` 中的 `APEX_CORE`。提取结果只保存在服务内存中，不写入公开下载目录，仅允许本机访问；再次提取或重启服务后，旧导入链接失效。导出为静态配置，节点变更后需重新提取，不会自动更新订阅。完整说明见 [梯子导出工具](qingyunti-export/README.md)。

### 可视化生成主备切换配置

在安装 Clash Verge Rev 的 Windows 电脑上运行 `python web.py`，打开 [主备切换配置页面](http://127.0.0.1:18080/failover)。顶部导航可在「IP 质量检测」与「主备切换配置」两个独立页面之间切换。

1. 页面打开时会自动读取当前 Windows 用户在 Clash 中已保存的订阅，也可点击「刷新本机订阅」重新读取，无需粘贴 YAML，也无需先检测节点。
2. 分别选择主用订阅与节点、第一备用和第二备用的订阅与节点，可以跨订阅选择。第二备用可不填；按「主用 → 第一备用 → 第二备用」的优先级使用第一个可用节点。
3. 填写配置名称和检测间隔，点击「生成主备配置」，然后下载或「导入 Clash」。导入后需在 Clash Verge Rev 中启用新配置。

以后调整已导入的主备配置时，刷新本机订阅，在「保存方式」选择「更新已有：配置名」，再点击「更新主备配置」。网页会复用原来的订阅地址，随后在 Clash Verge Rev 对原订阅点一次「更新」即可，不会新增订阅。首次使用且只有一个可更新的主备配置时会默认选中它；只有本网页生成且导出文件仍存在的配置可以更新。Clash 的导入协议本身会新增订阅，因此更新完成后网页不会再显示「导入 Clash」按钮。

当前浏览器会自动保存主用、两个备用节点、保存方式、名称和检测间隔，刷新或重新打开页面后恢复；已删除的订阅或节点会清空。浏览器只保存这些表单选择，不保存节点密码或整份订阅；清除网站数据、无痕窗口或更换浏览器/网址后不会保留。生成的 YAML 保存在网页服务的 `exports` 目录，Clash 的「更新」会重新拉取这份文件。刷新网页不会重新生成 YAML 或让 Clash 生效；修改后仍需先在网页保存配置，再在 Clash 更新订阅，并保持网页服务运行。

生成的是只包含所选节点的独立配置，默认使用 [Loyalsoldier/clash-rules 白名单模式](https://github.com/Loyalsoldier/clash-rules#白名单模式-rules-配置方式推荐)：私有网络、iCloud、Apple、国内域名及 IP 直连，广告拦截，Google、代理域名、Telegram IP 和未匹配流量交给主备切换。规则集通过 jsDelivr 获取，每 24 小时更新，首次启用时需要联网下载。主用恢复后优先切回。不修改原订阅，也不继承原订阅的分流规则或扩展脚本。节点使用本机订阅的当前快照，更新或换节点时重新选择并生成；代理集合和依赖链式代理的节点暂不支持。网页服务需与 Clash Verge Rev 在同一台电脑、同一 Windows 用户下运行；一键导入时保持网页服务运行。

主备配置不使用 `applications` 规则集或按程序强制直连规则，流量按域名和 IP 分流。配置开启 443/8443 端口的 TLS 域名嗅探，包含纯 IP 连接，并用识别出的域名作为实际访问目标，避免 Proxifier 传入受本机 DNS 影响的 IP 后仍连接错误地址。嗅探依赖可识别的 TLS 域名，不能保证覆盖所有协议。已生成的旧主备配置需要更新后才会使用这些调整。

### IP 质量检测

1. 打开你的 Clash 客户端 (例如 Clash Verge) 将当前clash正在运行的订阅配置文件切换为你想要测试的订阅，点击获取YAML源代码，然后复制粘贴进[web界面](http://127.0.0.1:8080)的yaml框中
    ![alt text](assets/clash-open-yaml-code.png)
2. 确保Clash中 External Controller (外部控制) 已在设置中开启，密码随便设置, 然后再Web界面中配置
![alt text](assets/clash-controller.png)
3. 使用默认配置直接点击开始即可，检测完成后会可一键预览导入Clash
![alt text](assets/clash-web-check.png)

## 命令行模式使用方法（旧版）

1.  打开你的 Clash 客户端 (例如 Clash Verge) 将当前clash正在运行的订阅配置文件切换为你想要测试的订阅， 然后获取该配置文件的yaml文件绝对路径, 在config.yaml中配置yaml_path.
    右键配置文件选择打开文件
    ![](assets/clash-open-yaml.png)
    通过vscode获取path
    ![](assets/clash-open-yaml-vscode.png)
    或者通过记事本获取path, 鼠标悬停展示但无法复制，需要在对应的文件夹中找到再复制
    ![](assets/clash-open-yaml-jsb.png)

1.  确保 **External Controller** (外部控制) 已在设置中开启，并在config.yaml中配置clash_api_url与clash_api_secret与之对应。密码随便设置
    ![alt text](assets/clash-controller.png)
2.  运行脚本:
    ```bash
    python clash_automator.py
    ```
    *默认使用浏览器模式 (包含 Bot 检测)。如需开启 **极速模式** (速度快 10 倍，无 Bot 检测)，请在 `config.yaml` 中设置 `fast_mode = True`。*

3.  脚本将会:
    - 连接到 Clash API。
    - 切换到 "Global" (全局) 模式。
    - 逐个测试代理节点, 访问IPPure获取ip信息。
    - 生成一个名为 `your_config_checked.yaml` 的新文件。
4.  在项目当前文件夹下将生成的 `_checked.yaml` 文件导入 Clash 即可切换该配置查看结果！
    导入_checked.yaml配置
    ![](assets/clash-import.png)

## 📝 输出示例

你的代理节点将会被重命名，直观展示其质量：

### 🔍 结果解读

格式： `【🟢🟡 机房|广播】` (默认浏览器模式) 或 `【⚪ 机房|广播】` (极速模式)

*   **第 1 个 Emoji (⚪)**: **IP 纯净度** (值越低越好，越低越像真实用户)
*   **第 2 个 Emoji (🟡)**: **Bot 比例** (浏览器模式独有，值越高来自机器人的流量更大更容易弹验证)
*   **属性**: 住宅 / 机房 
*   **来源**: 原生 / 广播

#### 📊 评分对照表

| 范围 | Emoji | 含义 |
| :--- | :---: | :--- |
| **0 - 10%** | ⚪ | **极佳** |
| **11 - 30%** | 🟢 | **优秀** |
| **31 - 50%** | 🟡 | **良好** |
| **51 - 70%** | 🟠 | **中等** |
| **71 - 90%** | 🔴 | **差** |
| **> 90%** | ⚫ | **极差** |

#### 🏷️ 常见标签说明

*   **住宅 (Residential)**: 家庭宽带 IP，隐蔽性高，被封锁概率低。
*   **机房 (Datacenter)**: 数据中心 IP，速度快但容易被识别。
*   **原生 (Native)**: 指该 IP 归属于当地运营商，通常解锁流媒体 (Netflix, Disney+) 效果最好。
*   **广播 (Broadcast)**: IP 地理位置与注册地不符。

## ⚙️ 配置项

查看 `config.yaml.example` 获取所有可用配置项的说明。

## 🤝 贡献参与

欢迎提交 Pull Request 来改进这个项目！

## ⚠️ 免责声明

本工具仅供教育和测试使用。请遵守当地法律法规，并合理使用代理服务。

## 🌟 Star 记录

[![Star History Chart](https://api.star-history.com/svg?repos=tombcato/clash-ip-checker&type=Date)](https://star-history.com/#tombcato/clash-ip-checker&Date)






