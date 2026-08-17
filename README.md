# DSH 插件集市

DSH 插件集市的静态站源码和自动部署配置。

线上地址：<https://dsh-market.pages.dev/>

## 自动部署

`.github/workflows/daily-deploy.yml` 每天按北京时间约 03:30 运行，也支持 GitHub Actions 页面手动触发。

工作流会：

1. 用 GitHub API 检查 `dsh-plugin` 数据源；
2. 运行 `python build.py --fetch`；
3. 校验目录数量、详情页、Sitemap 和数据变化；
4. 通过 `CLOUDFLARE_API_TOKEN` 和 `CLOUDFLARE_ACCOUNT_ID` 部署到现有 Cloudflare Pages 项目；
5. 对首页、`robots.txt`、`sitemap.xml` 和一个详情页做线上检查。

数据异常、抓取失败、快照大幅减少或密钥未配置时，工作流会停止，不部署新版本。

## 必需的 GitHub Secrets

- `CLOUDFLARE_API_TOKEN`：只授予 Pages 部署权限的 Cloudflare API Token；
- `CLOUDFLARE_ACCOUNT_ID`：Cloudflare 账户 ID。

密钥只放在 GitHub Actions Secrets，不写入源码、目录数据或日志。

