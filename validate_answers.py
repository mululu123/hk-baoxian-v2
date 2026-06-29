#!/usr/bin/env python3
"""
題庫答案正確性體檢 — 找出 PDF 抽取過程可能引入的錯誤。
檢查項目：
  1. answer 字段非法 (不是 A/B/C/D)
  2. answer 對應的選項為空或與其他選項重複
  3. 4 個選項裡有重複文本
  4. 問題文本異常短 (<10 字) 或異常長 (>1500 字)
  5. 問題或選項含明顯 OCR 殘留 (亂碼、暫未提供註解)
  6. 跨題庫 (old vs new) 同題不同答案 — 可能其中一個錯
  7. i/ii/iii 類題的答案組合不完整 (例如答案是 "i,ii,iii" 但選項裡沒這個)
"""
import json
import os
import re
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')

FILES = [
    ('paper1',     'paper1/paper1_dedup.json'),
    ('paper3',     'paper3/paper3_dedup.json'),
    ('paper1_old', 'paper1_old/paper1_old_dedup.json'),
    ('paper3_old', 'paper3_old/paper3_old_dedup.json'),
]

def normalize_text(s):
    if not s: return ''
    return re.sub(r'\s+', '', str(s)).lower()

def detect_issues(questions, paper_key):
    issues = []
    for q in questions:
        qid = q.get('id', '?')
        qno = q.get('question_no', '?')
        ans = q.get('answer', '')
        opts = q.get('options', {}) or {}
        text = q.get('question', '') or ''

        # 1. Invalid answer
        if ans not in ('A', 'B', 'C', 'D'):
            issues.append((qid, qno, 'BAD_ANSWER', f'answer="{ans}"'))
            continue  # skip further checks

        # 2. Chosen option empty
        chosen = opts.get(ans, '').strip()
        if not chosen:
            issues.append((qid, qno, 'EMPTY_CHOSEN', f'answer={ans} but option {ans} is empty'))

        # 3. Duplicate options (after normalizing whitespace)
        norm_opts = {k: normalize_text(v) for k, v in opts.items() if v}
        seen = {}
        for k, v in norm_opts.items():
            if v in seen:
                issues.append((qid, qno, 'DUP_OPTION',
                              f'options {seen[v]} and {k} identical: "{v[:40]}"'))
            else:
                seen[v] = k

        # 4. Question length
        if len(text) < 10:
            issues.append((qid, qno, 'Q_TOO_SHORT', f'len={len(text)} text="{text}"'))
        elif len(text) > 1500:
            issues.append((qid, qno, 'Q_TOO_LONG', f'len={len(text)}'))

        # 5. OCR residue
        if '暫未提供' in text or '暫只提供' in text:
            issues.append((qid, qno, 'OCR_RESIDUE_TEXT', 'question contains placeholder'))
        for k, v in opts.items():
            if v and ('暫未提供' in v or '暫只提供' in v):
                issues.append((qid, qno, 'OCR_RESIDUE_OPT', f'option {k}: "{v[:40]}"'))

        # 6. i/ii/iii type — verify answer text appears in some option
        if re.search(r'\bi\b.*\bii\b', text) or 'iii' in text:
            ans_text = normalize_text(opts.get(ans, ''))
            # check if at least the answer mentions one of i/ii/iii
            if ans_text and not re.search(r'\b(i|ii|iii|iv)\b', opts.get(ans, '')):
                issues.append((qid, qno, 'I_II_III_MISMATCH',
                              f'question uses i/ii/iii but answer {ans}="{opts.get(ans,"")[:40]}" doesn\'t'))

    return issues


def cross_paper_contradictions(banks):
    """Find questions with identical normalized text but different answers across papers."""
    by_text = defaultdict(list)
    for paper_key, questions in banks.items():
        for q in questions:
            t = normalize_text(q.get('question', ''))
            if len(t) > 20:  # skip very short
                by_text[t].append((paper_key, q.get('question_no'), q.get('answer'), q.get('id')))

    contradictions = []
    for text, occurrences in by_text.items():
        if len(occurrences) < 2: continue
        answers = set(o[2] for o in occurrences)
        if len(answers) > 1:
            contradictions.append((text[:80], occurrences))
    return contradictions


def main():
    banks = {}
    total_issues = 0
    print('=' * 70)
    print('題庫答案正確性體檢')
    print('=' * 70)

    for key, rel in FILES:
        path = os.path.join(RAW, rel)
        if not os.path.exists(path):
            print(f'\n[{key}] MISSING: {path}')
            continue
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        questions = data.get('questions', [])
        banks[key] = questions
        issues = detect_issues(questions, key)
        total_issues += len(issues)
        print(f'\n[{key}] {len(questions)} 題, 發現 {len(issues)} 個問題:')
        # group by type
        by_type = defaultdict(list)
        for i in issues:
            by_type[i[2]].append(i)
        for typ, items in sorted(by_type.items()):
            print(f'  {typ}: {len(items)} 則')
            for it in items[:3]:
                print(f'    - {it[1]} ({it[0]}): {it[3][:80]}')
            if len(items) > 3:
                print(f'    ... 還有 {len(items)-3} 則')

    # Cross-paper contradictions
    print('\n' + '=' * 70)
    print('跨題庫同題不同答案 (新版 vs 旧版)')
    print('=' * 70)
    contradictions = cross_paper_contradictions(banks)
    print(f'發現 {len(contradictions)} 組')
    for text, occ in contradictions[:10]:
        print(f'\n  Q: {text}...')
        for paper_key, qno, ans, qid in occ:
            print(f'    {paper_key} {qno} ({qid}): answer={ans}')
    if len(contradictions) > 10:
        print(f'\n  ... 還有 {len(contradictions)-10} 組')

    print('\n' + '=' * 70)
    print(f'總計: {total_issues} 個單題問題, {len(contradictions)} 組跨題庫矛盾')
    print('=' * 70)


if __name__ == '__main__':
    main()
