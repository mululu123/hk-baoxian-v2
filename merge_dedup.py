#!/usr/bin/env python3
"""
合并 + 去重 + 跨版校验 4 份 PDF 提取结果

输入（每份 PDF 各一个文件，分开存储）:
- raw/paper1/paper1_all.json
- raw/paper3/paper3_all.json
- raw/paper1_old/paper1_old_all.json
- raw/paper3_old/paper3_old_all.json

输出（合并产物）:
- merged/questions.json      高置信度最终题库
- merged/review.json         跨版答案不一致等待复核题目
- merged/verify_report.json  校验统计报告
"""
import json
import re
import os
import sys
from difflib import SequenceMatcher
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, 'raw')
OUT_DIR = os.path.join(BASE_DIR, 'merged')

SOURCES = [
    # (key, path, label, sister_key for cross-verify)
    ('paper1',     'paper1/paper1_all.json',                 'Paper 1 - 保險原理及實務 2025',         'paper1_old'),
    ('paper3',     'paper3/paper3_all.json',                 'Paper 3 - 長期保險 2025',               'paper3_old'),
    ('paper1_old', 'paper1_old/paper1_old_all.json',         '試卷一 - 保險原理及實務 (旧版)',         'paper1'),
    ('paper3_old', 'paper3_old/paper3_old_all.json',         '試卷三 - 長期保險 (旧版)',               'paper3'),
]

SIM_THRESHOLD = 0.88        # 题干相似度阈值（>= 视为同题）
OPTION_SIM_THRESHOLD = 0.6  # 选项集合相似度阈值
VALID_ANSWERS = {'A', 'B', 'C', 'D'}


def normalize(text):
    """标准化用于去重比较"""
    if not text:
        return ''
    s = str(text)
    # 全角转半角
    s = s.translate(str.maketrans({chr(0xFF10 + i): chr(0x30 + i) for i in range(10)}))
    s = s.translate(str.maketrans({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)}))
    s = s.translate(str.maketrans({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)}))
    # 去除所有标点、空白
    for ch in ' \t\n\r，。、；：（）「」『』""''\'\\.,;:()?!？！/\\-—–~·':
        s = s.replace(ch, '')
    return s.lower()


def clean_section(s):
    """清理 section 字段（去掉换行等）"""
    if not s:
        return ''
    return re.sub(r'\s+', '', str(s)).strip()


def clean_question_text(s):
    """清理题干文本"""
    if not s:
        return ''
    s = str(s).strip()
    # 多个连续空白合并
    s = re.sub(r'[ \t]+', ' ', s)
    # 末尾的 Y 标记（异常）
    s = re.sub(r'\s*Y\s*$', '', s)
    return s.strip()


def clean_option_text(s):
    """清理选项文本"""
    if not s:
        return ''
    s = str(s).strip()
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def opt_signature(q):
    """选项集合的标准化签名（按内容排序，忽略选项字母顺序）"""
    opts = q.get('options', {}) or {}
    vals = [normalize(v) for v in opts.values() if v]
    return '|'.join(sorted(vals))


def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def load_source(key, rel_path, label):
    path = os.path.join(RAW_DIR, rel_path)
    if not os.path.exists(path):
        print(f'  [skip] {path} 不存在', file=sys.stderr)
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    qs = data.get('questions', []) if isinstance(data, dict) else data
    # 清理每道题
    out = []
    for q in qs:
        q['section'] = clean_section(q.get('section', ''))
        q['question'] = clean_question_text(q.get('question', ''))
        opts = q.get('options', {}) or {}
        q['options'] = {k: clean_option_text(v) for k, v in opts.items()}
        q['answer'] = (q.get('answer') or '').strip().upper()
        q.setdefault('source_paper', key)
        q.setdefault('source_label', label)
        out.append(q)
    print(f'  载入 {rel_path}: {len(out)} 题')
    return out


