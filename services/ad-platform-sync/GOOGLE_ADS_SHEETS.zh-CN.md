# Google Ads → Google Sheets

此实现替代旧 Airtable 写入方案。运行文件为 `google_ads_sync.py`，部署为 Cloud Run Job。

## 数据口径

- 广告系列主档：平台 + 账户 + 广告系列 ID。
- 广告主档：平台 + 账户 + 广告组 + 广告 ID。PMax 不保证存在广告主档，不能据此判断未投放。
- 每日表现：日期 + 平台 + 账户 + `campaign` + 广告系列 ID；包含 PMax。
- 同一天、同一账户禁止混入旧广告级每日数据，以免花费重复汇总。旧历史记录不删除、不自动回填。
- 日期默认北京时间 T-4；指标中的日期按各广告账户自身时区解释。
- 购买数和收入只读取 PURCHASE 类别下的 conversions / conversions_value，可能为分数，遵循 Google Ads 归因口径，不等于 Shopify 实际订单、收款或 GA4。
- 只取 T-4 单日，不自动追溯后续转化修订；历史修订需明确日期重跑。
- CTR 为比例，CPC/CPM/ROAS 在分母为零时留空。不同币种不能直接汇总。
- 不覆盖人工红人关联、UTM、内容资产、备注及 Shopify 归因字段。

## 安全与运行

仅 SELECT 查询。运行身份通过短期令牌委托只读 Ads 机器账号；不生成长期密钥。通过现有私有 Sheets record gateway 写入原表，不公开工作表。

环境变量：`READ_ONLY=true`、`GOOGLE_ADS_SERVICE_ACCOUNT`、`GOOGLE_ADS_ACCOUNTS_JSON`、`SHEETS_STORE_URL`。
账户 JSON 是包含 `customer_id` 和 `account_type` 的数组；账户类型使用“自投”/“代投”。生产配置不入仓库。

默认只读取验证。显式设置 `WRITE_ENABLED=true` 才写入；可选 `SYNC_DATE=YYYY-MM-DD` 不得新于 T-4。
写入为稳定键 upsert，并重新读取每日表现核验核心指标。两账户都读取成功后才开始写入；写入过程不是跨表事务，失败可幂等重跑。

## 验证

`python3 -m unittest discover -s services/ad-platform-sync -p 'test*.py'`

`python3 scripts/check_ad_sync_read_only.py`

部署与定时任务是否启用必须以 Cloud Run / Scheduler 实际状态为准，代码存在不代表已上线。

### 2026-09-23 部署核验

- `google-ads-sheets-sync` 已部署；真实读取、写入、每日核心指标回读成功。
- 首次同步日期 2026-09-19：合计 20 个广告系列、26 条广告主档、20 条广告系列日记录。旧历史保留。
- `google-ads-sheets-daily` 已创建，计划北京时间 09:10。调度调用返回权限拒绝，已暂停，不能称为自动同步已启用。
- 待批准：为现有运行机器账号仅在这个 Job 上授予 `roles/run.invoker`，随后恢复调度并验证执行和幂等性；不扩大 Google Ads 权限。
- 现有汇总看板尚未纳入广告表，本次仅完成原始数据同步。

## 维护操作

1. 查看 Cloud Run Job 的最后执行结果；`READ_VALIDATED` 仅表示读取通过，`SYNCED` 才表示写入及每日指标回读通过。
2. 在原表的“广告系列”“广告”“广告每日表现”查看最后同步时间。每日表现筛选日期、账户，避免混看旧历史。
3. 单日失败可重跑同一个日期。不要人工复制行或删除唯一键；网关按唯一键更新已有行。
4. 需要补历史时，先检查是否含旧广告级记录。程序会拒绝混合粒度，需单独制定迁移方案。
5. 遇到 400 查询错误，先在只读模式诊断；遇到 403 检查 Ads 只读账号、机器身份委托和私有网关调用权限，不扩大广告编辑权限。
6. 每日任务只拉 T-4，不会自动补停机漏掉的日期。Cloud Scheduler 接收运行请求成功也不代表 Cloud Run 执行成功，排障须看后者。
