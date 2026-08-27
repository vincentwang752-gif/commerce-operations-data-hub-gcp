# 广告平台同步接口约定

本目录记录 Google Ads 与 Meta Ads 进入 Airtable 的统一契约。连接器代码需要结合实际账户、MCC/Business Manager 权限和 API App 审核部署，因此公开仓库不包含生产授权配置。

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

需要额外写入：合作类型、Creator、供应商/代理商、授权来源和内容资产。Creator 不存在时先写入红人主表，再建立关联，不能只把名字放在备注中。

## 财务口径

广告平台收入只保留为平台口径。ROAS 报表应同时展示平台 ROAS 与基于 Shopify 归因订单的可验证 ROAS。
