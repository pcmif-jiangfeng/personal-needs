# 多用户云端部署准备

## 当前阶段

本地应用仍使用 SQLite，不受本文件影响。`supabase/schema.sql` 是云端 PostgreSQL 的独立初始化脚本，执行前不会修改本机数据库。

## 在 Supabase 中初始化数据库

1. 打开 Supabase 项目。
2. 进入 **SQL Editor**，点击 **New query**。
3. 打开本项目的 `supabase/schema.sql`，复制全部内容到查询编辑器。
4. 点击 **Run**。
5. 进入 **Table Editor**，确认出现 `records`、`themes`、`tags` 和 `record_tags` 四张表。
6. 进入 **Authentication → Policies**，确认四张表均已启用 RLS。

脚本会创建系统标签、每用户数据归属字段、更新时间触发器、原始表达保护，以及只能访问本人数据的 RLS 策略。

## 不要提交的内容

- 数据库密码
- Supabase service role key / secret key
- PostgreSQL connection string
- 包含上述值的 `.env`

Supabase Project URL 和前端 publishable / anon key 会在接入登录页面时通过部署平台环境变量提供；service role key 不进入浏览器。

## 后续工作

数据库 schema 初始化成功后，按以下步骤部署：

1. 把最新的 `app/`、`supabase/`、`render.yaml`、`README.md` 和 `docs/` 上传到 GitHub。
2. 登录 Render，连接 GitHub 账号。
3. 在 Render 中选择 **New → Blueprint**，选择当前仓库；Render 会读取根目录的 `render.yaml` 创建静态站点。
4. 等待部署完成，记录 Render 提供的 `https://...onrender.com` 地址。
5. 回到 Supabase，进入 **Authentication → URL Configuration**。
6. 将 **Site URL** 设置为 Render 地址，并在 **Redirect URLs** 中加入同一个地址和 `/**` 通配路径。
7. 使用未注册的邮箱创建测试账号，完成邮件确认并登录。
8. 再创建第二个测试账号，确认两个账号互相看不到记录、主题和自定义标签。

云端模式使用浏览器可见的 Project URL 和 Publishable key，并由 RLS 执行授权。不要把数据库密码、service role key 或 PostgreSQL connection string 放进 `app/`。

本地 SQLite 数据不会自动同步到云端。上线后如需迁移旧记录，应使用单独的导入流程，不能直接上传 `data/needs.sqlite3`。
