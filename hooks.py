# mkdocs hooks：优先保留显式导航标题，未命名文章使用文件名（保留编号）
import re


def _nav_title(entries, src_uri):
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        for title, target in entry.items():
            if isinstance(target, str) and target == src_uri:
                return title
            if isinstance(target, list):
                nested = _nav_title(target, src_uri)
                if nested is not None:
                    return nested
    return None


def on_page_markdown(markdown, *, page, config, files):
    if page.file.src_uri == "index.md":
        return markdown
    stem = re.sub(r"\.md$", "", page.file.name)
    title = _nav_title(config.get("nav"), page.file.src_uri) or stem
    page.meta["title"] = title
    page.title = title
    return markdown
