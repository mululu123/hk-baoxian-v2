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

## 注意

原始考试 PDF 不包含在仓库内（版权原因）。如需重建数据，请自行准备 PDF 并依次运行：

```bash
python3 extract_pdf.py
python3 dedupe_per_file.py
python3 merge_dedup.py
python3 build_app_data.py
```
