# 指标口径与平台差异

| 指标 | 定义 | 主来源 |
|---|---|---|
| 订单数 | 排除测试/取消后，按 Shopify 订单 ID 去重 | Shopify |
| 净收入 | 订单收入减折扣和退款，税费/运费口径需固定 | Shopify |
| 活跃用户 | GA4 Active users | GA4 |
| 会话数 | GA4 Sessions | GA4 |
| 平均互动时长 | User engagement duration / Sessions | GA4 |
| 高意向未购 | 发生产品查看、加购或开始结账，但在分析窗口内没有 purchase 的用户 | GA4 用户细分 |
| 加购未结账 | 发生 add_to_cart 且没有 begin_checkout 的用户 | GA4 用户细分 |
| 结账放弃 | 发生 begin_checkout 且没有 purchase 的用户 | GA4 用户细分 |
| 广告花费 | 平台日级 Spend | Google Ads / Meta Ads |
| 平台收入 | 广告平台自身归因模型下的转化价值 | 广告平台 |
| 归因订单 | 至少有可解释触点证据的 Shopify 订单 | Airtable + Shopify |

## 为什么会不一致

- 用户拒绝 Cookie、跨设备或浏览器限制，会让 GA4 少记产品查看和购买。
- Shopify 快捷购买、购物车抽屉或结账域名追踪不完整，会出现开始结账高于加购或购买者没有 view_item。
- GA4 用户细分若排除条件设置为“同一事件/同一会话”而不是“整个用户窗口”，会出现所谓未结账人群仍有结账事件。
- 广告平台使用自己的归因窗口、建模转化和时区，通常不会与 Shopify 一致。
- GA4 数据有成熟延迟，本项目默认每日读取 T-4。

这些差异需要通过来源字段、同步时间、差值和异常状态呈现，而不是直接覆盖任一平台数据。
