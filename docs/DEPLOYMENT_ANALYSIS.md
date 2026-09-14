# 部署可行性分析

审计日期：2026-09-14

## 当前判断

**尚不适合直接部署到公网。**

应用使用本地 SQLite 保存全部个人需求记录，且没有登录或权限隔离。更重要的是，多数平台的服务文件系统是临时的；重启或重新部署后，写入的 SQLite 数据会丢失。Render 明确说明默认文件系统是临时的，而持久磁盘仅适用于单实例服务并会影响部署方式。[Render Persistent Disks](https://render.com/docs/disks)

## 平台比较

| 方案 | 适配度 | 结论 |
| --- | --- | --- |
| Render Web Service + 持久磁盘 | 中 | 技术上最接近当前 Python + SQLite 单实例架构。需要付费持久磁盘；免费 Web Service 不提供持久磁盘。[Render 免费部署说明](https://render.com/docs/free) |
| Render Web Service + Postgres | 中长期 | 更适合真实公网服务，但需要 SQLite 迁移、认证和备份策略。本轮不实施。 |
| Railway + Volume | 中 | 具备长期存储路线，但仍需要认证、备份和生产级进程方案；作为备选。 |
| Cloudflare Pages | 低 | 适合静态 HTML；当前应用有 Python API 和可写 SQLite，不能直接部署。官方文档说明 Pages 的静态部署模式。[Cloudflare Pages Static HTML](https://developers.cloudflare.com/pages/framework-guides/deploy-anything/) |
| Vercel / Netlify 静态部署 | 低 | 与 Cloudflare Pages 同样不适合当前可写 SQLite + Python 进程结构。 |

## 推荐方案

首选：**继续本地运行**。这是当前产品的本地优先设计，数据不离开用户设备，也不需要增加登录、服务器和数据库运维。

如必须发布给单个受控用户：**Render 付费 Web Service + 持久磁盘** 是改动最少的托管方向。数据库应放在挂载目录，例如 `/var/data/needs.sqlite3`，并通过 `DATABASE_PATH` 配置；服务必须保持单实例。

备选：**Railway + Volume**，适合希望以容器和卷管理部署的人，但并不会消除认证、备份与单实例 SQLite 的限制。

## 不推荐方案

- Cloudflare Pages、Vercel、Netlify 的纯静态托管：不能承载当前 Python API 与持久 SQLite 写入。
- Render 免费 Web Service 承载真实 SQLite 数据：官方说明免费服务没有持久磁盘，数据不可靠。[Render Free](https://render.com/docs/free)
- 直接把内置 `ThreadingHTTPServer` 裸露到公网：缺少认证、TLS、反向代理、限流和生产级进程管理。

## 未来部署步骤

1. 先决定是否接受“数据上云”，并定义认证与备份要求。
2. 若是，添加生产级服务进程与健康检查，并将 SQLite 迁移到托管 Postgres，或明确采用单实例持久卷的风险。
3. 在非真实数据环境完成部署测试、备份恢复测试和权限测试后，再连接域名。
