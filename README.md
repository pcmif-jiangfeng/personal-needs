# 个人需求发现工具

把生活、学习和工作中反复遇到的麻烦记下来，找出最值得解决的问题，再整理成可以交给 Codex 的项目描述。

适合想改善个人工作流、减少重复劳动，或希望从真实经历中寻找软件项目方向的人。只想先记下一件不顺的小事，也可以直接开始。

**核心流程：随手记录 → 补充细节和评分 → 把同类问题归入主题 → 分析与每周复盘 → 生成项目描述。**

例如：多次记录“整理实验数据时，总要手动改列名”，归入“实验数据整理”主题，补充理想输入和输出，最后生成一份数据整理工具的开发需求。

当前版本既可以在电脑浏览器中运行，也已经具备 PWA 能力。通过 Tailscale 提供的私有 HTTPS 地址，可以在手机上安装到主屏幕，并继续使用电脑上的同一份数据。

## 本地启动

需要 **Python 3.11 或更新版本**、浏览器，以及 Git（也可以下载仓库 ZIP 后解压）。无需配置 AI 账号或 API Key；项目没有运行时第三方依赖。

### 1. 获取项目

```bash
git clone https://github.com/pcmif-jiangfeng/personal-needs.git
cd personal-needs
```

已有项目文件夹时，直接在该文件夹打开终端。

### 2. 启动应用

在项目根目录运行：

```bash
python -m app.server
```

macOS / Linux 如果使用 `python3` 命令，请改为 `python3 -m app.server`。

浏览器打开 **http://127.0.0.1:8765**。首次启动会自动创建数据库，无需手动初始化或复制配置文件。

使用期间保持终端运行；按 `Ctrl+C` 停止。下次执行同一命令即可继续使用，已保存的记录会保留。若端口被占用，可用 `python -m app.server --port 8766` 启动，并打开对应端口。

<details>
<summary>可选：使用虚拟环境并安装命令行入口</summary>

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m app.server
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m app.server
```

安装后，在已激活的虚拟环境中也可运行 `personal-needs`。日常直接从源码启动无需这一步。

</details>

## 在手机上安装 PWA

推荐使用 Tailscale Serve。它会把电脑上的本地服务映射为一个 HTTPS 地址，并且默认只允许同一个 Tailscale 私有网络中的设备访问。

### 1. 准备设备

- 在电脑和手机上安装 Tailscale，并登录同一个账号。
- 在电脑上启动本项目：`python -m app.server`。
- 保持电脑开机和服务运行。

### 2. 开启私有 HTTPS 地址

先在一个终端窗口启动应用，并保持运行：

```bash
python -m app.server
```

再在另一个终端窗口执行：

```bash
tailscale serve --bg --yes http://127.0.0.1:8765
tailscale serve status
```

第一次执行时，如果终端提示 `Serve is not enabled on your tailnet`，请打开它显示的 Tailscale 官方链接，登录同一个账号并点击 **Enable Serve**，完成后重新执行上面的两条命令。

终端会显示形如 `https://设备名.网络名.ts.net/` 的地址。用手机浏览器打开该地址即可使用。

当前这台电脑生成的实际地址是：<https://qingfengwu.tailcb5008.ts.net/>。这个地址由 `tailscale serve status` 返回，只对登录到你同一 Tailscale 网络的设备有效；其他用户需要在自己的电脑上部署并生成自己的地址。

如需停止共享：

```bash
tailscale serve --https=443 off
```

### 3. 安装到主屏幕

- Android Chrome：打开 HTTPS 地址，点击右上角菜单，选择 **安装应用** 或 **添加到主屏幕**。
- iPhone Safari：打开 HTTPS 地址，点击 **分享**，选择 **添加到主屏幕**。

安装后会以独立窗口启动，但数据仍存放在运行服务的电脑中。手机上的应用不是一份独立数据库；电脑关机、Python 服务停止或 Tailscale 断开时，手机无法读取和保存记录。

<details>
<summary>临时局域网访问</summary>

电脑与手机连接同一个 Wi-Fi 时，也可以运行：

