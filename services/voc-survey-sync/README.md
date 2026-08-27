# 两阶段 VOC 调查同步

Google Form 响应进入 Google Sheet 后，Apps Script 调用私有 Cloud Run。服务按邮箱校验符合条件且未取消的订单，随后：

1. 向 Klaviyo 发送阶段完成事件；
2. 更新 Airtable 客户生命周期；
3. 将奖励或延保写为待审核；
4. 将同步状态和错误信息回写 Google Sheet。

## Apps Script 属性

- `VOC_ENDPOINT`
- `VOC_WEBHOOK_TOKEN`
- `VOC_STAGE`：1 或 2
- `VOC_INVOKER_SERVICE_ACCOUNT`

两个表单各自安装 `installVocTrigger()`。同一响应 ID 会生成稳定 Klaviyo `unique_id`，减少重试导致的重复事件。

## 产品资格

使用 `ELIGIBLE_PRODUCT_TERMS` 配置产品名或 SKU 匹配词，不在公开代码中写真实商品名称。若找不到订单，返回 `INELIGIBLE` 并进入人工检查。
