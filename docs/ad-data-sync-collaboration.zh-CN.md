# 广告数据同步协作规范

## 目标

广告同事负责确认平台账户、字段和投放口径；数据负责人负责 Google Cloud、BigQuery、Airtable 及跨平台归因。两边可以分别使用 Codex，但所有自动化只读取广告平台数据，不修改广告生产环境。

## 职责分工

| 角色 | 负责 | 不负责 |
|---|---|---|
| 广告同事 | 账户授权、账户清单、平台字段口径、Campaign/Ad 命名、平台数据抽查、平台变更通知 | Airtable 底层关系、跨平台订单归因、生产部署 |
| 数据负责人 | Schema、稳定键、同步代码、BigQuery/Airtable 写入、Shopify/GA4 对账、生产部署和回滚 | 预算、出价、受众、广告状态和投放策略 |
| 管理员 | Google Ads MCC、Meta Business Manager、API App、开发者令牌和紧急撤权 | 日常数据修复 |
| Codex | 生成只读查询、字段映射、测试、差异报告和 Pull Request | 独立获得修改广告生产环境的授权 |

## 两位同事如何同时使用 Codex

1. 共用本仓库，不共用浏览器会话、OAuth Token、Secret 或 Codex 任务。
2. 广告同事从最新 `main` 建分支：
   - Google Ads：`feat/google-ads-sync-日期`
   - Meta Ads：`feat/meta-ads-sync-日期`
3. 每个分支只处理一个平台或一个明确问题，不同时改两套字段口径。
4. 广告同事提交 Pull Request，并填写仓库中的广告同步安全检查项。
5. 数据负责人检查 Schema、幂等键、平台差异、脱敏和 Dry Run 结果。
6. 通过检查后合并；只有合并后的固定版本可以部署到 Google Cloud。
7. 平台侧发生字段、归因窗口、账户或权限变化时，广告同事先提 Issue/PR，不直接在生产任务中临时修改。

提交前先运行 `python scripts/check_ad_sync_read_only.py`。仓库同时提供 `docs/templates/ad-sync-read-only.yml`；由具备 GitHub Workflow 管理权限的管理员复制到 `.github/workflows/` 后，可把同一检查设为每个 PR 的自动闸门。

## 账户登记要求

每个广告账户单独登记，至少包括：

- 平台和账户 ID
- 账户类型：品牌自投、代理商代投或其他供应商
- 内部负责人和外部供应商
- 币种、账户时区和归因窗口
- API 授权状态
- 是否包含合创广告
- 最后成功同步时间
- 当前同步状态和异常说明

真实账户 ID、MCC、Business Manager、App ID 和 Secret 只放在 Airtable 受限视图或 Google Secret Manager，不进入公开 Git。仓库中的示例见 `config/ad-accounts.example.yaml`。

## 每次 Pull Request 必须交付

1. 修改的账户、字段或接口范围。
2. 是否改变历史数据口径。
3. Dry Run 日期范围和返回行数。
4. 与平台后台抽查值的差异。
5. 是否涉及合创广告和未知红人。
6. 幂等键及重复写入验证。
7. 回滚到上一版本的方法。

## 广告同事使用 Codex 的固定任务说明

```text
本任务只处理广告数据的只读同步。

允许读取 Google Ads / Meta Ads 的账户、Campaign、Ad Group/Ad Set、Ad、Creative、花费、曝光、点击、转化和归因字段，并写入 BigQuery 或 Airtable。

禁止创建、修改、启停或删除 Campaign、广告组、广告、素材、受众、预算、出价、转化动作、账户权限和支付信息；禁止使用浏览器自动化操作广告生产后台；禁止把密钥、访问令牌、客户数据或真实生产配置提交到 Git。

所有改动必须在独立分支完成并提交 Pull Request。输出必须包含：修改字段、口径影响、Dry Run 结果、新旧数据差异、幂等验证和回滚方法。如果需要任何广告生产环境写操作，立即停止并请求人工确认。
```

## 日常协作节奏

- 每日：Google Cloud 自动拉取已成熟日期的数据，失败只告警，不自动改变广告。
- 每周：广告同事抽查平台后台，数据负责人检查 BigQuery/Airtable 完整度与 Shopify 差异。
- 平台变化：广告同事在发现后一个工作日内登记，先修改测试配置，再走 PR。
- 紧急异常：暂停同步任务或撤销同步身份，不暂停广告 Campaign。
