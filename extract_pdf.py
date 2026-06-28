#!/usr/bin/env python3
"""
PDF 题库提取器 - 基于表格结构解析

依赖: pdfplumber
输入: PDF 文件路径
输出: 结构化 JSON 题库

表格结构（每页通常一个表格）:
- 题头行: col0=题号(Q##), col1=参考章节, col2=题干, col3=空, col4=解析
- 选项行: col0=空, col1=选项字母(A/B/C/D), col2=选项内容, col3=Y(标记答案), col4=空

输出 schema:
{
  "source_paper": "paper1",
  "source_label": "...",
  "total_pages": N,
  "questions": [
    {
      "id": "p1_0001",
      "source_paper": "paper1",
      "page": 5,
      "question_no": "Q18",
      "section": "1.1.1",
      "question": "题干",
      "options": {"A":"...","B":"...","C":"...","D":"..."},
      "answer": "C",
      "explanation": "解析"
    }
  ]
}
"""
import pdfplumber
import json
import re
import sys
import os
from collections import OrderedDict

VALID_OPT_LETTERS = {'A', 'B', 'C', 'D'}


def clean_cell(c):
    """清理单元格内容：去掉首尾空白、统一换行。"""
    if c is None:
        return ''
    s = str(c).strip()
    return s


def normalize_letter(s):
    """从单元格里提取单字母 A/B/C/D（可能附带其他字符）。"""
    if not s:
        return None
    s = str(s).strip()
    # 纯字母
    if s in VALID_OPT_LETTERS:
        return s
    # 含 Y 标记的（如 "Y" 或 "A Y"）
    m = re.search(r'\b([A-D])\b', s)
    if m:
        return m.group(1)
    return None


def parse_inline_options(text):
    """
    旧版格式专用：解析 'question_stem\\na)optA\\nb)optB\\nc)optC\\nd)optD' 这种
    a/b/c/d 小写标记直接拼接的格式，返回 (options_dict, question_stem)。
    选项标记必须独占一行（前有 \\n 或在开头）。
    """
    if not text:
        return {}, ''
    # 用正则找出 a) b) c) d) 的位置（在行首）
    # 不匹配 i)/ii)/iii)/iv) 这种小写罗马数字
    positions = []
    for letter in ['a', 'b', 'c', 'd']:
        pattern = rf'(?:^|\n)\s*{letter}\s*\)'
        for m in re.finditer(pattern, text, re.IGNORECASE):
            positions.append((letter.upper(), m.start(), m.end()))
            break  # 每个字母只取第一个出现的位置
    positions.sort(key=lambda x: x[1])
    if len(positions) != 4:
        return {}, text
    # 题干是第一个选项之前的全部内容
    question_stem = text[:positions[0][1]].strip()
    # 各选项内容
    options = {}
    for i, (letter, start, end) in enumerate(positions):
        if i + 1 < len(positions):
            opt_text = text[end:positions[i + 1][1]].strip()
        else:
            opt_text = text[end:].strip()
        # 去掉开头的换行
        opt_text = opt_text.lstrip('\n').strip()
        options[letter] = opt_text
    return options, question_stem


