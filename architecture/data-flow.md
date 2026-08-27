# 数据流与系统边界

## 写入链路

1. Shopify 新订单触发 Flow，Flow 将当前订单快照发送给 Cloud Run；有应用权限时也可使用 Webhook。
2. Cloud Run 直接消费 Flow 快照；配置 Admin API 后，可按订单 ID 重新查询规范订单并执行退款刷新、更新和定时对账。
3. 订单以 `Shopify Order ID` 幂等写入 Airtable。
4. GA4 Cloud Run 每日读取 T-4，并合并到 BigQuery 和 Airtable 日级表。
5. Google Forms 提交后由 Apps Script 调用 VOC Cloud Run；服务先校验符合条件的订单，再发 Klaviyo 事件并写客户生命周期。
6. 广告平台日级表现进入广告系列、广告、广告每日表现三张表；合创广告同时关联对应红人。
7. 归因触点表统一保存 UTM、Coupon、Creator、Campaign、平台 Click ID 和证据等级。

## 分层

- Source：Shopify、GA4、Google Ads、Meta Ads、Google Forms、Klaviyo。
- Ingestion：Cloud Run、Apps Script、Cloud Scheduler、平台 API。
- History：BigQuery，适合长期历史、重算和大表查询。
- Operations：Airtable，适合中文字段、人工审核、运营协作和 Interface。
- Activation：Klaviyo、售后流程、投放与红人复盘。

## 不做的事

- 不用 GA4 收入覆盖 Shopify 净收入。
- 不把广告平台自报转化当作唯一真实订单。
- 不仅凭最后一次点击把订单永久归给某个红人。
- 不在 Git、GA4 或 UTM 中保存客户 PII。
- 不让问卷自动化直接修改实际售后保修记录；只进入待审核队列。
