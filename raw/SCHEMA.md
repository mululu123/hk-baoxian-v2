# 题库数据结构 Schema

## 单题结构（questions.json 中的每一条）

```json
{
  "id": "p1_0001",
  "source_paper": "paper1",
  "source_label": "Paper 1 - 保險原理及實務 2025",
  "page": 5,
  "question_no": 1,
  "question": "下列哪項有關風險的描述是正確的？",
  "options": {
    "A": "選項 A 內容",
    "B": "選項 B 內容",
    "C": "選項 C 內容",
    "D": "選項 D 內容"
  },
  "answer": "B",
  "explanation": "解析內容（若 PDF 提供）",
  "category": "風險管理"
}
```

## source_paper 取值

| 取值 | 来源 |
|------|------|
| `paper1` | Paper 1.pdf（保險原理及實務，218 页，2025 新版） |
| `paper3` | Paper 3.pdf（長期保險，210 页，2025 新版） |
| `paper1_old` | 試卷一(1).pdf（保險原理及實務，166 页，旧版） |
| `paper3_old` | 試卷三(1).pdf（長期保險，157 页，旧版） |

## 提取流程

1. 每个 PDF 切成 ~70 页的块，一块一个 agent 并行提取
2. 每块输出到 `raw/<paper>_part<N>.json`
3. 合并 + 跨题号匹配答案 → `raw/<paper>_all.json`
4. 跨 4 份去重（按题干标准化后比对）→ `merged/questions.json`

## 去重规则

- 题干去除标点、空格、全半角差异后做精确匹配
- 题干相似度 > 95% 视为重复（选项顺序不同也算同一题）
- 保留所有来源（sources 数组）
