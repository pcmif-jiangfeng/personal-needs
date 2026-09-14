# 项目审计

审计日期：2026-09-14

## 技术栈

| 项目 | 结论 |
| --- | --- |
| 前端 | 单页原生 HTML、CSS、JavaScript，位于 `app/index.html`。 |
| 后端 | Python 标准库 `http.server`，路由与 API 位于 `app/server.py`。 |
| 语言 | Python 3.11+；审计环境为 Python 3.13.12。 |
| 包管理 | 新增 `pyproject.toml`；运行时没有第三方依赖。 |
| 数据库 | SQLite，默认路径 `data/needs.sqlite3`。 |
| CSS / 构建 | 无 CSS 框架、无打包构建步骤。 |
| 外部 / AI / 登录服务 | 未发现。 |

## 当前启动与验证

- 开发启动：`python -m app.server`
- 测试：`python -m unittest discover -s tests -v`
- 安装后启动：`personal-needs --host 0.0.0.0 --port 8765`
- 没有生产构建步骤；项目直接运行 Python 源码。

## 目录评估

| 路径 | 作用 | 评估 |
| --- | --- | --- |
| `app/` | 服务端、SQLite schema、前端 | 合理。 |
| `tests/` | 临时 SQLite 数据库上的单元与 HTTP 测试 | 合理。 |
| `docs/` | 需求、决策和工程文档 | 合理。 |
| `data/` | 本地用户数据 | 必须保留，但不能提交。 |

未移动现有业务文件。`app/server.py` 当前承担路由、查询、统计和导出，约 665 行；这是中优先级维护性问题，因本轮禁止大规模重构，仅记录。

## 审计结论

- Git：审计开始时未初始化；本轮已完成本地 Git 初始化，并确认 `.env` 与 `data/needs.sqlite3` 被 `.gitignore` 排除。未创建提交，也未连接或推送远程仓库。
- 依赖：审计开始时没有 Python 项目元数据；本轮新增 `pyproject.toml`，声明 Python 版本和零依赖状态。
- 数据库：表结构可由 `app/schema.sql` 重建。审计时数据库为 0 条记录、0 个主题，仍按真实用户数据保护并排除在 Git 外。
- 本机路径：运行时代码只使用相对数据库路径；`127.0.0.1` 是本地默认监听与测试地址。现在可用 `HOST`、`PORT`、`DATABASE_PATH` 覆盖。
- 敏感信息：对应用、测试和 README 进行了密钥模式扫描，未发现疑似 API Key、Token、密码或认证头。

## 最小修改方案

1. 新增项目元数据、`.env.example` 和依赖零的本地配置读取。
2. 扩展 `.gitignore`，保护 SQLite 用户数据、环境文件、缓存和虚拟环境。
3. 完善 README，补齐复现、运行和限制说明。
4. 添加安全、部署与 App 路线文档。
5. 初始化 Git，验证待跟踪文件不包含用户数据和 `.env`。

未修改数据库 schema、需求逻辑、视觉界面或产品功能。
