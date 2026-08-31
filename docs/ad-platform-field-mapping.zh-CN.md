# Google Ads / Meta Ads 字段映射

## 数据层级

| 中台对象 | Google Ads | Meta Ads | Airtable |
|---|---|---|---|
| 广告账户 | Customer | Ad Account | 账户登记配置，不单独建事实行 |
| 广告系列 | Campaign | Campaign | 广告系列 |
| 广告组 | Ad Group | Ad Set | 广告表中的广告组 ID/名称 |
| 广告 | Ad / Ad Group Ad | Ad | 广告 |
| 创意 | Ad/Asset/Creative 相关对象 | Ad Creative/Post | 内容资产 + 广告创意字段 |
| 日级表现 | Metrics by segments.date | Insights by date_start | 广告每日表现 |

## 广告系列主档

| 中台字段 | Google Ads 来源 | Meta Ads 来源 | 说明 |
|---|---|---|---|
| 广告系列唯一键 | `google_ads|customer_id|campaign.id` | `meta_ads|account_id|campaign_id` | 不使用名称去重 |
| 平台 | 固定 `Google Ads` | 固定 `Meta Ads` | 单选值需统一 |
| 账户 ID | Customer ID | Ad Account ID | 公开仓库不保存真实值 |
| 广告系列 ID | campaign.id | campaign_id | 平台原始 ID |
| 广告系列名称 | campaign.name | campaign_name/name | 保留平台当前名称 |
| 投放目标 | advertising_channel_type/goal | objective | 平台值原样保留或映射 |
| 状态 | campaign.status | status/effective_status | 同时保留原始状态更利于排错 |
| 每日预算 | campaign_budget.amount_micros | daily_budget | 注意单位换算 |
| 币种 | customer.currency_code | account.currency | 不跨币种直接相加 |
| 账户类型 | 配置表 | 配置表 | 品牌自投/代理商代投/其他供应商 |

## 广告主档

| 中台字段 | Google Ads 来源 | Meta Ads 来源 | 说明 |
|---|---|---|---|
| 广告唯一键 | `google_ads|customer_id|ad.id` | `meta_ads|account_id|ad_id` | 稳定幂等键 |
| 广告系列 ID | campaign.id | campaign_id | 用于链接广告系列 |
| 广告组 ID | ad_group.id | adset_id | Google Ad Group / Meta Ad Set |
| 广告 ID | ad.id | ad_id | 平台原始 ID |
| 广告名称 | ad.name 或内部组合名 | ad_name/name | Google 部分类型没有业务名称时按规则生成 |
| 创意 ID | asset/ad 相关 ID | creative_id | 不用素材文件名替代 ID |
| 状态 | ad_group_ad.status | effective_status | Meta 同时保留配置状态和有效状态 |
| 落地页链接 | final_urls | object_url/link_url | 需要剥离敏感参数后展示 |
| UTM | tracking_url_template/final_url_suffix | url_tags/落地页参数 | 保留原值并解析结构化字段 |

## 日级表现

| 中台字段 | Google Ads | Meta Ads | 口径提醒 |
|---|---|---|---|
| 表现唯一键 | 日期+平台+账户+广告 | 日期+平台+账户+广告 | 同日重复运行覆盖更新 |
| 曝光量 | impressions | impressions | 可直接作为平台曝光 |
| 触达人数 | 通常无同等通用指标 | reach | Google 留空，不填 0 |
| 点击数 | clicks | clicks/link_clicks | 需固定 Meta 点击口径 |
| 落地页浏览量 | 视 Campaign 类型和转化设置 | landing_page_views | 缺失留空 |
| 广告花费 | cost_micros | spend | 统一换算到账户币种数值 |
| 平台加购数 | conversion action 映射 | actions:add_to_cart | 依赖平台事件配置 |
| 平台发起结账数 | conversion action 映射 | actions:initiate_checkout | 不等同 Shopify 人数 |
| 平台购买数 | conversions/purchase action | purchases/actions:purchase | 平台归因口径 |
| 平台归因收入 | conversion_value | purchase_roas/action_values | 平台归因口径 |
| Shopify 订单/收入 | 中台归因规则 | 中台归因规则 | 不从广告 API 获取 |

## Meta 合创广告补充字段

每条疑似 Partnership/合创广告至少保留：

- 是否合创广告
- Instagram 用户 ID
- Facebook 主页 ID
- Meta 帖子 ID
- 平台红人显示名原值
- 合作来源/供应商
- 内容资产
- 合创红人
- 红人合作
- 合创资料状态

匹配优先级：稳定平台 ID → 已确认内容资产/Post ID → 已确认合作记录 → 人工确认。显示名只能辅助排查，不能单独作为自动合并依据。未知红人先进入“待确认”状态，不自动归并到名称相似的已有红人。

## 平台差异

- 广告平台的购买和收入用于平台优化参考，不替代 Shopify 订单与净收入。
- Google Ads、Meta Ads、GA4 和 Shopify 的归因窗口、时区、建模方式及去重方式不同。
- 账户币种或时区不同必须分账户保存，汇总前先换算和对齐日期。
- 平台未提供的字段应留空并记录原因，不能用 0 冒充真实值。

