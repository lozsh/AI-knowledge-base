#!/usr/bin/env python3
"""知识库保鲜扫描：按「更新于」日期找出最久没核验过的笔记，并列出含易过期信息的笔记。

这是什么：知识库的季度保鲜工具——产出一份"该复审哪些篇"的待办清单，不做任何修改。
用法：python3 tools/stale_scan.py [文档目录，默认 AI知识库] [--top 20]
更新日期：2026-11-06 · 对应模块：全库 .md 文件
规则：每季度跑一次，逐篇核对清单上的笔记是否仍然成立，核验后把文首
<p class="note-date">更新于 日期</p> 改为新日期。
"""
import os
import re
import sys
from datetime import date

DATE = re.compile(r'<p class="note-date">更新于 (\d{4}-\d{2}-\d{2})</p>')
# 易过期信息：具体版本号、价格、产品对比中的"最新"字样
STALE_HINTS = [
    (re.compile(r'\bv?\d+\.\d+(\.\d+)+\b'), '具体版本号'),
    (re.compile(r'截至|最新|目前最|当前最'), '时效性断言'),
    (re.compile(r'\b(20[12]\d 年 \d{1,2} 月)\b'), '带月份的动态'),
]


def main(docs_dir: str, top: int) -> None:
    rows = []
    today = date.today()
    for root, _dirs, files in os.walk(docs_dir):
        for name in files:
            if not name.endswith('.md') or name == 'index.md':
                continue
            path = os.path.join(root, name)
            with open(path, encoding='utf-8') as f:
                text = f.read()
            m = DATE.search(text)
            if m:
                y, mo, d = map(int, m.group(1).split('-'))
                age = (today - date(y, mo, d)).days
            else:
                age = 9999
            hints = sorted({label for pat, label in STALE_HINTS if pat.search(text)})
            rel = os.path.relpath(path, docs_dir)
            rows.append((age, rel, hints))
    rows.sort(reverse=True)
    print(f'保鲜扫描（今天 {today}）——最久未核验的前 {top} 篇：')
    for age, rel, hints in rows[:top]:
        star = ' ⚠️' if age > 180 else ''
        print(f'  {age:>5} 天  {rel}{star}')
        if hints:
            print(f'          含：{"、".join(hints)}')
    no_date = [r for r in rows if r[0] == 9999]
    if no_date:
        print(f'\n缺少「更新于」日期标记的笔记 {len(no_date)} 篇：')
        for _age, rel, _h in no_date:
            print(f'  {rel}')


if __name__ == '__main__':
    top = 20
    argv = sys.argv[1:]
    if '--top' in argv:
        top = int(argv[argv.index('--top') + 1])
    args = [a for a in argv if not a.startswith('--') and not a.isdigit()]
    main(args[0] if args else 'AI知识库', top)
