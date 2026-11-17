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


def on_post_page(output, *, page, config):
    # 在首屏布局前恢复选择；存储被禁用时仍可使用本次页面开关。
    bootstrap = """<script>
try {
  if (localStorage.getItem('aikb-immersive-reading') === 'on') {
    document.documentElement.dataset.readingMode = 'immersive';
  }
} catch (_) {}
</script>"""
    controls = """<script>
(() => {
  const root = document.documentElement;
  const key = 'aikb-immersive-reading';
  function mount() {
    const header = document.querySelector('.md-header__inner');
    if (!header || document.getElementById('kb-reading-toggle')) return;
    const button = document.createElement('button');
    button.id = 'kb-reading-toggle';
    button.type = 'button';
    button.className = 'kb-reading-toggle';
    button.innerHTML = '<svg aria-hidden="true" viewBox="0 0 24 24"><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/></svg><span></span>';
    const search = header.querySelector('label[for="__search"]');
    header.insertBefore(button, search || header.querySelector('.md-header__source'));
    function render() {
      const active = root.dataset.readingMode === 'immersive';
      const label = active ? '退出沉浸' : '沉浸阅读';
      button.querySelector('span').textContent = label;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', String(active));
      button.title = active ? '退出沉浸阅读（Esc）' : '沉浸阅读：隐藏侧栏，拓宽正文';
    }
    function setMode(active) {
      if (active) root.dataset.readingMode = 'immersive';
      else delete root.dataset.readingMode;
      // 防止进入沉浸后手机抽屉仍挡住正文。
      const drawer = document.getElementById('__drawer');
      if (drawer) drawer.checked = false;
      try { localStorage.setItem(key, active ? 'on' : 'off'); } catch (_) {}
      render();
      window.dispatchEvent(new Event('resize'));
    }
    button.addEventListener('click', () => setMode(root.dataset.readingMode !== 'immersive'));
    document.addEventListener('keydown', event => {
      const search = document.getElementById('__search');
      if (event.key !== 'Escape' || event.defaultPrevented || (search && search.checked)) return;
      if (event.target.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')) return;
      if (root.dataset.readingMode === 'immersive') {
        setMode(false);
        button.focus();
      }
    });
    render();
  }
  mount();
  if (typeof document$ !== 'undefined') document$.subscribe(mount);
})();
</script>"""
    return output.replace('</head>', bootstrap + '</head>', 1).replace('</body>', controls + '</body>', 1)
