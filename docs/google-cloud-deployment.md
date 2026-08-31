# Google Cloud 部署

## 需要启用的 API

- Cloud Run
- Cloud Build / Artifact Registry
- Secret Manager
- IAM Credentials
- Cloud Scheduler
- BigQuery
- Google Analytics Data API
- API Gateway（Shopify Flow 外部入口需要时）

## 服务账号

- 每个 Cloud Run 服务使用独立运行账号。
- GA4 同步账号只授予目标 GA4 Property 的读取权、BigQuery 数据写入权和所需 Secret 访问权。
- Shopify 同步账号只读取对应 Secret，不授予项目管理员权限。
- VOC 同步账号需要读取 Airtable、问卷 Webhook 和 Shopify Admin Token Secret；Shopify Token 仅用于 Airtable 漏单时的订单资格回查与补写。
- Apps Script 调用私有 VOC 服务时，使用专用账号并仅授予 `roles/run.invoker`。

## Secret Manager

建议保存：

- `AIRTABLE_TOKEN`
- `SHOPIFY_ACCESS_TOKEN`
- `SHOPIFY_FLOW_TOKEN`
- `SHOPIFY_WEBHOOK_SECRET`
- `VOC_WEBHOOK_TOKEN`
- `KLAVIYO_PRIVATE_API_KEY`（如果改用私有 Events API）

普通环境变量只保存表名、字段名、时区、数据集名和非敏感业务配置。

## 部署 Cloud Run

在对应服务目录执行：

```bash
gcloud run deploy SERVICE_NAME \
  --source . \
  --region REGION \
  --service-account RUNTIME_SERVICE_ACCOUNT \
  --no-allow-unauthenticated
```

部署后用 `--set-secrets` 和 `--update-env-vars` 注入配置。不要把真实值写入仓库脚本。

## GA4 定时任务

推荐每天 09:00（业务时区）调用 GA4 服务。代码默认只读取 T-4，因此即使任务每天运行，也不会采集最近三个完整自然日。

```bash
gcloud scheduler jobs create http ga4-daily-sync \
  --schedule="0 9 * * *" \
  --time-zone="Asia/Shanghai" \
  --uri="CLOUD_RUN_URL" \
  --http-method=POST \
  --oidc-service-account-email=SCHEDULER_CALLER
```

如果需要先审核配置，可在创建后立即暂停，确认权限与字段映射后再恢复。

## BigQuery

- 日级表按 `date` 分区。
- 使用 `date + property_id` 作为合并键。
- Cloud Run 先写临时表，再使用 `MERGE` 保证重跑幂等。

## Airtable

- 使用 Personal Access Token，权限只覆盖目标 Base。
- 以稳定业务键执行 upsert。
- 每批最多 10 条写入，遇到 429 应退避重试。
