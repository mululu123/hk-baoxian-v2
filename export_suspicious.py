#!/usr/bin/env python3
"""导出 10 个可疑题目的完整内容，便于人工核对。"""
import json, os
BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')

SUSPICIOUS = [
    # 跨版本矛盾 (paper_key, question_no)
    ('paper1', 'Q166'), ('paper1_old', 'Q104'),     # 矛盾 1
    ('paper1', 'Q168'), ('paper1_old', 'Q159'),     # 矛盾 2
    ('paper1', 'Q815'), ('paper1_old', 'Q911'),     # 矛盾 3
    ('paper1', 'Q817'), ('paper1_old', 'Q857'),     # 矛盾 4
    ('paper3', 'Q55'),  ('paper3_old', 'Q21'),      # 矛盾 5
    ('paper3', 'Q635'), ('paper3_old', 'Q496'),     # 矛盾 6
    ('paper3', 'Q650'), ('paper3_old', 'Q483'),     # 矛盾 7
    # 重复选项
    ('paper1', 'Q144'),
    ('paper3', 'Q245'),
    ('paper3_old', 'Q114'),
]

def load(paper_key):
    p = os.path.join(RAW, f'{paper_key}/{paper_key}_dedup.json')
    with open(p, encoding='utf-8') as f: return json.load(f)['questions']

banks = {k: load(k) for k, _ in SUSPICIOUS}

print('=' * 75)
print('可疑题目清单 — 请对照原 PDF 核对')
print('=' * 75)

# Group contradictions
groups = [
    ('矛盾 1: 訂約的行爲能力', [('paper1','Q166'),('paper1_old','Q104')]),
    ('矛盾 2: 訂約的行為能力 (適用於)', [('paper1','Q168'),('paper1_old','Q159')]),
    ('矛盾 3: 打擊洗錢管控措施', [('paper1','Q815'),('paper1_old','Q911')]),
    ('矛盾 4: 防止洗錢步驟', [('paper1','Q817'),('paper1_old','Q857')]),
    ('矛盾 5: 投保人必須披露的重要事實', [('paper3','Q55'),('paper3_old','Q21')]),
    ('矛盾 6: 壽險保單產權轉讓', [('paper3','Q635'),('paper3_old','Q496')]),
    ('矛盾 7: 已婚者地位條例', [('paper3','Q650'),('paper3_old','Q483')]),
    ('重複選項 1', [('paper1','Q144')]),
    ('重複選項 2', [('paper3','Q245')]),
    ('重複選項 3', [('paper3_old','Q114')]),
]

for title, keys in groups:
    print(f'\n{"─" * 75}')
    print(f'【{title}】')
    print('─' * 75)
    for paper_key, qno in keys:
        q = next((x for x in banks[paper_key] if x.get('question_no') == qno), None)
        if not q:
            print(f'\n  ❌ {paper_key} {qno} 未找到')
            continue
        print(f'\n  ■ {paper_key} {qno}  (page {q.get("page","?")}, id {q.get("id","?")})')
        print(f'  章節: {q.get("section","?")}')
        print(f'  問題: {q.get("question","")}')
        for letter in 'ABCD':
            v = q.get('options',{}).get(letter,'')
            mark = ' ◀ 答案' if q.get('answer') == letter else ''
            if v: print(f'    {letter}. {v}{mark}')
        print(f'  解析: {q.get("explanation","")[:100]}')
