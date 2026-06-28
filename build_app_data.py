#!/usr/bin/env python3
"""
把 4 份去重后的 JSON 题库转成 JS 数据文件，供网页 app 直接 <script> 加载。
输出到 app/data/<paper>.js，格式：
    window.QUESTION_BANKS = window.QUESTION_BANKS || {};
    window.QUESTION_BANKS['paper1'] = { ... };
"""
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, 'raw')
APP_DATA_DIR = os.path.join(BASE_DIR, 'app', 'data')


def natural_sort_key(s):
    """章节号自然排序：'1.1', '1.2', '1.10', '2.1' 而不是 '1.1', '1.10', '1.2'"""
    s = str(s)
    parts = re.split(r'(\d+)', s)
    result = []
    for p in parts:
        if p == '':
            continue
        if p.isdigit():
            # 数字转 int，前面加个标记 (0=int) 让 int 之间比较，避免和 str 冲突
            result.append((0, int(p)))
        else:
            result.append((1, p))
    return result

FILES = [
    ('paper1',     'paper1/paper1_dedup.json',     'Paper 1',         '保險原理及實務', '2025 新版'),
    ('paper3',     'paper3/paper3_dedup.json',     'Paper 3',         '長期保險',       '2025 新版'),
    ('paper1_old', 'paper1_old/paper1_old_dedup.json', '試卷一 (旧)', '保險原理及實務', '旧版'),
    ('paper3_old', 'paper3_old/paper3_old_dedup.json', '試卷三 (旧)', '長期保險',       '旧版'),
]


def to_js_string(obj):
    """把 Python dict 转成合法的 JS 对象字面量字符串（用 json.dumps 保证）"""
    return json.dumps(obj, ensure_ascii=False, indent=None, separators=(',', ':'))


def clean_section(s):
    """清理 section 字段：去空白、去换行、标准化"""
    if not s:
        return ''
    s = str(s).strip()
    # 去掉所有空白和换行
    s = re.sub(r'\s+', '', s)
    # 全角括号转半角
    s = s.replace('（', '(').replace('）', ')')
    # 多余的空括号
    s = re.sub(r'\(\s*\)', '', s)
    return s


def normalize_section_for_group(s):
    """章节归一化：用于把 '1.1.2(a)' 和 '1.1.2a' 视为同一章节"""
    s = clean_section(s)
    # 把 '1.1.2a' 和 '1.1.2(a)' 归一化
    s = re.sub(r'(\d)\s*\(\s*([a-z])\s*\)', r'\1\2', s)
    return s


def main():
    os.makedirs(APP_DATA_DIR, exist_ok=True)

    banks_meta = []
    for key, rel_path, label, subject, edition in FILES:
        src = os.path.join(RAW_DIR, rel_path)
        if not os.path.exists(src):
            print(f'[skip] {src}')
            continue
        with open(src, encoding='utf-8') as f:
            data = json.load(f)
        questions = data.get('questions', [])

        # 精简每道题（只保留 app 需要的字段）+ 清理 section
        slim = []
        sections_counter = {}  # 归一化后的 section → [显示名, 题数]
        for q in questions:
            raw_sec = q.get('section', '')
            norm_sec = normalize_section_for_group(raw_sec)
            # 选较"完整"的原始版本作为显示名（去掉 \n 后的）
            display_sec = clean_section(raw_sec)
            sq = {
                'id': q.get('id', ''),
                'no': q.get('question_no', ''),
                'section': display_sec,
                'sectionKey': norm_sec,
                'question': q.get('question', ''),
                'options': q.get('options', {}),
                'answer': q.get('answer', ''),
                'explanation': q.get('explanation', ''),
            }
            slim.append(sq)
            if norm_sec:
                if norm_sec not in sections_counter:
                    sections_counter[norm_sec] = {'display': display_sec, 'count': 0}
                sections_counter[norm_sec]['count'] += 1
                # 偏好带括号的版本作为 display
                if '(' in display_sec and '(' not in sections_counter[norm_sec]['display']:
                    sections_counter[norm_sec]['display'] = display_sec

        # 输出归并后的章节列表（按章节号自然排序）
        sections_list = sorted(
            [{'key': k, 'display': v['display'], 'count': v['count']}
             for k, v in sections_counter.items()],
            key=lambda x: natural_sort_key(x['display'])
        )

        # 输出 JS 数据文件
        out_js = os.path.join(APP_DATA_DIR, f'{key}.js')
        with open(out_js, 'w', encoding='utf-8') as f:
            f.write('// Auto-generated from raw/' + rel_path + '\n')
            f.write('// Do not edit manually; regenerate with build_app_data.py\n')
            f.write("window.QUESTION_BANKS = window.QUESTION_BANKS || {};\n")
            f.write(f"window.QUESTION_BANKS[{json.dumps(key)}] = ")
            f.write(to_js_string({
                'key': key,
                'label': label,
                'subject': subject,
                'edition': edition,
                'total': len(slim),
                'sections': sections_list,
                'questions': slim,
            }))
            f.write(';\n')

        banks_meta.append({
            'key': key,
            'label': label,
            'subject': subject,
            'edition': edition,
            'total': len(slim),
            'sections': len(sections_list),
        })
        print(f'  → {out_js}: {len(slim)} 题, {len(sections_list)} 章节')

    # 输出 banks 元信息（让 app 知道有哪些题库）
    meta_js = os.path.join(APP_DATA_DIR, '_meta.js')
    with open(meta_js, 'w', encoding='utf-8') as f:
        f.write('// Auto-generated index of question banks\n')
        f.write("window.QUESTION_BANKS_META = ")
        f.write(to_js_string(banks_meta))
        f.write(';\n')
    print(f'  → {meta_js}: {len(banks_meta)} 题库索引')

    print(f'\n=== 总题数: {sum(b["total"] for b in banks_meta)} ===')


if __name__ == '__main__':
    main()
