# 个人需求发现工具

一个本地优先的轻量工具，用于把生活、学习、科研和工作中的零散摩擦记录为可搜索、可比较、可复盘的需求数据库。

## 技术栈

- Python 3.11+
- Python 标准库 HTTP 服务
- SQLite（本地数据）
- 原生 HTML、CSS、JavaScript

项目没有运行时第三方依赖。

## 安装

```bash
git clone <repository-url>
cd personal-needs
python -m venv .venv
```

激活虚拟环境后安装项目：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

## 环境变量

`.env` 仅用于本机配置，已被 Git 忽略。`.env.example` 可以提交，且不包含密钥。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | 服务监听地址；本地使用保持默认值。 |
| `PORT` | `8765` | 服务端口。 |
| `DATABASE_PATH` | `data/needs.sqlite3` | SQLite 数据库相对路径或绝对路径。 |

系统环境变量会优先于 `.env` 中的值。

## 本地运行

```bash
python -m app.server
```

浏览器打开 `http://127.0.0.1:8765`。应用默认只监听本机；真实用户数据保存在 `data/needs.sqlite3`，该目录不会提交到 Git。

## 验证

```bash
python -m unittest discover -s tests -v
```

测试使用临时数据库，不会修改 `data/needs.sqlite3`。

## 生产运行

当前仓库没有静态构建步骤；安装后可通过以下命令启动：

```bash
personal-needs --host 0.0.0.0 --port 8765
```

这只适合受信任网络或反向代理后的单实例部署。当前版本没有登录、权限隔离和托管数据库，不应直接公开到互联网。部署判断与后续步骤见 [DEPLOYMENT_ANALYSIS.md](docs/DEPLOYMENT_ANALYSIS.md)。

## 项目结构

```text
app/                  应用代码、SQLite schema 和前端页面
tests/                自动化测试
docs/                 需求、工程决策、审计和部署文档
data/                 本地 SQLite 用户数据（不提交）
.env.example          可提交的配置模板
pyproject.toml        Python 项目元数据和命令行入口
```

## 主要功能

- 快速记录、详情编辑、搜索、排序与完整导出
- 标签、评分和机会价值计算
- 需求分析、周复盘与手动主题聚类
- 基于主题生成 Codex 项目描述
