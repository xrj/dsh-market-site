# 部署迁移说明

主站部署仓库与公开数据/外链仓库分开：

- 主站：`xrj/dsh-market-site`；
- 目录快照和外链：`xrj/dsh-plugin-registry`；
- 生产站：`dsh-market` Cloudflare Pages 项目。

主站仓库只提交构建器、模板、品牌资源和一份目录基线。每日生成的详情页不提交到 Git，避免仓库不断膨胀。

工作流会在校验通过后，仅在目录有实质变化时更新 `site/data.json`，再部署静态产物。快照 push 失败时不会继续部署，防止下一次任务使用过期基线。

