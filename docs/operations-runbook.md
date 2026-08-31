# 运营与故障处理

## 每日检查

- Shopify 最新订单是否写入，订单 ID 是否唯一。
- GA4 表最新日期是否为 T-4，且同步来源和时间完整。
- Shopify 订单数/净收入与 GA4 购买事件/收入差值是否异常扩大。
- 广告花费是否按账户和日期完整写入。
- VOC Google Sheet 是否出现 `ERROR`、`INELIGIBLE` 或需人工匹配。

## 订单漏数

1. 用 Shopify Order ID 查 Airtable。
2. 检查 Flow/Webhook 日志和 Cloud Run 请求日志。
3. 确认订单是否在应用可读取范围及 API Scope 内。
4. 调用 `/reconcile` 对指定时间段补数。
5. 重跑后确认同一订单被更新而非重复新增。

## GA4 缺数

1. 确认目标日期早于当前日期四天。
2. 检查 GA4 Property 权限和 Data API 配额。
3. 检查 BigQuery 临时表与 MERGE 日志。
4. 检查 Airtable 字段名是否与 Schema 一致。
5. 重跑同一天；稳定键会覆盖更新。

## VOC 未匹配订单

- Google Sheet 的 `SYNCED` 只表示问卷已经写入数据中台，不代表订单资格已经确认。
- 同步详情出现 `match=MATCHED` 才代表自动匹配成功；`match=REVIEW_REQUIRED` 必须人工检查。
- 标准化邮箱大小写与空格。
- 确认订单同步已经完成。
- 检查产品匹配词、取消状态和订单时间。
- 若 Airtable 缺少历史订单，确认 VOC 服务已配置 Shopify Admin API 兜底回查；命中后应先补客户和订单，再写生命周期。
- Google Sheet 中的 `ERROR` 行由 `retryFailedResponses` 每 6 小时重试，也可选中单行运行 `testSelectedResponse`。
- 若客户使用不同邮箱，先由客服向客户确认下单邮箱，再用 Shopify 核对有效 S1 订单。确认前保持“需人工匹配”，不自动扩大资格条件。
- 人工确认后，在 Airtable 填写“对应S1订单ID”，将“延保审核状态”改为“待审核”或“已确认”；保留原问卷邮箱，便于审计。

### 问卷上线检查

- 邮箱题设为必填。
- 邮箱题下显示“请填写下单时使用的同一邮箱”的提示。
- 提交一次测试响应，确认同步详情同时写出 `match=`、`order=`（匹配时）和 `lifecycle=`。
- 不要把 `REVIEW_REQUIRED` 当成系统失败，也不要自动发送延保完成邮件。

## 广告与红人

- Campaign Key 必须包含平台和 Account ID。
- 合创广告缺红人时，先在红人表建立供应商来源记录再关联。
- Coupon 和 UTM 冲突时保留两条触点，并交由归因规则/人工判断。

## 变更管理

- Airtable 字段改名后，同步代码和 Schema 必须一起更新。
- 先在测试 Base 验证，再切生产 Base。
- 密钥轮换后检查 Cloud Run Revision 是否读取最新 Secret。
- 不删除历史字段；先停写、迁移、验证，再隐藏或弃用。
