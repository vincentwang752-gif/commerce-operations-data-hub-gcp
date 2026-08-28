# 实施状态

| 模块 | 仓库状态 | 说明 |
|---|---|---|
| Shopify 新订单同步 | 已上线 | Flow 完整订单快照 → Cloud Run → Airtable；不依赖 Admin API Token |
| Shopify 新订单归因触点 | 已实现、待部署 | 实时订单按专属 Coupon、Click ID、UTM、Referrer 生成幂等触点；每单仅一个最终触点计收入；不回填历史 |
| Shopify 手动补数 | 已验证 | Shopify 订单批量运行同一 Flow，并按订单 ID 幂等写入 |
| Shopify 自动对账补数 | 代码已实现、生产未启用 | 需要 Shopify Admin API 凭证后才能按时间范围重新读取 |
| GA4 全站日级数据 | 已实现 | T-4 → BigQuery + Airtable |
| GA4 渠道/落地页/商品粒度 | Schema 已定义 | 需要在 Data API 请求中增加维度并控制行数 |
| GA4 五类用户细分 | Schema 与口径已定义 | 建议用 GA4 Audience/Exploration 验证后再自动化 |
| 两阶段 VOC | 已实现 | Forms/Sheets → Apps Script → Cloud Run → Airtable/Klaviyo |
| Google Ads 日级同步 | 数据模型完成 | 连接器需按实际账号权限部署 |
| Meta Ads 日级同步 | 数据模型完成 | 需额外处理合创广告和红人关联 |
| Shopify Collabs 红人与订单归因同步 | 已上线 | 新事件自动写入；平台确认归因会覆盖同订单的普通推断触点；本阶段不做历史回填 |
| 外部红人表格同步 | 数据模型完成 | Google Sheet 增量读取与来源优先级仍需配置 |
| Airtable Interface | 页面结构完成 | 可按管理层使用反馈继续迭代 |

“Schema 已定义”不等于平台 API 已上线。公开文档把两者分开，避免误导使用者。
