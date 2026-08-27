# Shopify 订单同步

生产环境优先由 Shopify Flow 发送完整订单快照，私有 Cloud Run 直接以订单 ID 幂等写入 Airtable。这样即使当前 Shopify 操作账号没有 Dev Dashboard 建应用权限，也能持续同步新订单。

取得 Shopify Admin API 权限后，可启用“只传订单 ID后由 Cloud Run 查询完整订单”、原生 Webhook、退款刷新和定时对账。两种接入方式使用同一套字段映射和幂等写入逻辑。

支持：

- `POST /flow/shopify`：Flow 共享令牌校验
- `POST /webhooks/shopify`：Shopify HMAC 校验
- `POST /reconcile`：按时间范围重新同步
- `GET /health`：健康检查

## 当前推荐的 Shopify Flow 请求体

请求头继续使用 API Gateway API key 和 `X-Shopify-Flow-Token`。请求体使用 `shopify-flow-order-payload.json.liquid` 中的模板，至少包含：

- `order.legacyResourceId`
- 下单时间、邮箱、币种、订单金额与折扣
- 付款状态、履约状态、取消时间
- Shopify 客户 ID、国家/地区
- 商品标题、SKU、数量和变体

Flow 当前可提供的快照不含完整退款交易、Landing Site、Referring Site 和部分归因字段，因此这些字段需要 Admin API/Webhook 或 GA4/广告数据补足。Shopify 订单和收入仍是财务主口径。

配置见 `.env.example`，部署见 `deployment.md`，运维见 `operations.md`。
