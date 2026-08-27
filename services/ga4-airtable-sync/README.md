# GA4 日级同步

每天读取一个已经成熟的自然日，默认 T-4，并将结果合并到 BigQuery 和 Airtable。

## 当前写入指标

- 活跃用户、新用户、会话、互动会话、互动率
- 浏览量、平均互动时长
- 购买用户、购买事件、GA4 购买收入

GA4 用于行为和平台归因，订单与净收入仍以 Shopify 为准。代码写入 Airtable 的中文字段名，不依赖生产 Field ID。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
pytest -q
flask --app main run --debug
```

生产环境应使用私有 Cloud Run，并由 Cloud Scheduler 通过 OIDC 每日调用。
