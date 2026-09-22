# A股研究站：构建与发布

只发布 **Jadyli/stock · feature/1.0** 的两类研究报告，不读取其他仓库。本配置不改变源仓库可见性；网站公开与仓库公开是两件事。

## 内容来源与功能

```text
盘前策略/YYYY年M月/M月D日盘前分析.md
涨停分析/YYYY年M月/M月D日涨停复盘.md
```

任务继续按原规则提交 Markdown，不需要另做 HTML、不需要修改目录。构建时自动生成首页、两个栏目、月份归档、同日关联、文章目录、全文搜索和 Markdown 下载。历史报告全部保留，日期按数值从新到旧排序。没有报告时显示真实的空状态，不生成示例行情或示例报告。

采用 Python + markdown-it-py 生成纯静态网页，无数据库、无 Node 环境、无运行时 CDN 或第三方搜索服务。搜索支持中文子串、股票代码，以及用空格分隔的多个关键词；完整索引在首次搜索时载入浏览器。网站适配手机，支持深浅色、宽表横向滚动与浏览器打印。

## 首次启用 GitHub Pages

1. 打开 https://github.com/Jadyli/stock/settings/pages 。
2. 在 **Build and deployment → Source** 选择 **GitHub Actions**。
3. 打开 https://github.com/Jadyli/stock/actions/workflows/stock-pages.yml ，选择 **Run workflow → feature/1.0 → Run workflow**。若先前因 Pages 未启用而失败，也可重新运行该次工作流。
4. 确认 build 与 deploy 均成功，再用未登录窗口访问 https://jadyli.github.io/stock/ 。源码提交成功不等于网站已发布。

若设置页提示当前套餐不能从私有仓库使用 Pages，须先解决套餐资格。GitHub Free 支持公开仓库 Pages；个人私有仓库需要支持该功能的套餐，例如 GitHub Pro。本配置不会自动升级套餐或公开仓库。不要把个人访问令牌放进仓库或前端文件。

如果 `github-pages` 环境限制了可部署分支，请在 **Settings → Environments → github-pages** 允许 `feature/1.0`。仅在确有环境限制报错时调整，并保留其他保护设置。

## 自动更新

`.github/workflows/stock-pages.yml` 监听 `feature/1.0`：报告 Markdown、`site/` 代码或工作流自身变更会触发构建。每次构建两个栏目的完整网站，再整体部署，避免相互覆盖。不向源分支回写 HTML，不创建 PR，不访问其他仓库。

外部 GitHub 连接的提交已可触发普通 push 工作流。若未来改为用 GitHub Actions 自带的 `GITHUB_TOKEN` 提交文件，这类提交不会再次触发普通 push 工作流；应在同一工作流调用发布逻辑或显式 dispatch。不要公开凭证或增加未授权的定时器。

网站构建时间与报告行情时点分开展示，以各篇正文的数据截止时间为准。排队、构建和部署状态以 Actions 页面为准，不保证与提交瞬时同步。

## 本地构建

使用 Python 3.10 或以上：

```bash
python3 -m venv .site-venv
.site-venv/bin/python -m pip install -r site/requirements.txt
.site-venv/bin/python -m unittest discover -s site -p 'test_*.py' -v
.site-venv/bin/python site/build.py --base / --output _site-preview
.site-venv/bin/python -m http.server 8000 --directory _site-preview
```

打开 http://localhost:8000/ 。正式 Pages 构建使用 `--base /stock/ --output _site`。生成目录不提交到源分支；发布 artifact 只包含构建出的静态网站。

## 发布边界

仅收录两个指定目录中符合日期命名的报告，忽略根目录 README、其他说明和其他目录；拒绝符号链接、无效日期、空报告和同类同日重复文件。构建只清理显式指定的 `_site` / `_site-preview` 输出目录。

Markdown 原始 HTML 不执行，危险链接由解析器过滤，报告不会作为 Python、JavaScript 或 Vue 模板执行。表格不截断，引用链接保留。测试在临时目录使用合成文档，不向真实报告目录写入测试内容。`manifest.json` 记录收录路径、内容摘要与网页路径，便于核验。

**这是公开网站。** 被收录的正文、下载文件和搜索索引都可被他人阅读，请勿在报告中写入凭证、个人隐私或未授权资料。本地相对图片、HTML 图表及 Mermaid 图形需要另外适配；当前任务应继续生成可独立阅读的 Markdown。

## 官方参考

- Pages 创建与套餐：https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site
- Actions 发布：https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- 工作流事件：https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- Markdown 解析器：https://markdown-it-py.readthedocs.io/
