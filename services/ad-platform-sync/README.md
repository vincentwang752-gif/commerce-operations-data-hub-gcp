# 广告平台同步接口约定

本目录记录 Google Ads 与 Meta Ads 进入 Airtable 的统一契约。连接器代码需要结合实际账户、MCC/Business Manager 权限和 API App 审核部署，因此公开仓库不包含生产授权配置。

本服务必须保持只读。协作、权限、字段和上线要求见：

- [广告数据同步协作规范](../../docs/ad-data-sync-collaboration.zh-CN.md)
- [广告生产环境安全规范](../../docs/ad-production-safety.zh-CN.md)
- [广告平台字段映射](../../docs/ad-platform-field-mapping.zh-CN.md)
- [脱敏账户配置示例](../../config/ad-accounts.example.yaml)
- [只读策略](policy.json)

## 稳定键

- Campaign：`platform|account_id|campaign_id`
- Ad：`platform|account_id|ad_id`
- Daily performance：`date|platform|account_id|ad_id`

## 必填字段

- 日期、平台、Account ID、Campaign ID、Ad ID
- Campaign/Ad 名称与状态
- 花费、曝光、点击、平台转化和平台转化价值
- 币种、时区、同步来源、最后同步时间

## Meta 合创广告

需要额外写入：合作类型、Creator、供应商/代理商、授权来源和内容资产。Creator 不存在时先进入“待确认”状态；只有稳定平台 ID 或人工证据确认后才能合并到已有红人，不能只凭显示名自动关联。

## 财务口径

广告平台收入只保留为平台口径。ROAS 报表应同时展示平台 ROAS 与基于 Shopify 归因订单的可验证 ROAS。

## Google Ads 只读 Dry Run

首版连接器覆盖 Customer、Campaign、Ad Group、Ad 和按 `segments.date` 的日级表现。
代码只调用 Google Ads SDK 的 GAQL 报表查询，并且当前版本没有任何数据写入路径或生产调度配置。

运行时配置必须来自本地环境或 Secret Manager。`GOOGLE_ADS_ACCOUNTS_JSON` 是批准账户清单，
同时支持品牌自投和代理商代投；真实 Customer ID 和 MCC ID 不得写入仓库。例如：

```powershell
$env:READ_ONLY = "true"
$env:GOOGLE_ADS_ACCOUNTS_JSON = '[{"alias":"brand_us","customer_id":"<secret>","account_type":"brand_managed"},{"alias":"agency_us","customer_id":"<secret>","login_customer_id":"<secret>","account_type":"agency_managed","agency":"agency_alias"}]'
$env:GOOGLE_ADS_DEVELOPER_TOKEN = "<secret>"
$env:GOOGLE_ADS_CLIENT_ID = "<secret>"
$env:GOOGLE_ADS_CLIENT_SECRET = "<secret>"
$env:GOOGLE_ADS_REFRESH_TOKEN = "<secret>"
python google_ads_sync.py --dry-run --start-date 2026-08-27 --end-date 2026-08-27
```

Dry Run 输出仅包含账户别名、账户类型、币种、时区、日期范围及各层级返回行数，
不会输出 Customer ID 或凭证。默认窗口为 T-4；显式日期按各 Google Ads 账户自身时区解释。

稳定幂等键：

- Campaign：`google_ads|customer_id|campaign_id`
- Ad Group：`google_ads|customer_id|ad_group_id`
- Ad：`google_ads|customer_id|ad_id`
- 日级表现：`date|google_ads|customer_id|ad_id`

当前版本不写 BigQuery/Airtable，因此重复运行的写入行数始终为 0。后续接入存储时应以这些键执行覆盖更新。
