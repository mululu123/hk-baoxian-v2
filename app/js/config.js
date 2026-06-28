// Cloud sync configuration.
// 把下面两个占位值换成你 Supabase 项目 Settings → API 的真实值，云同步就生效。
// anon key 是公开 key（RLS 保护），可以直接写进前端代码 / 提交到 public 仓库。
window.CONFIG = {
  SUPABASE_URL: 'YOUR_SUPABASE_URL_HERE',          // e.g. https://abcdef.supabase.co
  SUPABASE_ANON_KEY: 'YOUR_SUPABASE_ANON_KEY_HERE', // eyJ... 长 JWT
};
