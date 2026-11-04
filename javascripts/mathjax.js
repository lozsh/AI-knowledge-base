// MathJax 配置：配合 pymdownx.arithmatex (generic) 使用
// 行内 \(…\) 与块级 \[…\]（arithmatex 会把 $…$ / $$…$$ 转成这两种定界符）
window.MathJax = {
  tex: {
    inlineMath: [["\\(", "\\)"]],
    displayMath: [["\\[", "\\]"]],
    processEscapes: true,
    processEnvironments: true
  },
  options: {
    ignoreHtmlClass: ".*",
    processHtmlClass: "arithmatex"
  }
};