def extract_pdf_inline_format(pdf_path, source_paper, source_label):
    """
    旧版格式提取器：每行是一道完整题目，选项 a)/b)/c)/d) 拼在题干后。
    表格列: [題號, 參考章節, 題目+選項, 空白, 答案字母]
    """
    all_questions = []
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables()
            except Exception as e:
                print(f'  [warn] page {page_idx} failed: {e}', file=sys.stderr)
                continue
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    row = list(row) + [''] * (5 - len(row))
                    qno_raw = clean_cell(row[0])
                    # 跳过表头和非数字行
                    if not qno_raw or qno_raw == '題號' or not qno_raw.lstrip('Qq').isdigit():
                        continue
                    section = clean_cell(row[1])
                    full_text = clean_cell(row[2])
                    answer = clean_cell(row[4]).upper()
                    # 答案必须合法
                    if answer not in VALID_OPT_LETTERS:
                        # 试 col3
                        answer = clean_cell(row[3]).upper()
                    if answer not in VALID_OPT_LETTERS:
                        continue
                    options, question_stem = parse_inline_options(full_text)
                    if len(options) != 4:
                        # 解析失败，标记 needs_review
                        q = {
                            'source_paper': source_paper,
                            'page': page_idx,
                            'question_no': f'Q{qno_raw.lstrip("Qq")}',
                            'section': section,
                            'question': question_stem or full_text,
                            'options': options,
                            'answer': answer,
                            'explanation': '',
                            'needs_review': True,
                            'parse_issue': f'only {len(options)} options parsed',
                        }
                    else:
                        q = {
                            'source_paper': source_paper,
                            'page': page_idx,
                            'question_no': f'Q{qno_raw.lstrip("Qq")}',
                            'section': section,
                            'question': question_stem,
                            'options': options,
                            'answer': answer,
                            'explanation': '',
                        }
                    all_questions.append(q)
    for i, q in enumerate(all_questions, start=1):
        q['id'] = f'{source_paper}_{i:04d}'
    total = len(all_questions)
    with_answer = sum(1 for q in all_questions if q['answer'] in VALID_OPT_LETTERS)
    with_4_opts = sum(1 for q in all_questions if len(q['options']) == 4)
    return {
        'source_paper': source_paper,
        'source_label': source_label,
        'total_pages': total_pages,
        'stats': {
            'total_questions': total,
            'with_valid_answer': with_answer,
            'with_4_options': with_4_opts,
            'with_explanation': 0,  # 旧版无解析
        },
        'questions': all_questions,
    }


def is_question_header(row):
    """题头行：col0 以 Q 开头或为纯数字。"""
    if not row or len(row) < 3:
        return False
    c0 = clean_cell(row[0])
    # Q18, Q1, 18, etc.
    return bool(re.match(r'^Q?\d+$', c0))


def is_option_row(row):
    """选项行：col1 是单字母 A/B/C/D。"""
    if not row or len(row) < 3:
        return False
    c0 = clean_cell(row[0])
    c1 = clean_cell(row[1])
    # col0 应该为空，col1 是 A/B/C/D
    return (not c0) and (c1 in VALID_OPT_LETTERS)


def has_y_marker(row, col=3):
    """检查指定列是否含 Y 标记（表示该选项是正确答案）。"""
    if len(row) <= col:
        return False
    val = clean_cell(row[col])
    return 'Y' in val or '✓' in val or '√' in val


def parse_table_rows(rows, page_num, source_paper, current_q):
    """
    解析一个表格的行，更新 current_q（跨页延续），返回已完成的题目列表。
    """
    finished = []
    for row in rows:
        if not row:
            continue
        # 补齐到 5 列
        row = list(row) + [''] * (5 - len(row))

        if is_question_header(row):
            # 保存前一道题
            if current_q['question'] and current_q['options']:
                finished.append(current_q)
            qno = clean_cell(row[0])
            section = clean_cell(row[1])
            question = clean_cell(row[2])
            explanation = clean_cell(row[4])
            # 题干可能有 Y 标记混入（异常情况），保留处理
            current_q = {
                'source_paper': source_paper,
                'page': page_num,
                'question_no': qno,
                'section': section,
                'question': question,
                'options': OrderedDict(),
                'answer': '',
                'explanation': explanation,
            }
        elif is_option_row(row):
            if current_q is None or not current_q.get('question'):
                # 选项但没有题头，跳过
                continue
            letter = clean_cell(row[1])
            text = clean_cell(row[2])
            # 选项内容里的 Y 应该去掉（Y 是答案标记，不属于选项文本）
            text = re.sub(r'\s*Y\s*$', '', text).strip()
            current_q['options'][letter] = text
            if has_y_marker(row, col=3):
                current_q['answer'] = letter
        # else: skip noise rows (continuation, empty, etc.)
    return finished, current_q


