# 香港保险中介人资格考试 — 模拟试题练习 v2

香港 IIQE（Insurance Intermediaries Qualifying Examination）Paper 1（保险原理及实务）和 Paper 3（长期保险）的模拟试题练习 web app。

> **v2** 是 [hk-baoxian](https://github.com/mululu123/hk-baoxian) 的迭代版本，规划新增 Supabase 云同步、多账号登录、跨设备进度同步。v1 仓库保留作为稳定参考。

## 在线访问

部署到 Vercel 后访问根域名。

## 项目结构

```
app/                  # 静态 web app（可直接部署）
  index.html
  css/style.css
  js/app.js
  data/               # 题库 JSON-in-JS 数据
raw/                  # 从 PDF 提取的中间数据（每题一个 JSON）
extract_pdf.py        # PDF → 文本/JSON
dedupe_per_file.py    # 单文件内去重
merge_dedup.py        # 多文件合并去重
build_app_data.py     # 生成 app/data/*.js
```

## 本地预览

```bash
cd app && python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

## 部署

**Vercel**：导入仓库，Root Directory 设为 `app`。

**GitHub Pages**：仓库 Settings → Pages → Source `main` 分支 → `/app` 目录。

## 云同步（Supabase）

v2 已内置云同步代码框架，**默认禁用**——在 `app/js/config.js` 填入凭证才会启用。

### 一次性后端初始化

1. supabase.com 新建项目 `hk-baoxian-v2`。
2. 进 **SQL Editor** 跑：

```sql
create table if not exists user_progress (
  id uuid primary key default gen_random_uuid(),
  device_id text not null,
  user_id uuid references auth.users(id) on delete cascade,
  paper_key text not null,
  progress jsonb not null,
  updated_at timestamptz not null default now(),
  unique (device_id, paper_key)
);
create index if not exists idx_user_progress_device on user_progress(device_id);
create index if not exists idx_user_progress_user on user_progress(user_id) where user_id is not null;

alter table user_progress enable row level security;
create policy "anon_rw_by_device" on user_progress for all to anon using (true) with check (true);

create or replace function tg_set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;
create trigger trg_user_progress_updated_at before update on user_progress
  for each row execute function tg_set_updated_at();
```

3. 进 **Settings → API**，把 **Project URL** 和 **anon public** key 填到 `app/js/config.js`：

```js
window.CONFIG = {
  SUPABASE_URL: 'https://xxxxx.supabase.co',
  SUPABASE_ANON_KEY: 'eyJhbGciOi...',
};
```

提交、推 Vercel 自动重新部署，首页会显示 `✓ 已同步` 徽章。

### 工作原理

- 首次访问生成 `device_id` (UUID) 存 localStorage，永久绑定本设备。
- 答题/翻页时 debounce 1.5 秒后 `upsert` 整个 progress 到 Supabase。
- 启动时 `pull` 云端数据，按 `_updatedAt` 时间戳与本地比较，**最后写入者胜**。
- 离线时全部 no-op，恢复网络后下次写入会自动同步。
- 后期加 Supabase Auth 后，只需把 RLS 策略换成基于 `auth.uid()`，前端再加登录 UI，进度会从 device_id 平滑迁到 user_id。

## 注意

原始考试 PDF 不包含在仓库内（版权原因）。如需重建数据，请自行准备 PDF 并依次运行：

```bash
python3 extract_pdf.py
python3 dedupe_per_file.py
python3 merge_dedup.py
python3 build_app_data.py
```
