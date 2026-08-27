# 安全与隐私

## 不进入 Git 的内容

- API Token、Webhook Secret、API Key
- Google Cloud 项目、服务账号和生产服务 URL
- GA4 Property、Shopify 店铺、Airtable Base/Table/Field 内部 ID
- 客户邮箱、电话、地址、订单记录、问卷回答

## 最小权限

- Cloud Run 使用私有入口。
- 调用方仅获得目标服务的 Invoker 权限。
- Airtable PAT 只覆盖目标 Base 和必要 Scope。
- GA4 服务账号只读目标 Property。
- BigQuery 写入账号只访问目标 Dataset。

## 日志

- 不记录完整请求头、Token、客户地址或问卷全文。
- 业务日志使用订单 ID、响应 ID 等非直接身份键。
- 错误详情回写 Google Sheet 时截断长度，避免泄漏上游响应。

## GA4 与 UTM

- 禁止传递邮箱、电话、姓名和订单详细地址。
- Consent Mode 与 Cookie 同意应按所在市场法规配置。
- 用户删除请求需要覆盖 Shopify、Airtable、Klaviyo、BigQuery 和表单数据。
