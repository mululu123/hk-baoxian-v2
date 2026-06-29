#!/usr/bin/env python3
"""
Diff 新提取 vs 现有去重后的题库，找出抽取过程可能引入的错误。
重点：相同题号在新旧两次提取中，question/options/answer 是否一致。
"""
import json, os, re
BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, 'raw')

def norm(s):
    return re.sub(r'\s+', '', str(s or '')).lower()

def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)['questions']

print('=' * 70)
print('新提取 vs 现有 (去重后) 差异')
print('=' * 70)

for key in ['paper1', 'paper3', 'paper1_old', 'paper3_old']:
    fresh = load(os.path.join(RAW, '_reextract', f'{key}_all.json'))
    existing = load(os.path.join(RAW, key, f'{key}_dedup.json'))

    # Match by question_no (Q166 etc.)
    fresh_by_no = {q['question_no']: q for q in fresh}
    existing_by_no = {q['question_no']: q for q in existing}

    diffs = []
    only_fresh = []
    only_existing = []

    for qno, fq in fresh_by_no.items():
        if qno not in existing_by_no:
            only_fresh.append(qno)
            continue
        eq = existing_by_no[qno]
        # Compare key fields
        if norm(fq['question']) != norm(eq['question']):
            diffs.append((qno, 'QUESTION_TEXT'))
        if fq['answer'] != eq['answer']:
            diffs.append((qno, f'ANSWER {eq["answer"]}→{fq["answer"]}'))
        # Options
        for letter in 'ABCD':
            fo = norm(fq.get('options',{}).get(letter,''))
            eo = norm(eq.get('options',{}).get(letter,''))
            if fo != eo:
                diffs.append((qno, f'OPTION_{letter}'))

    for qno in existing_by_no:
        if qno not in fresh_by_no:
            only_existing.append(qno)

    print(f'\n[{key}]')
    print(f'  fresh={len(fresh)} existing={len(existing)} (after dedup)')
    print(f'  only in fresh: {len(only_fresh)} {only_fresh[:5]}')
    print(f'  only in existing: {len(only_existing)} {only_existing[:5]}')
    print(f'  conflicts (same Q# but different content): {len(diffs)}')

    # Show first 20 conflicts in detail
    if diffs:
        by_q = {}
        for qno, kind in diffs:
            by_q.setdefault(qno, []).append(kind)
        sorted_qs = sorted(by_q.items(), key=lambda x: int(x[0].lstrip('Qq')) if x[0].lstrip('Qq').isdigit() else 9999)
        for qno, kinds in sorted_qs[:15]:
            fq = fresh_by_no[qno]
            eq = existing_by_no[qno]
            print(f'\n  ■ {qno}  diffs: {kinds}')
            if any('ANSWER' in k for k in kinds):
                print(f'    OLD answer: {eq["answer"]}  →  NEW answer: {fq["answer"]}')
            if any(k.startswith('OPTION_') for k in kinds):
                for letter in 'ABCD':
                    fo = fq.get('options',{}).get(letter,'')[:60]
                    eo = eq.get('options',{}).get(letter,'')[:60]
                    if norm(fo) != norm(eo):
                        print(f'    {letter} OLD: {eo}')
                        print(f'    {letter} NEW: {fo}')
            if 'QUESTION_TEXT' in kinds:
                print(f'    OLD Q: {eq["question"][:100]}')
                print(f'    NEW Q: {fq["question"][:100]}')