```bash
python -m app.server --host 0.0.0.0 --port 8765
```

然后用手机访问 `http://电脑的局域网IP:8765/`。Windows 防火墙需要允许 Python 通过专用网络。由于局域网地址使用 HTTP，更适合临时访问，不建议作为 PWA 安装方式。

</details>

## 多用户云端部署

仓库已包含可选的 Supabase 云端模式。部署到 Render 的 `*.onrender.com` 域名后，页面会自动显示邮箱注册与登录，并通过 Supabase RLS 让每位用户只能访问自己的记录。本地 `localhost` 和 Tailscale 使用方式仍连接本机 SQLite。

部署前先在 Supabase SQL Editor 执行 `supabase/schema.sql`，再把最新代码上传到 GitHub。Render 可以直接读取根目录的 `render.yaml` 创建静态站点。获得 Render HTTPS 地址后，需要在 Supabase **Authentication → URL Configuration** 中把 **Site URL** 和允许的 **Redirect URL** 设置为该地址。

完整步骤见 [多用户云端部署准备](docs/CLOUD_SETUP.md)。`cloud-config.js` 中只包含允许放在浏览器里的 Project URL 和 Publishable key，不包含数据库密码或 service role key。

### 访问故障排查

如果 HTTPS 域名暂时打不开，可以先确认手机是否能连接电脑上的服务。电脑终端执行：

```bash
tailscale ip -4
```

假设返回 `100.x.x.x`，手机在 Tailscale 已连接的情况下访问：`http://100.x.x.x:8765/`。这个地址只用于排查网络连接，不支持正式 PWA 安装；正式使用仍应打开 `https://设备名.网络名.ts.net/`。

## 第一次使用：先记一条真实问题

1. 在 **快速记录** 填写“我当时在做什么”和“发生了什么”，点击 **记下来**。例如：“整理实验数据”／“每次都要手动统一列名，容易漏改”。只有这两项必填，感受和补充说明可选。
2. 打开 **需求**，点击刚保存的记录。以后有空再补场景、标签、当前解决方法和理想状态；首次记录的原话会保留。
3. 想比较优先级时，再补齐五项 1–5 分评分：痛苦程度、出现频率、时间成本、自动化潜力和使用意愿。填全后会得到 0–100 的机会评分；未填全显示“待补评分”。分数用于辅助比较。
4. 同类问题再次出现时，新增记录；到 **主题** 建立一个主题，再在各条记录的详情里选择“需求主题”并保存。每次遇到都记录，才便于看清实际出现次数。
5. 每周打开 **复盘**，选一个值得继续解决的问题。需要推进成项目时，在对应主题上点击 **生成 Prompt**，检查内容后复制给 Codex，或下载 TXT。

不必第一次就填完所有细节。先积累真实记录，再逐步判断哪些问题值得投入时间。

## 主要功能入口

| 入口 | 可以做什么 |
| --- | --- |
| 快速记录 | 用两句话保存当下的问题，可选即时感受。 |
| 需求 | 搜索记录，按时间、痛苦、频率、耗时、自动化潜力或综合价值排序；点击记录编辑详情、标签和评分，也可删除。页面右上方提供导出。 |
| 主题 | 手动汇集同类记录，查看出现次数、首次／最近出现时间、平均痛苦和机会分；生成 Codex 项目描述。删除主题会保留其记录。 |
| 分析 | 查看场景与问题类型分布、评分完成度，以及最痛、最频繁、最值得自动化和综合价值排行。 |
| 复盘 | 查看本周记录数量、分布和重点问题；按北京时间周一至周日统计。 |

分析和复盘不计入已归档记录。当前界面尚无状态切换入口。

## 数据存储与隐私

- 默认数据保存在**运行服务的电脑**上，位置是项目目录中的 `data/needs.sqlite3`。关闭浏览器不会删除数据。
- 默认仅本机可访问（`127.0.0.1`）。通过 Tailscale Serve 可以向自己的私有网络提供 HTTPS 访问；当前没有应用内登录和权限隔离，不适合直接公开到互联网。
- 应用不接入外部 AI 服务；“生成 Prompt”是在本地按模板整理记录，只有你将内容提交给 Codex 或其他服务时，内容才会发送到相应服务。
- `data/` 和 `.env` 已被 Git 忽略。数据库是普通本地文件，应用未提供数据库加密，也没有自动云备份。

