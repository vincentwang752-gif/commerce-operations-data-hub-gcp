# 红人与内容归因接口约定

红人数据可以来自自有 Google Sheet、Shopify Collabs、平台代理或其他供应商。所有来源统一进入现有红人和归因数据模型，不为不同来源重复建表。

## Shopify Collabs 当前实现

Shopify Collabs 的持续增量由 Shopify Flow 触发，复用 `services/shopify-order-sync` 已上线的 Cloud Run 和 API Gateway：

1. `Creator Approved` 发送 `event_type=collabs_creator_approved`，upsert「红人」。
2. `Order Attributed` 发送 `event_type=collabs_order_attributed`，upsert「归因触点」并关联「订单」与「红人」。
3. 订单若晚于归因到达，会在订单同步时自动补齐关联。
4. 佣金结算状态不覆盖 Shopify 财务口径；需要固定复盘时再从 Collabs 报告回填或拆字段。

幂等键：

- 红人：优先 `shopify-collabs:{creator_id}`，缺失时再用邮箱、主页或平台 Handle。
- 触点：`shopify-collabs:{order_id}:{creator_id}:{event_id}`。

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
