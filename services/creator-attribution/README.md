# 红人与内容归因接口约定

红人数据可以来自自有 Google Sheet、Shopify Collabs、平台代理或其他供应商。所有来源统一进入“红人、红人合作、内容资产、归因触点”四张表。

## 去重

- 首选平台 + Handle / Channel ID。
- 其次使用规范化主页 URL。
- 邮箱只用于内部匹配，不作为公开标识，也不进入 GA4/UTM。
- 来源冲突时保留原始来源，并指定一个主记录。

## 自动更新建议

1. Cloud Scheduler 每日调用 Cloud Run。
2. 读取各 Google Sheet 和 Collabs/API 的增量记录。
3. 标准化平台、Handle、链接、Coupon、UTM 和供应商。
4. 以稳定 Creator Key upsert 红人，再 upsert 合作和内容。
5. Shopify 新订单根据 Coupon/UTM/Click ID 生成归因触点。
6. 不确定关联进入人工审核视图，不自动计入确定归因收入。
