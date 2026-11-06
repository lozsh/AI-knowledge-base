#!/usr/bin/env python3
"""生成 mkdocs.yml 的显式 nav 列表（两级：大区 → 域 → 篇）。

这是什么：知识库导航生成器——按 6 大区分组（与 00-全貌.md 的 SVG 地图同一套层次），
域内按文件名前缀排序；每域第一篇自动成为域首页（配合 navigation.indexes）。
用法：python3 tools/gen_nav.py [文档目录，默认 AI知识库]  # 输出 YAML 片段到 stdout
更新日期：2026-11-06 · 对应模块：mkdocs.yml nav
"""
import os
import re
import sys

PREFIX = re.compile(r'^\d+-')

BANDS = [
    ('思潮与边界', ['01', '21']),
    ('地基', ['02', '03', '09']),
    ('模型谱系', ['04', '05', '06', '10', '11']),
    ('大模型与智能体', ['07', '08', '18', '22']),
    ('工程与系统', ['12', '13', '14', '15', '16']),
    ('数据与应用', ['23', '24', '17']),
]


def strip_prefix(name: str) -> str:
    if name.endswith('.md'):
        name = name[:-3]
    return PREFIX.sub('', name).strip()


def main(docs_dir: str) -> None:
    domains = sorted(
        d for d in os.listdir(docs_dir)
        if os.path.isdir(os.path.join(docs_dir, d)) and PREFIX.match(d)
    )
    by_num = {d.split('-')[0]: d for d in domains}
    print('nav:')
    print('  - 首页: index.md')
    print('  - 全貌: 00-全貌.md')
    print('  - 标签: tags.md')
    for band, nums in BANDS:
        print(f'  - {band}:')
        for n in nums:
            d = by_num[n]
            notes = sorted(f for f in os.listdir(os.path.join(docs_dir, d)) if f.endswith('.md'))
            print(f'      - {strip_prefix(d)}:')
            for x in notes:
                print(f'          - {d}/{x}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'AI知识库')
