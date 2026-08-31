# 两阶段 VOC 调查同步

Google Form 响应进入 Google Sheet 后，Apps Script 调用私有 Cloud Run。服务按邮箱校验符合条件且未取消的订单，随后：

1. 向 Klaviyo 发送阶段完成事件；
2. 更新 Airtable 客户生命周期；
3. 将奖励或延保写为待审核；
4. 将同步状态和错误信息回写 Google Sheet。

当 Airtable 中暂时找不到订单时，服务会使用 Shopify Admin API 按邮箱回查最近的有效产品订单。命中后先把缺失的客户和订单快照补入 Airtable，再继续写入生命周期和 Klaviyo 完成事件。这样历史订单漏导入不会直接造成问卷丢失。

如果仍无法自动匹配订单，问卷也会先写入客户生命周期并标记为“需人工匹配”。这类记录不会自动触发延保完成事件，避免因为邮箱不一致或资格不明而误发权益。Google Sheet 中仍显示 `SYNCED`，表示问卷已经入库；是否完成订单匹配以同步详情中的 `match=MATCHED` / `match=REVIEW_REQUIRED` 和 Airtable 的“延保审核状态”为准。

问卷邮箱题下方应明确提示用户填写下单邮箱：

> Please enter the same email address you used when placing your AirStudio S1 order so we can verify your purchase and apply the warranty extension.

该字段应设为必填。不要自动用其他邮箱模糊匹配订单，以免把延保权益发给错误账户。详细配置见 [`docs/voc-survey-form-copy.md`](../../docs/voc-survey-form-copy.md)。

## Apps Script 属性

- `VOC_ENDPOINT`
- `VOC_WEBHOOK_TOKEN`
- `VOC_STAGE`：1 或 2
- `VOC_INVOKER_SERVICE_ACCOUNT`
- `VOC_MAX_RETRY_ROWS`：每轮最多重试的失败行数，默认 20

两个表单各自安装 `installVocTrigger()`。同一响应 ID 会生成稳定 Klaviyo `unique_id`，减少重试导致的重复事件。
建议同时运行一次 `installVocRetryTrigger()`，每 6 小时自动重试状态为 `ERROR` 的响应。重试仍使用同一 response ID，因此不会重复创建 Klaviyo 事件或 Airtable 订单。

## 产品资格

使用 `ELIGIBLE_PRODUCT_TERMS` 配置产品名或 SKU 匹配词，不在公开代码中写真实商品名称。若找不到订单，问卷仍会入库并返回 `REVIEW_REQUIRED`，随后进入人工检查；系统不会自动发送延保完成事件。

## Shopify 兜底回查

- `SHOPIFY_STORE_DOMAIN`
- `SHOPIFY_API_VERSION`
- `SHOPIFY_ACCESS_TOKEN`：通过 Secret Manager 挂载，不写入环境文件或仓库

兜底回查只在 Airtable 没有符合条件的订单时执行。订单以 Shopify legacy order ID 幂等写入，因此同一份问卷重跑不会重复创建订单。
