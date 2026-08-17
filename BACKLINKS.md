# DSH 外链工作流

本目录采用“自动发现、人工审核、只读监测”的方式增长外链。脚本不会自动评论、发帖、创建 PR、提交表单或联系第三方。

## 每日候选发现

```powershell
python .\backlink-prospects.py --data .\site\data.json --out-dir .\research\backlinks
```

输出文件：

- `research/backlinks/backlink-prospects.json`：机器可读候选池；
- `research/backlinks/backlink-prospects.md`：按分数排序的审核报告；
- `research/backlinks/drafts/github-readme-outreach.md`：README 沟通草稿；
- `research/backlinks/published.json`：人工确认后登记的已发布链接。

## 已发布链接监测

```powershell
python .\backlink-monitor.py --input .\research\backlinks\published.json --output .\research\backlinks\backlink-monitor.json
```

监测脚本只读取公开页面并记录 HTTP 状态、最终地址和内容类型，不修改目标站点。

## 审核边界

- 只处理和 DeepSeek Harness、MCP、AI Agent 或插件开发有直接关系的页面；
- 优先链接到具体插件详情页，避免所有链接都使用首页和同一个锚文本；
- 任何 PR、投稿、评论、私信或表单提交都必须人工确认；
- 不购买链接、不使用 PBN、不做批量评论、不隐藏链接、不绕过 CAPTCHA 或平台限制；
- DR、流量、链接属性等第三方指标必须记录来源、查询时间和 `estimated` 状态。
