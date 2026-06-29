-- 用户上报的可疑题目表
-- 每条记录是一个用户对某道题的标记，便于后台集中审查

create table if not exists question_reports (
  id uuid primary key default gen_random_uuid(),
  device_id text not null,
  user_id uuid references auth.users(id) on delete cascade,
  paper_key text not null,
  question_id text not null,
  question_no text,
  reason text not null check (reason in (
    'wrong_answer',       -- 答案疑似错误
    'duplicate_options',  -- 选项重复
    'ocr_garbage',        -- 题干/选项乱码
    'missing_options',    -- 选项不足 4 个
    'other'               -- 其他
  )),
  note text,
  suggested_answer text check (suggested_answer is null or suggested_answer in ('A','B','C','D')),
  created_at timestamptz not null default now()
);

create index if not exists idx_reports_question on question_reports(paper_key, question_id);
create index if not exists idx_reports_device on question_reports(device_id);

-- 启用 RLS；anon 用 device_id 作为弱身份标识自己上报的记录
alter table question_reports enable row level security;

-- anon 可插入（任何人都可上报）
create policy "anon_insert_report" on question_reports
  for insert to anon with check (true);

-- anon 可读自己 device_id 的上报（用于"我上报过哪些"列表）
create policy "anon_read_own_reports" on question_reports
  for select to anon using (device_id = current_setting('request.header.x-device-id', true));

-- 注：服务端管理（看所有上报、改 status）走 service_role，绕过 RLS。
-- 后期加 Auth 后，管理员角色可以基于 auth.uid() 解锁全表读权限。
