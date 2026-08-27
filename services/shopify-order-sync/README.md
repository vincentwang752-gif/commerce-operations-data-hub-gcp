# Shopify 订单同步

Shopify Flow 只发送订单 ID；私有 Cloud Run 使用 Admin GraphQL 查询完整订单，并以订单 ID 幂等写入 Airtable。

支持：

- `POST /flow/shopify`：Flow 共享令牌校验
- `POST /webhooks/shopify`：Shopify HMAC 校验
- `POST /reconcile`：按时间范围重新同步
- `GET /health`：健康检查

配置见 `.env.example`，部署见 `deployment.md`，运维见 `operations.md`。
