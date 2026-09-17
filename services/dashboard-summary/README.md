# 看板汇总服务

只读现有 Google Sheets 的订单、红人、归因触点、客户生命周期和 GA4 日数据，写入**另一张专用汇总表**。不读写广告账户，不修改原始数据，不触发邮件。汇总输出不含客户姓名、邮箱、地址或订单ID。

配置 `SOURCE_SPREADSHEET_ID`、`SUMMARY_SPREADSHEET_ID`。使用已授权的公司 Cloud Run 运行身份，目标表需单独授予该机器账号编辑权限；源表只需读取权限。服务必须保持 IAM 私有，建议单实例、并发1，由 Scheduler OIDC 调用 `POST /`。不要同时手动和定时执行，也不要在运行时部署新版本。

指标规则见 `metrics.py`，测试：`python -m unittest discover -s services/dashboard-summary`。

- 已付款订单含 PAID、PARTIALLY_REFUNDED、REFUNDED，排除取消单和仅授权订单。重复订单ID整体排除并提示，不随意选择一条。
- 退款后订单金额 = 订单总额 - 退款。订单总额已扣折扣，不能再减一次折扣；包含税和运费，不能命名为商品净销售额。历史空白退款暂按0，需在看板披露。源数据没有完整测试订单标识，不能宣称排除了所有测试单。
- 归因金额每单一次。多最终触点归入待核对，不分摊给红人；无归因方式的历史记录不标为 Collabs 确认。
- 问卷统计为生命周期记录，非原始表单提交数；缺少邀请分母，不提供回收率。待人工匹配和待审核独立展示。
- GA4只纳入T-4及之前全站日记录。互动率用互动会话/会话，平均互动秒数用互动总时长/会话；每日活跃用户不能跨日求和冒充去重人数。
- 订单按北京时间归日，GA4保留属性日期。跨平台差异不能单凭数值判断丢单或归咎平台。

所有输出使用原生数值和文字，不接受输入字符串作为公式。一次 Sheets batchUpdate 原子替换受服务管理的输出范围，回读校验成功才报告完成。不要在这些输出范围手工填数据；人工维护保留在原始表。

## 部署记录（2026-09-17）

- 私有 Cloud Run 汇总服务已部署。首次手动刷新返回 HTTP 200，五张输出表已完成写入回读校验。
- `dashboard-summary-daily` 已创建并核验为 `ENABLED`，每天北京时间 **09:20** 调用 `POST /`。首次计划运行时间为 2026-09-18 09:20；截至本次记录尚未验证首次定时执行结果。
- 现有 GA4 任务仍为北京时间 **09:00** 拉取 T-4 当天，未修改。两个任务独立，20 分钟间隔不是依赖或成功保证；GA4 失败或延迟时，汇总只能读取当时已有数据。
- 仅向现有运行机器账号授予此汇总服务的 `roles/run.invoker`。Scheduler 使用 OIDC，audience 为服务根 URL（不带末尾斜杠）；未添加匿名访问权限。
- 单次调度超时 300 秒，失败最多重试 3 次，退避 60–300 秒。运行服务超时 240 秒、并发 1、最大实例数 1。
- 原始明细表、订单/VOC/广告同步和邮件流程不受此任务修改。Looker Studio 报表目前仅完成初始数据源连接及首个指标，不能视为完整看板已交付。

生产项目、服务地址、表格 ID 和账号信息不放入公开仓库。后续状态以云端配置和执行日志为准。

## 可复用定时配置

先由管理员确认权限范围，再为已有机器账号添加**仅此服务**的调用权限。以下环境变量均须由部署者填写，不包含任何生产值：

```sh
gcloud run services add-iam-policy-binding dashboard-summary \
  --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" --role=roles/run.invoker

gcloud scheduler jobs create http dashboard-summary-daily \
  --project="$PROJECT_ID" --location="$REGION" \
  --schedule='20 9 * * *' --time-zone=Asia/Shanghai \
  --uri="${SUMMARY_SERVICE_URL%/}/" --http-method=POST \
  --oidc-service-account-email="$RUNTIME_SERVICE_ACCOUNT" \
  --oidc-token-audience="${SUMMARY_SERVICE_URL%/}" \
  --attempt-deadline=300s --max-retry-attempts=3 \
  --min-backoff=60s --max-backoff=300s
```

执行前先列出现有任务；同名任务存在时先检查，再按需要使用 `jobs update http`，不要重复创建。创建任务会启用自动执行。

## 运行检查与暂停

1. 在 Cloud Scheduler 检查任务状态、时区和下一次执行时间。`ENABLED` 只代表已启用，不代表执行成功。
2. 首次运行后检查 Scheduler 执行日志及 Cloud Run HTTP 状态；预期返回 200，不能只看任务存在。
3. 核对汇总表「数据说明」最近成功汇总时间和源记录数。刷新时间新不等于源数据完整，还要核对 GA4 最新日期、订单覆盖范围及排除记录提示。
4. GA4 数据缺日时先处理上游同步，不要在汇总表手工补数。Looker Studio 的数据缓存可能使页面展示晚于汇总表更新，需另行刷新/检查数据新鲜度。
5. 异常时只暂停 `dashboard-summary-daily`，不要暂停或修改原 GA4、订单和问卷任务：

```sh
gcloud scheduler jobs pause dashboard-summary-daily --project="$PROJECT_ID" --location="$REGION"
```

排障完成后用同名任务的 `resume` 恢复。人工重跑前确保没有正在执行的汇总；服务并发限制不是跨版本的分布式锁。
