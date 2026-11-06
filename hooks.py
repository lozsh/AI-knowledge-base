# mkdocs hooks：让导航/搜索标题使用文件名（保留编号），而非正文首行标题
import re


def on_page_markdown(markdown, *, page, config, files):
    if page.file.src_uri == "index.md":
        return markdown
    stem = re.sub(r"\.md$", "", page.file.name)
    page.meta["title"] = stem
    page.title = stem
    return markdown
