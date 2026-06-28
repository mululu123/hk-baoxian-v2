#!/usr/bin/env python3
"""
按原文件分别去重（不跨文件合并）

对每个 raw/<paper>/<paper>_all.json 单独去重：
- 同一份 PDF 内部，按题干相似度找出重复题
- 保留代表版本（优先题干+选项最完整的）
- 输出到同目录下 <paper>_dedup.json

输出文件保持原始单文件结构，不混合。
"""
import json
import re
import os
import sys
from difflib import SequenceMatcher
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, 'raw')

FILES = [
    ('paper1',     'paper1/paper1_all.json',         'Paper 1 - 保險原理及實務 2025'),
    ('paper3',     'paper3/paper3_all.json',         'Paper 3 - 長期保險 2025'),
    ('paper1_old', 'paper1_old/paper1_old_all.json', '試卷一 - 保險原理及實務 (旧版)'),
    ('paper3_old', 'paper3_old/paper3_old_all.json', '試卷三 - 長期保險 (旧版)'),
]

SIM_THRESHOLD = 0.92        # 同一文件内去重阈值（更严格，避免误删）
OPTION_SIM_THRESHOLD = 0.7


def normalize(text):
    if not text:
        return ''
    s = str(text)
    s = s.translate(str.maketrans({chr(0xFF10 + i): chr(0x30 + i) for i in range(10)}))
    s = s.translate(str.maketrans({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)}))
    s = s.translate(str.maketrans({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)}))
    for ch in ' \t\n\r，。、；：（）「」『』""''\'\\.,;:()?!？！/\\-—–~·':
        s = s.replace(ch, '')
    return s.lower()


def opt_signature(q):
    opts = q.get('options', {}) or {}
    vals = [normalize(v) for v in opts.values() if v]
    return '|'.join(sorted(vals))


def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def dedupe_within(qs):
    """对单个文件的题目列表去重"""
    # 按标准化题干精确分组
    by_norm = defaultdict(list)
    no_stem = []
    for q in qs:
        nq = normalize(q.get('question', ''))
        if not nq:
            no_stem.append(q)
        else:
            by_norm[nq].append(q)

    # 相似度合并
    keys = list(by_norm.keys())
    used = [False] * len(keys)
    clusters = []
    for i, k in enumerate(keys):
        if used[i]:
            continue
        group = list(by_norm[k])
        sig_i = opt_signature(group[0])
        used[i] = True
        for j in range(i + 1, len(keys)):
            if used[j]:
                continue
            sim = similarity(k, keys[j])
            if sim >= SIM_THRESHOLD:
                sig_j = opt_signature(by_norm[keys[j]][0])
                sig_sim = similarity(sig_i, sig_j) if sig_i and sig_j else 1.0
                if sig_sim >= OPTION_SIM_THRESHOLD or not sig_i or not sig_j:
                    group.extend(by_norm[keys[j]])
                    used[j] = True
        clusters.append(group)
    # 无题干的单独成簇
    for q in no_stem:
        clusters.append([q])
    return clusters


def pick_representative(group):
    """选最佳代表"""
    def score(q):
        s = 0
        if (q.get('explanation') or '').strip() and '暫未提供' not in q.get('explanation', ''):
            s += 1000
        if q.get('answer') in {'A', 'B', 'C', 'D'}:
            s += 100
        if len(q.get('options', {})) == 4:
            s += 50
        # 题号小的优先（更"标准"）
        try:
            qno_int = int(str(q.get('question_no', '')).lstrip('Qq'))
            s += max(0, 1000 - qno_int) // 100
        except (TypeError, ValueError):
            pass
        return s
    return sorted(group, key=score, reverse=True)[0]


def process_file(key, rel_path, label):
    path = os.path.join(RAW_DIR, rel_path)
    if not os.path.exists(path):
        print(f'  [skip] {path} 不存在')
        return None
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    qs = data.get('questions', [])
    total = len(qs)

    clusters = dedupe_within(qs)
    final = []
    duplicates_log = []
    for group in clusters:
        rep = pick_representative(group)
        # 记录该题的重复来源
        rep['_dup_count'] = len(group)
        if len(group) > 1:
            rep['_dup_of'] = [
                {
                    'question_no': g.get('question_no'),
                    'page': g.get('page'),
                    'answer': g.get('answer'),
                }
                for g in group
            ]
            duplicates_log.append({
                'kept': rep.get('question_no'),
                'duplicates': [g.get('question_no') for g in group],
            })
        final.append(rep)
    # 清理临时字段但保留 _dup_count 和 _dup_of 作为元信息
    # 重新分配 ID
    for i, q in enumerate(final, start=1):
        q['id'] = f'{key}_dedup_{i:04d}'

    out_obj = {
        'source_paper': key,
        'source_label': label,
        'total_pages': data.get('total_pages'),
        'stats': {
            'original_count': total,
            'after_dedup': len(final),
            'duplicates_removed': total - len(final),
        },
        'duplicates_log': duplicates_log,
        'questions': final,
    }

    sub_dir = os.path.dirname(path)
    out_path = os.path.join(sub_dir, f'{key}_dedup.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    return {
        'key': key,
        'original': total,
        'after': len(final),
        'removed': total - len(final),
        'out_path': out_path,
    }


def main():
    print('=== 按原文件分别去重 ===\n')
    results = []
    for key, rel_path, label in FILES:
        print(f'--- {key} ---')
        r = process_file(key, rel_path, label)
        if r:
            print(f'  原始: {r["original"]} 题')
            print(f'  去重后: {r["after"]} 题')
            print(f'  移除重复: {r["removed"]} 题')
            print(f'  输出: {r["out_path"]}')
            results.append(r)
        print()

    print('=== 汇总 ===')
    total_orig = sum(r['original'] for r in results)
    total_after = sum(r['after'] for r in results)
    print(f'4 份合计: 原始 {total_orig} 题 → 去重后 {total_after} 题 (移除 {total_orig - total_after})')


if __name__ == '__main__':
    main()
