# 实施状态

| 模块 | 仓库状态 | 说明 |
|---|---|---|
| Shopify 新订单同步 | 已实现 | Flow/Webhook → Cloud Run → Airtable |
| Shopify 对账补数 | 已实现 | 按时间范围重新读取并幂等写入 |
| GA4 全站日级数据 | 已实现 | T-4 → BigQuery + Airtable |
| GA4 渠道/落地页/商品粒度 | Schema 已定义 | 需要在 Data API 请求中增加维度并控制行数 |
| GA4 五类用户细分 | Schema 与口径已定义 | 建议用 GA4 Audience/Exploration 验证后再自动化 |
| 两阶段 VOC | 已实现 | Forms/Sheets → Apps Script → Cloud Run → Airtable/Klaviyo |
| Google Ads 日级同步 | 数据模型完成 | 连接器需按实际账号权限部署 |
| Meta Ads 日级同步 | 数据模型完成 | 需额外处理合创广告和红人关联 |
| 红人表格/Collabs 自动同步 | 数据模型完成 | 外部表格去重和来源优先级仍需配置 |
| Airtable Interface | 页面结构完成 | 可按管理层使用反馈继续迭代 |

“Schema 已定义”不等于平台 API 已上线。公开文档把两者分开，避免误导使用者。