def cross_verify(by_paper):
    """跨版本校验答案一致性 (paper1 vs paper1_old, paper3 vs paper3_old)"""
    pairs = [('paper1', 'paper1_old'), ('paper3', 'paper3_old')]
    issues = []
    matched = 0
    for new_key, old_key in pairs:
        new_qs = by_paper.get(new_key, [])
        old_qs = by_paper.get(old_key, [])
        if not new_qs or not old_qs:
            continue
        # 用标准化题干建索引
        old_index = defaultdict(list)
        for q in old_qs:
            nq = normalize(q.get('question', ''))
            if nq:
                old_index[nq].append(q)
        for q_new in new_qs:
            nq_new = normalize(q_new.get('question', ''))
            if not nq_new:
                continue
            # 精确匹配
            candidates = old_index.get(nq_new, [])
            # 相似度匹配
            if not candidates:
                best_sim = 0
                best_key = None
                for k in old_index:
                    sim = similarity(nq_new, k)
                    if sim > best_sim:
                        best_sim, best_key = sim, k
                if best_sim >= SIM_THRESHOLD and best_key:
                    candidates = old_index[best_key]
            if not candidates:
                continue
            matched += 1
            ans_new = (q_new.get('answer') or '').strip().upper()
            for q_old in candidates:
                ans_old = (q_old.get('answer') or '').strip().upper()
                if ans_new and ans_old and ans_new != ans_old:
                    issues.append({
                        'type': 'answer_mismatch',
                        'new_paper': new_key,
                        'old_paper': old_key,
                        'new_qno': q_new.get('question_no'),
                        'old_qno': q_old.get('question_no'),
                        'new_answer': ans_new,
                        'old_answer': ans_old,
                        'question_preview': (q_new.get('question') or '')[:80],
                    })
    return matched, issues


def dedupe(all_q):
    """按题干标准化文本聚类，再用相似度合并近似簇"""
    by_norm = defaultdict(list)
    for q in all_q:
        nq = normalize(q.get('question', ''))
        if nq:
            by_norm[nq].append(q)
    clusters = list(by_norm.values())

    # 相似度合并
    used = [False] * len(clusters)
    merged = []
    for i, c in enumerate(clusters):
        if used[i]:
            continue
        sig_i = opt_signature(c[0])
        text_i = normalize(c[0].get('question', ''))
        group = list(c)
        used[i] = True
        for j in range(i + 1, len(clusters)):
            if used[j]:
                continue
            text_j = normalize(clusters[j][0].get('question', ''))
            sim = similarity(text_i, text_j)
            if sim >= SIM_THRESHOLD:
                sig_j = opt_signature(clusters[j][0])
                sig_sim = similarity(sig_i, sig_j) if sig_i and sig_j else 1.0
                # 题干相似 + 选项集合也要相似
                if sig_sim >= OPTION_SIM_THRESHOLD or not sig_i or not sig_j:
                    group.extend(clusters[j])
                    used[j] = True
        merged.append(group)
    return merged


def pick_representative(group):
    """从重复题簇中选最佳代表：优先新版有解析的"""
    PRIORITY = {'paper1': 4, 'paper3': 3, 'paper1_old': 2, 'paper3_old': 1}

    def score(q):
        s = 0
        # 有解析的优先
        expl = q.get('explanation') or ''
        if expl and '暫未提供' not in expl and '暫只提供' not in expl:
            s += 1000
        # 答案合法
        if q.get('answer') in VALID_ANSWERS:
            s += 100
        # 4 个选项齐全
        if len(q.get('options', {})) == 4:
            s += 50
        # 新版优先（解析更完整）
        s += PRIORITY.get(q.get('source_paper'), 0) * 10
        return s

    return sorted(group, key=score, reverse=True)[0]


