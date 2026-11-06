#!/usr/bin/env python3
"""全库 markdown 相对链接统一改写：
- 以"文件 basename"为全局键建立索引（前提：全库无重名）
- delete_map.json: 被并文件 basename → 基底 basename
- 对每个 .md 里的每个 .md 链接目标（含 URL 编码、含空格、含 <> 包裹、含 #锚点）：
  解码 → basename → 查映射 → 计算从当前文件的正确相对路径 → 重新编码写回
用法: python3 -I relink.py <repo_root> [delete_map.json]
"""
import json, os, re, sys, pathlib, urllib.parse

root = pathlib.Path(sys.argv[1]).resolve()
delete_map = {}
if len(sys.argv) > 2:
    delete_map = json.loads(pathlib.Path(sys.argv[2]).read_text())

files = sorted(p for p in root.rglob('*.md'))
index = {p.name: p for p in files}

# 形式1: ](<target>)  可含 #anchor；形式2: ](target) 可含空格与 #anchor
ANGLE = re.compile(r'\]\(<([^)<>\n]+?\.md)(#[^)\n]*)?>\)')
PLAIN = re.compile(r'\]\(([^()\n]+?\.md)(#[^)\n]*)?\)')

changed_files = 0
total_links = 0
rewritten = 0
missing = []

def fix_target(cur: pathlib.Path, raw: str, anchor: str):
    dec = urllib.parse.unquote(raw)
    base = os.path.basename(dec)
    if base not in delete_map:
        cand = (cur.parent / dec)
        # 原样可解析、无空格破坏 → 保留原样
        if ' ' not in raw and cand.exists():
            return 'KEEP'
    base = delete_map.get(base, base)
    if base not in index:
        missing.append((str(cur.relative_to(root)), raw))
        return None
    rel = os.path.relpath(index[base], cur.parent)
    return urllib.parse.quote(rel) + (anchor or '')

def process(p: pathlib.Path, text: str):
    global rewritten
    result = text
    for pat in (ANGLE, PLAIN):
        out, pos, n = [], 0, 0
        for m in pat.finditer(result):
            raw, anchor = m.group(1), m.group(2) or ''
            global_total[0] += 1
            new = fix_target(p, raw, anchor)
            if new is None or new == 'KEEP':
                continue
            new_full = '](' + new + ')'
            if new_full != m.group(0):
                out.append(result[pos:m.start()]); out.append(new_full)
                pos = m.end(); n += 1
        out.append(result[pos:])
        if n:
            rewritten += n
            result = ''.join(out)
    return result

global_total = [0]

for p in files:
    text = p.read_text()
    new_text = process(p, text)
    if new_text != text:
        p.write_text(new_text)
        changed_files += 1

print(f'扫描链接 {global_total[0]} 条，改写 {rewritten} 条（涉及 {changed_files} 个文件）')
if missing:
    print(f'未解析目标 {len(missing)} 条：')
    for f, raw in missing[:40]:
        print('  ', f, '->', raw)
else:
    print('全部目标可解析')
