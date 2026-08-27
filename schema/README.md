# Schema

`airtable-schema.json` 是从 Airtable 元数据生成的可复用结构，只保留表名、字段名、字段类型和说明。

它不包含：

- Base、Table、Field、Record 内部 ID
- 单选项内部 ID
- 生产公式中的内部引用
- 客户或订单记录

导入或重建时应先创建主表与主字段，再创建关联字段、Lookup、Rollup 和 Formula。生产字段与此模板不同的部署，应通过环境变量映射字段名。