def extract_pdf(pdf_path, source_paper, source_label):
    """
    提取整个 PDF 的所有题目。
    """
    all_questions = []
    current_q = {
        'source_paper': source_paper,
        'page': 0,
        'question_no': '',
        'section': '',
        'question': '',
        'options': OrderedDict(),
        'answer': '',
        'explanation': '',
    }

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for page_idx, page in enumerate(pdf.pages, start=1):
            try:
                tables = page.extract_tables()
            except Exception as e:
                print(f'  [warn] page {page_idx} extract_tables failed: {e}', file=sys.stderr)
                continue
            for table in tables:
                finished, current_q = parse_table_rows(
                    table, page_idx, source_paper, current_q
                )
                all_questions.extend(finished)
        # 保存最后一题
        if current_q['question'] and current_q['options']:
            all_questions.append(current_q)

    # 重新分配 ID
    for i, q in enumerate(all_questions, start=1):
        q['id'] = f'{source_paper}_{i:04d}'

    # 统计
    total = len(all_questions)
    with_answer = sum(1 for q in all_questions if q['answer'] in VALID_OPT_LETTERS)
    with_4_opts = sum(1 for q in all_questions if len(q['options']) == 4)
    with_explanation = sum(1 for q in all_questions if q['explanation']
                           and '暫未提供' not in q['explanation']
                           and '暫只提供' not in q['explanation'])

    return {
        'source_paper': source_paper,
        'source_label': source_label,
        'total_pages': total_pages,
        'stats': {
            'total_questions': total,
            'with_valid_answer': with_answer,
            'with_4_options': with_4_opts,
            'with_explanation': with_explanation,
        },
        'questions': all_questions,
    }


SOURCES = [
    ('paper1',     'Paper 1.pdf',                                   'Paper 1 - 保險原理及實務 2025',         'new'),
    ('paper3',     'Paper 3.pdf',                                   'Paper 3 - 長期保險 2025',               'new'),
    ('paper1_old', '試卷㇐：保險原理及實務 — 模擬試題2025年版(1).pdf', '試卷一 - 保險原理及實務 (旧版)',         'old'),
    ('paper3_old', '試卷三⾧期保險模擬試題2025年版(1).pdf',          '試卷三 - 長期保險 (旧版)',               'old'),
]


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    raw_dir = os.path.join(base_dir, 'raw')
    os.makedirs(raw_dir, exist_ok=True)

    if len(sys.argv) > 1:
        # 单文件模式: extract_pdf.py <key> <pdf_path> <label> [format]
        key = sys.argv[1]
        pdf_path = sys.argv[2]
        label = sys.argv[3] if len(sys.argv) > 3 else key
        fmt = sys.argv[4] if len(sys.argv) > 4 else 'new'
        sources = [(key, pdf_path, label, fmt)]
    else:
        sources = SOURCES

    summary = []
    for key, pdf_name, label, fmt in sources:
        pdf_path = pdf_name if os.path.isabs(pdf_name) else os.path.join(base_dir, pdf_name)
        if not os.path.exists(pdf_path):
            print(f'[skip] {pdf_path} not found', file=sys.stderr)
            continue
        print(f'=== Extracting {key} ({pdf_name}) [format={fmt}] ===')
        if fmt == 'old':
            result = extract_pdf_inline_format(pdf_path, key, label)
        else:
            result = extract_pdf(pdf_path, key, label)
        sub_dir = os.path.join(raw_dir, key)
        os.makedirs(sub_dir, exist_ok=True)
        out_path = os.path.join(sub_dir, f'{key}_all.json')
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        s = result['stats']
        print(f'  → {out_path}')
        print(f'  questions: {s["total_questions"]}, '
              f'with answer: {s["with_valid_answer"]}, '
              f'with 4 opts: {s["with_4_options"]}, '
              f'with explanation: {s["with_explanation"]}')
        summary.append((key, s))

    print('\n=== Summary ===')
    for key, s in summary:
        print(f'  {key}: {s["total_questions"]} questions '
              f'({s["with_valid_answer"]} with answer, '
              f'{s["with_4_options"]} with 4 opts)')


if __name__ == '__main__':
    main()