**备份与恢复：**先停止应用，再复制整个 `data/` 文件夹到其他位置。恢复时也先停止应用，保留现有数据副本后，将备份放回原位置，再启动。若自定义了数据库位置，应备份和恢复该位置的数据库及相关文件。

## 导出

在 **需求** 页面点击右上方的导出按钮：

| 格式 | 适合用途 | 包含内容 |
| --- | --- | --- |
| JSON | 完整数据留存、后续迁移或自行处理 | 全部记录、原始表达、主题、标签及关联关系。 |
| CSV | 在 Excel 等表格工具中查看和分析 | 全部记录字段，感受和标签展开为文本。 |
| TXT | 将需求交给 Codex | 在 **主题 → 生成 Prompt → 下载 TXT** 获取该主题的项目描述。 |

JSON 和 CSV 导出的是**全部记录，包括归档记录**，不受当前搜索结果影响。当前没有 JSON／CSV 导入入口；如需恢复应用原状，请使用数据库备份。导出文件可能含私人记录，分享前请检查内容。

## 可选配置

默认配置即可使用。需要修改时，将 `.env.example` 复制为项目根目录的 `.env`，按需调整：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | 监听地址，本机使用保持默认。 |
| `PORT` | `8765` | 浏览器访问的端口。 |
| `DATABASE_PATH` | `data/needs.sqlite3` | 数据库位置；相对路径以项目根目录为基准。 |

修改后重启应用生效。系统环境变量优先于 `.env`，启动参数 `--host`、`--port`、`--db` 优先于两者。更换数据库路径不会自动迁移旧数据。

## 项目结构与验证

```text
app/
  index.html          页面与交互
  server.py           本地服务、分析、导出和 Prompt 生成
  db.py / schema.sql  数据库初始化与结构
  config.py           本机配置
  scoring.json        机会评分配置
  cloud-config.js     可公开的 Supabase 项目配置与云端启用规则
  cloud.js            登录、会话和云端数据适配器
  manifest.webmanifest / service-worker.js / icons/
                      Web 应用信息、页面缓存与图标
supabase/schema.sql   PostgreSQL 表、触发器与 RLS 策略
render.yaml           Render 静态站点部署配置
data/                 本地用户数据（自动创建，不提交）
tests/                自动化测试
docs/                 需求、工程决策、安全与部署说明
.env.example          可选配置模板
pyproject.toml        Python 版本要求和安装信息
```

项目使用 Python 标准库、SQLite 和原生网页，无需前端构建。开发或修改后，可在项目根目录运行现有测试：

```bash
python -m unittest discover -s tests -v
```

测试使用临时数据库，不修改日常使用的数据库。

## 当前限制与后续方向

- 本地模式面向单人使用；云端模式已接入 Supabase 邮箱账号和用户数据隔离，但需要完成 Render 部署后才能公开使用。
- 主题归类需要手动完成，尚无 AI 自动聚类；生成 Prompt 后需自行提交给 Codex，不会自动创建或开发项目。
- 界面目前支持搜索与排序，尚无独立的日期／标签筛选和需求状态流转操作。
- 已支持 PWA 安装和基础页面缓存，但服务停止后无法读取或保存需求数据，不支持完整离线使用。

后续可围绕导入与备份恢复、筛选与状态管理、智能归类以及移动端／离线体验继续完善；同步和公开部署需要先补齐相应的数据与访问控制能力。这些是待完善方向，不代表当前已支持。

更多背景见 [需求说明](docs/requirements.md)、[应用形态方向](docs/APP_PATH.md)、[安全说明](docs/SECURITY_NOTES.md) 和 [部署分析](docs/DEPLOYMENT_ANALYSIS.md)。这些文档包含早期规划，当前功能以实际界面和实现为准。
