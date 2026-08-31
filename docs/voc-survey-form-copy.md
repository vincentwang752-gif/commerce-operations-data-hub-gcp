# VOC 问卷邮箱与订单匹配文案

## 邮箱题提示

建议放在邮箱题说明中，并将该题设为必填：

> Please enter the same email address you used when placing your AirStudio S1 order so we can verify your purchase and apply the warranty extension.

中文内部释义：

> 请填写购买 AirStudio S1 时使用的同一邮箱，以便我们核实订单并为你登记延保。

## 提交前说明

如果表单有开头或结尾说明，可补充：

> Your survey response can only be linked automatically when the email matches your AirStudio S1 order. If you used a different email, our team may contact you to verify the purchase.

## 数据处理口径

| 状态 | 含义 | 后续处理 |
|---|---|---|
| `SYNCED` + `MATCHED` | 问卷已入库，且找到有效 S1 订单 | 写入订单 ID，进入延保审核并触发对应完成事件 |
| `SYNCED` + `REVIEW_REQUIRED` | 问卷已入库，但未按邮箱找到有效 S1 订单 | 保留记录，客服人工核对，不自动发送延保完成事件 |
| `ERROR` | 调用或写入失败 | 自动重试，仍失败则检查 Apps Script、Cloud Run 与 Airtable 日志 |

## 人工核对要求

1. 向客户确认下单邮箱或订单号。
2. 在 Shopify 检查订单是否包含符合资格的 S1 商品，并确认未取消、未全额退款。
3. 在 Airtable 补全客户和订单关联。
4. 更新“对应S1订单ID”和“延保审核状态”。
5. 不覆盖问卷原始邮箱，保留匹配过程和结果。