def main():
    print('=== 加载 4 份提取结果 ===')
    by_paper = {}
    for key, rel_path, label, _ in SOURCES:
        by_paper[key] = load_source(key, rel_path, label)

    print('\n=== 结构完整性（应全部 OK，因为我们已校验过）===')
    for key, qs in by_paper.items():
        bad = [q for q in qs if not q.get('answer') or len(q.get('options', {})) != 4]
        print(f'  {key}: {len(qs)} 题, {len(bad)} 题结构异常')

    print('\n=== 跨版本答案一致性校验 ===')
    matched, issues = cross_verify(by_paper)
    print(f'  跨版匹配到 {matched} 道重叠题')
    print(f'  答案不一致：{len(issues)} 道')
    if issues:
        for it in issues[:10]:
            print(f'    [{it["new_paper"]}#{it["new_qno"]} vs {it["old_paper"]}#{it["old_qno"]}] '
                  f'答案 {it["new_answer"]}≠{it["old_answer"]}: {it["question_preview"][:50]}...')

    print('\n=== 去重合并 ===')
    all_q = []
    for key, _, _, _ in SOURCES:
        all_q.extend(by_paper.get(key, []))
    print(f'  合并前：{len(all_q)} 题')
    clusters = dedupe(all_q)
    print(f'  去重后：{len(clusters)} 个独立题')

    final = []
    review_items = []
    for idx, group in enumerate(clusters, start=1):
        rep = pick_representative(group)
        sources = []
        seen = set()
        answers_in_group = set()
        for q in group:
            ref = f'{q.get("source_paper")}#{q.get("question_no")}'
            if ref not in seen:
                sources.append({
                    'paper': q.get('source_paper'),
                    'question_no': q.get('question_no'),
                    'page': q.get('page'),
                    'section': q.get('section'),
                })
                seen.add(ref)
            a = (q.get('answer') or '').upper()
            if a:
                answers_in_group.add(a)

        obj = {
            'id': f'q{idx:05d}',
            'question': rep.get('question', ''),
            'options': rep.get('options', {}),
            'answer': rep.get('answer', ''),
            'explanation': rep.get('explanation', ''),
            'section': rep.get('section', ''),
            'source_paper': rep.get('source_paper'),
            'sources': sources,
            'dup_count': len(group),
            'all_answers_in_dups': sorted(answers_in_group),
        }
        # 答案是否一致
        if len(answers_in_group) > 1:
            obj['confidence'] = 'low'
            obj['issue'] = 'conflicting_answers_across_versions'
            review_items.append({
                'id': obj['id'],
                'issue': '答案在多个版本中不一致',
                'answers': sorted(answers_in_group),
                'sources': sources,
                'question_preview': obj['question'][:120],
            })
        else:
            obj['confidence'] = 'high'
        final.append(obj)

    # 排序：按 section，然后按 source_paper 优先级
    PRIORITY = {'paper1': 0, 'paper3': 1, 'paper1_old': 2, 'paper3_old': 3}

    def sort_key(q):
        src = q['source_paper'] or ''
        # 用 sources 里第一个的 section + question_no
        first = q['sources'][0] if q['sources'] else {}
        section = first.get('section', '') or ''
        qno = first.get('question_no', '')
        try:
            qno_int = int(str(qno).lstrip('Qq')) if qno else 99999
        except (TypeError, ValueError):
            qno_int = 99999
        # section 排序：1.x 在 2.x 之前
        section_key = section
        return (PRIORITY.get(src, 99), section_key, qno_int)

    final.sort(key=sort_key)
    for i, q in enumerate(final, start=1):
        q['id'] = f'q{i:05d}'

    os.makedirs(OUT_DIR, exist_ok=True)
    high = [q for q in final if q['confidence'] == 'high']
    low = [q for q in final if q['confidence'] == 'low']

    main_out = {
        'version': '1.0',
        'generated_from': [s[0] for s in SOURCES],
        'total_high_confidence': len(high),
        'total_low_confidence': len(low),
        'papers': [{'key': k, 'label': l} for k, _, l, _ in SOURCES],
        'questions': high,
    }
    with open(os.path.join(OUT_DIR, 'questions.json'), 'w', encoding='utf-8') as f:
        json.dump(main_out, f, ensure_ascii=False, indent=2)

    review_out = {
        'version': '1.0',
        'total': len(review_items),
        'cross_version_answer_mismatches': len(issues),
        'items': review_items,
        'cross_version_issues': issues,
    }
    with open(os.path.join(OUT_DIR, 'review.json'), 'w', encoding='utf-8') as f:
        json.dump(review_out, f, ensure_ascii=False, indent=2)

    report = {
        'loaded': {k: len(v) for k, v in by_paper.items()},
        'total_loaded': sum(len(v) for v in by_paper.values()),
        'cross_version_matched': matched,
        'cross_version_answer_mismatches': len(issues),
        'after_dedup': len(final),
        'high_confidence': len(high),
        'low_confidence': len(low),
    }
    with open(os.path.join(OUT_DIR, 'verify_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f'\n=== 最终输出 ===')
    print(f'  questions.json (高置信度): {len(high)} 题')
    print(f'  review.json     (待复核): {len(low)} 题')
    print(f'  跨版答案冲突: {len(issues)} 题')
    print(f'  verify_report.json: 校验报告')

    print(f'\n=== 各来源代表题数 ===')
    by_src = Counter(q['source_paper'] for q in final)
    for k, _, _, _ in SOURCES:
        print(f'  {k}: {by_src.get(k, 0)} 题')


if __name__ == '__main__':
    main()
