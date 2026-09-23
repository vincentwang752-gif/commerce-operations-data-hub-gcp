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
