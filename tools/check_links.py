#!/usr/bin/env python3
"""AI 知识库全站链接体检：扫描所有 Markdown 相对链接（含 URL 编码形式），校验目标文件存在。

这是什么：知识库的防坏链闸门，本地与 CI（.github/workflows/ci.yml）共用。
用法：python3 tools/check_links.py [知识库文档目录，默认 AI知识库]
更新日期：2026-11-06 · 对应模块：全库 .md 文件
"""
import os
import re
import sys
import urllib.parse

ANGLE = re.compile(r'\]\(<([^)<>\n]+?\.md)(#[^)\n]*)?>\)')
PLAIN = re.compile(r'\]\(([^()\s]+?\.md)(#[^)\n]*)?\)')


def main(docs_dir: str) -> int:
    docs_dir = os.path.abspath(docs_dir)
    bad = []
    checked = 0
    for root, _dirs, files in os.walk(docs_dir):
        for name in files:
            if not name.endswith('.md'):
                continue
            path = os.path.join(root, name)
            with open(path, encoding='utf-8') as f:
                text = f.read()
            for m in PLAIN.finditer(text):
                checked += 1
                bad += check(path, docs_dir, m.group(1), text, m.start())
            for m in ANGLE.finditer(text):
                checked += 1
                bad += check(path, docs_dir, m.group(1), text, m.start())
    print(f'链接总数：{checked}，坏链：{len(bad)}')
    for path, target, line in bad:
        print(f'  坏链 {path}:{line} -> {target}')
    return 1 if bad else 0


def check(path: str, docs_dir: str, raw: str, text: str, pos: int) -> list:
    line = text.count('\n', 0, pos) + 1
    if re.match(r'^[a-z]+://', raw) or raw.startswith('/'):
        return []
    target = urllib.parse.unquote(raw.split('#')[0])
    full = os.path.normpath(os.path.join(os.path.dirname(path), target))
    if os.path.isfile(full):
        return []
    return [(path, raw, line)]


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'AI知识库'))
