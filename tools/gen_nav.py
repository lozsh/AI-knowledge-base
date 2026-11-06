#!/usr/bin/env python3
"""生成 mkdocs.yml 的显式 nav 列表。

这是什么：知识库导航生成器——扫描文档目录，按"域目录名排序 + 域内文件名前缀排序"
输出 nav 片段；写入后 mkdocs 页序不再依赖文件名猜测，且每域第一篇自动成为域首页
（配合 navigation.indexes）。
用法：python3 tools/gen_nav.py [文档目录，默认 AI知识库]  # 输出 YAML 片段到 stdout
更新日期：2026-11-06 · 对应模块：mkdocs.yml nav
"""
import os
import re
import sys

PREFIX = re.compile(r'^\d+-')


def strip_prefix(name: str) -> str:
    if name.endswith('.md'):
        name = name[:-3]
    return PREFIX.sub('', name).strip()


def main(docs_dir: str) -> None:
    domains = sorted(
        d for d in os.listdir(docs_dir)
        if os.path.isdir(os.path.join(docs_dir, d)) and PREFIX.match(d)
    )
    print('nav:')
    print('  - 首页: index.md')
    print('  - 全貌: 00-全貌.md')
    for d in domains:
        notes = sorted(
            n for n in os.listdir(os.path.join(docs_dir, d))
            if n.endswith('.md')
        )
        print(f'  - {strip_prefix(d)}:')
        for n in notes:
            print(f'      - {d}/{n}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'AI知识库')
