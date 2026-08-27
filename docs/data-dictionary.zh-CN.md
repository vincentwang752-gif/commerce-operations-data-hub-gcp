# Airtable 数据字典

这份字典只包含表名、字段名、字段类型和说明，不含生产 Base ID、Table ID、Field ID、记录或客户数据。它对应本项目建议的 11 张底层表。

订单与净收入以 Shopify 为准；GA4 用于网站行为与平台归因。两者发生差异属于正常的平台口径差异，需要通过每日对账字段监控，不应直接视为订单错误。

## 客户

客户主档。一行代表一位客户，汇总联系方式、地区、客户类型及关联订单。数据主要来自 Shopify；按订单同步更新。

| 字段 | 类型 | 说明 |
|---|---|---|
| 客户名称 | `singleLineText` | 客户显示名称，通常来自 Shopify 订单中的客户姓名。 |
| 邮箱 | `email` | 客户邮箱，用于跨系统匹配客户、订单和问卷；属于个人信息，请限制访问。 |
| 手机号 | `phoneNumber` | 客户联系电话，来自 Shopify；属于个人信息，请限制访问。 |
| 国家/地区 | `singleLineText` | 客户订单或收货地址对应的国家/地区。 |
| 客户类型 | `singleSelect` | 客户类型：个人或企业，用于客户分层。 |
| 关联订单 | `multipleRecordLinks` | 该客户对应的 Shopify 订单，由关联字段自动维护。 |
| 关联生命周期 | `multipleRecordLinks` | 该客户对应的生命周期记录，由关联字段自动维护。 |
| Shopify 客户 ID | `singleLineText` | Shopify 分配的客户唯一 ID，用于跨系统匹配和去重；访客订单可能为空。 |
| 最近下单时间 | `dateTime` | 该客户最近一次下单时间。 |
| 首次下单时间 | `dateTime` | 该客户在 Shopify 的首次下单时间。 |
| 累计订单数 | `number` | Shopify 客户累计订单数量。 |
| 累计收入 | `currency` | Shopify 客户累计消费金额；币种口径以店铺主币种为准。 |
| 最后同步时间 | `dateTime` | 该客户资料最近一次由 Make 从 Shopify 更新的时间。 |
| 客户唯一键 | `singleLineText` | Shopify 客户的稳定唯一标识。优先使用 Shopify 客户 ID；访客订单使用规范化邮箱，供自动同步去重和更新。 |

## 订单

订单事实表。一行代表一笔订单，记录商品、收入、折扣、退款、取消、退货及归因关系。数据来自 Shopify。

| 字段 | 类型 | 说明 |
|---|---|---|
| 订单 ID | `singleLineText` | Shopify 订单的唯一标识，用于跨系统匹配和去重；不要人工修改。 |
| 下单时间 | `dateTime` | 客户完成下单的日期和时间，来自 Shopify。 |
| SKU | `singleLineText` | 订单商品的库存单位编码；用于区分产品和套装。 |
| 订单收入 | `currency` | 该订单记录的销售收入；分析时需结合退款金额判断净收入。 |
| 折扣金额 | `currency` | 该订单使用优惠码或自动折扣减少的金额。 |
| 退款金额 | `currency` | 该订单已发生的退款金额；来自 Shopify。 |
| 是否取消 | `checkbox` | 勾选表示订单已取消。 |
| 是否退货 | `checkbox` | 勾选表示订单发生退货；与退款并非完全等同。 |
| 国家/地区 | `singleLineText` | 订单对应的客户或收货国家/地区。 |
| 客户 | `multipleRecordLinks` | 该订单所属客户，由关联字段连接到客户主档。 |
| 归因触点 | `multipleRecordLinks` | 可解释该订单来源的营销触点，可能包含广告、红人、内容、邮件等。 |
| 红人合作 | `multipleRecordLinks` | 与该订单有关的红人合作项目；仅在存在可识别证据时关联。 |
| Shopify 客户 ID | `singleLineText` | 订单关联的 Shopify Customer ID；访客订单可能为空，用于客户匹配审计。 |
| 客户邮箱 | `email` | 下单邮箱，用于访客订单和客户匹配；属于个人信息，请限制访问。 |
| 币种 | `singleLineText` | 订单金额使用的币种代码，例如 USD。 |
| 付款状态 | `singleLineText` | Shopify financial_status 原始值，例如 paid、refunded、partially_refunded。 |
| 履约状态 | `singleLineText` | Shopify fulfillment_status 原始值；为空通常表示未履约。 |
| 净收入 | `currency` | 订单当前净金额，考虑订单调整和退款；用于实际收入分析。 |
| 优惠码 | `singleLineText` | 订单使用的优惠码；多个优惠码以逗号分隔。 |
| 商品明细 | `multilineText` | 订单商品明细，格式为商品名称 / SKU × 数量；一行仍代表一笔订单。 |
| SKU 列表 | `multilineText` | 该订单包含的全部 SKU，以逗号分隔，支持多商品订单。 |
| 订单来源 | `singleLineText` | Shopify source_name 或订单创建渠道，例如 web、draft_order、POS。 |
| 主产品 | `singleLineText` | 按订单商品识别的主要产品，用于 S1、S2 等产品级汇总。 |
| Landing Site | `multilineText` | 客户进入商店时记录的原始 landing_site，可能包含 UTM 和 Click ID。 |
| Referring Site | `multilineText` | Shopify 记录的外部引荐页面或来源。 |
| UTM 来源 | `singleLineText` | 从 Landing Site 解析的 utm_source。 |
| UTM 媒介 | `singleLineText` | 从 Landing Site 解析的 utm_medium。 |
| UTM 广告系列 | `singleLineText` | 从 Landing Site 解析的 utm_campaign。 |
| UTM 内容 | `singleLineText` | 从 Landing Site 解析的 utm_content。 |
| UTM 关键词 | `singleLineText` | 从 Landing Site 解析的 utm_term。 |
| 点击 ID | `singleLineText` | 从 Landing Site 解析的平台点击标识，优先保留 gclid、fbclid、ttclid 等。 |
| 最后同步时间 | `dateTime` | 该订单最近一次由 Make 从 Shopify 更新的时间。 |
| GA4 交易 ID | `singleLineText` | 与该 Shopify 订单匹配的 GA4 transaction_id。GA4 属于行为平台数据；匹配失败不代表 Shopify 订单无效。 |
| GA4 客户端 ID | `singleLineText` | 下单时捕获的 GA4 client_id，用于回溯同一浏览器购买前触点。属于假名化标识，应限制访问，不得写入邮箱或手机号。 |
| GA4 会话 ID | `singleLineText` | 下单会话对应的 GA4 ga_session_id，用于连接订单与最终会话触点。 |
| GA4 匹配状态 | `singleSelect` | 订单与 GA4 purchase 的匹配结果。GA4 未记录或异常属于平台追踪问题；订单真实性与收入仍以 Shopify 为准。 |

## 红人

红人主档。一行代表一位合作或潜在红人，汇总平台账号、受众、联系来源、负责人和合作状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| 红人名称 | `singleLineText` | 红人或创作者的显示名称，用于内部识别。 |
| 邮箱 | `email` | 红人的联系邮箱；属于个人信息，请限制访问。 |
| 关联内容 | `multipleRecordLinks` | 该红人发布或制作的内容资产，由关联字段自动维护。 |
| 归因触点 | `multipleRecordLinks` | 与该红人有关的订单归因触点。 |
| 红人唯一键 | `singleLineText` | 系统用于去重红人的稳定唯一键；不要人工修改。 |
| 平台 | `multipleSelects` | 红人活跃的平台，可多选，例如 YouTube、Instagram、TikTok。 |
| 账号名称 | `singleLineText` | 红人在主要平台上的账号名或 Handle。 |
| 主页链接 | `url` | 红人主要社交平台主页的链接。 |
| 国家/地区 | `singleLineText` | 红人主要所在国家或受众市场。 |
| 语言 | `multipleSelects` | 红人内容使用的主要语言，可多选。 |
| 红人类型 | `multipleSelects` | 红人的内容领域或业务类型，例如音乐、教育、生活方式。 |
| 粉丝量 | `number` | 红人主要账号的受众规模；需定期更新。 |
| 联系来源 | `singleSelect` | 该红人进入合作池的来源，例如主动开发、入站、转介绍。 |
| 负责人 | `singleLineText` | 公司内部负责跟进该红人的人员。 |
| 红人状态 | `singleSelect` | 红人从线索、联系、谈判到合作或暂停的当前状态。 |
| Shopify Collabs ID | `singleLineText` | Shopify Collabs 中的红人标识，用于跨系统匹配。 |
| 默认推广链接 | `url` | 该红人长期使用的默认 Affiliate Link。 |
| 默认优惠码 | `singleLineText` | 该红人长期使用的默认优惠码，用于转化识别。 |
| 备注 | `multilineText` | 记录无法结构化表达的补充信息。 |
| 最后更新时间 | `date` | 该红人资料最近一次人工或自动更新的日期。 |
| 红人合作 | `multipleRecordLinks` | 该红人对应的合作项目，由关联字段自动维护。 |
| Instagram 用户 ID | `singleLineText` | Meta/Instagram 返回的稳定用户标识，用于自动匹配合创广告红人；优先级高于账号名称。 |
| Facebook 主页 ID | `singleLineText` | Facebook Page 的稳定标识，用于自动匹配合创广告红人。 |
| 引入方/供应商 | `singleLineText` | 该红人由谁引入或洽谈，例如品牌直谈、钛动、Shopify Collabs 或其他供应商；无法识别时填“待确认”。 |
| 资料确认状态 | `singleSelect` | 标记红人资料是否仅由广告平台自动发现，或已经人工核验。 |
| 首次发现时间 | `dateTime` | 系统第一次从广告、Collabs、表格或其他来源发现该红人的时间。 |
| 最后发现时间 | `dateTime` | 该红人最近一次被自动化流程识别或更新的时间。 |
| 广告 | `multipleRecordLinks` | 通过合创广告、白名单投放或创作者身份关联到该红人的广告；由广告表的“合创红人”反向链接自动维护。 |

## 内容资产

营销内容主档。一行代表一条可识别内容，记录发布信息、内容角度、表现、成本和归因收入。

| 字段 | 类型 | 说明 |
|---|---|---|
| 内容名称 | `singleLineText` | 用于内部识别该内容的名称，建议包含红人、平台和主题。 |
| 内容类型 | `singleSelect` | 内容形式，例如视频、图片、博客或其他。 |
| 发布时间 | `dateTime` | 内容首次公开发布的日期和时间。 |
| 红人 | `multipleRecordLinks` | 制作或发布该内容的红人，关联到红人主档。 |
| 平台 | `singleSelect` | 内容实际发布的平台。 |
| 内容版本 | `singleLineText` | 同一创意的版本标识，用于区分不同剪辑、文案或素材。 |
| 产品 | `singleSelect` | 该内容主要推广的产品，例如 S1 或 S2。 |
| 内容链接 | `url` | 已发布内容的公开链接。 |
| 平台内容 ID | `singleLineText` | 平台分配的 Post/Video ID，用于自动抓取和去重。 |
| 开场钩子 | `singleLineText` | 内容前几秒或首段使用的核心 Hook，用于比较创意表现。 |
| 使用场景 | `multipleSelects` | 内容展示的产品使用场景，可多选。 |
| 内容角度 | `multipleSelects` | 内容采用的主要沟通角度，例如便携、音质、工作流。 |
| CTA | `singleLineText` | 内容中的主要行动号召，例如访问官网、使用优惠码或立即购买。 |
| 优惠码 | `singleLineText` | 该内容使用的优惠码，用于订单归因。 |
| 推广链接 | `url` | 该内容使用的 Affiliate Link 或带 UTM 的推广链接。 |
| 自然/付费 | `singleSelect` | 区分自然发布内容与付费投放内容。 |
| 使用权限 | `singleSelect` | 品牌获得的内容使用范围和期限。 |
| 播放量 | `number` | 平台显示的观看或播放次数；需注明数据更新时间。 |
| 点赞数 | `number` | 平台显示的点赞次数。 |
| 评论数 | `number` | 平台显示的评论次数。 |
| 收藏数 | `number` | 平台显示的收藏或保存次数。 |
| 分享数 | `number` | 平台显示的分享次数。 |
| 链接点击数 | `number` | 该内容推广链接产生的可识别点击次数。 |
| 订单数 | `number` | 归因到该内容的订单数量；取决于优惠码、链接、UTM 或人工确认。 |
| 归因收入 | `currency` | 归因到该内容的订单收入；不是内容发布平台显示收入。 |
| 内容成本 | `currency` | 该内容对应的制作费、红人固定费或授权成本。 |
| 表现更新时间 | `date` | 播放、互动、点击等表现数据最近更新的日期。 |
| 红人合作 | `multipleRecordLinks` | 产生该内容的合作项目，关联到红人合作表。 |
| 内容 ROAS | `formula` | 归因收入 ÷ 内容成本；由公式自动计算，不要人工修改。 |
| 归因触点 | `multipleRecordLinks` | 与该内容有关的订单归因触点。 |
| 关联广告 | `multipleRecordLinks` | 复用该内容资产进行投放的广告。 |

## 归因触点

归因触点事实表。一行代表订单链路中的一个可识别营销触点，用于连接订单、红人、内容和广告。

| 字段 | 类型 | 说明 |
|---|---|---|
| 触点 ID | `autoNumber` | Airtable 自动生成的触点编号，用于内部识别；不要人工修改。 |
| 订单 | `multipleRecordLinks` | 该触点最终关联的订单。 |
| 红人 | `multipleRecordLinks` | 该触点对应的红人；仅在有可识别证据时关联。 |
| 视频 ID | `singleLineText` | 来源视频或内容在平台上的标识。 |
| 内容版本 | `singleLineText` | 触点对应的内容版本，用于区分同一创意的不同版本。 |
| 平台 | `singleSelect` | 触点发生的平台，例如 YouTube、Instagram、TikTok。 |
| UTM 参数 | `singleLineText` | 触点中捕获的完整或组合 UTM 信息。 |
| 推广链接 | `url` | 产生该触点的 Affiliate Link 或推广链接。 |
| 优惠码 | `singleLineText` | 订单使用的优惠码，用于识别红人或活动来源。 |
| 是否首次触点 | `checkbox` | 勾选表示这是当前可识别的客户最早触点。 |
| 是否最终触点 | `checkbox` | 勾选表示这是下单前最后一个可识别触点。 |
| 落地页版本 | `singleLineText` | 客户访问的落地页版本，用于比较页面转化。 |
| 触点日期 | `date` | 该营销触点发生或被识别的日期。 |
| 来源类型 | `singleSelect` | 触点的大类来源，例如红人、付费广告、自然、邮件、搜索。 |
| 归因方式 | `singleSelect` | 用于确认来源的证据类型，例如 UTM、优惠码、问卷或人工确认。 |
| 归因置信度 | `singleSelect` | High=Click ID/优惠码等强证据；Medium=UTM 等中等证据；Low=问卷或人工推断。 |
| 归因收入 | `currency` | 分配给该触点的订单收入；同一订单多触点时避免重复全额计算。 |
| UTM 来源 | `singleLineText` | utm_source 的值，用于识别流量平台或来源。 |
| UTM 媒介 | `singleLineText` | utm_medium 的值，用于识别 paid、affiliate、email 等媒介。 |
| UTM 广告系列 | `singleLineText` | utm_campaign 的值，用于识别具体营销活动。 |
| UTM 内容 | `singleLineText` | utm_content 的值，用于区分广告或创意版本。 |
| 归因角色 | `singleSelect` | 该触点在链路中的角色，例如首次、最终或辅助触点。 |
| 内容资产 | `multipleRecordLinks` | 该触点对应的内容资产。 |
| 红人合作 | `multipleRecordLinks` | 该触点对应的红人合作项目。 |
| 广告 | `multipleRecordLinks` | 匹配到的付费广告记录。 |
| 广告 ID | `singleLineText` | 平台广告 ID，来自 UTM、结账归因或广告平台数据。 |
| 广告组 ID | `singleLineText` | 平台 Ad Set 或 Ad Group ID。 |
| UTM 关键词 | `singleLineText` | utm_term 的值，可用于关键词、受众或广告组区分。 |
| 点击 ID | `singleLineText` | 平台点击标识，例如 gclid、fbclid、ttclid；属于强归因证据。 |
| 落地页链接 | `url` | 客户首次或对应触点访问的完整落地页 URL。 |
| 触点唯一键 | `singleLineText` | 归因触点的稳定唯一标识，用于自动同步时去重；通常由订单 ID 与触点类型组合生成。 |
| 行为数据来源 | `singleSelect` | 该触点的行为证据来源。GA4 代表平台观察数据；Shopify 代表订单事实；两者不一致时不得覆盖 Shopify 交易数据。 |
| GA4 客户端 ID | `singleLineText` | GA4 client_id，用于同一浏览器内匿名会话串联。属于假名化标识，应限制访问；清除 Cookie、换浏览器或拒绝同意会导致变化或缺失。 |
| GA4 会话 ID | `singleLineText` | GA4 ga_session_id，用于区分会话。只有与 transaction_id、订单或已捕获的一方标识匹配时，才能连接到订单。 |
| GA4 事件名称 | `singleLineText` | 触点对应的 GA4 事件，例如 page_view、view_item、add_to_cart、begin_checkout、purchase。 |
| GA4 事件时间 | `dateTime` | GA4 事件时间。导入时应统一转换到业务报表时区，避免与 Shopify 下单时间跨日。 |
| GA4 页面路径 | `multilineText` | 该行为发生的页面路径或完整 URL，用于还原购买前页面顺序。 |
| GA4 页面标题 | `singleLineText` | 该行为对应的页面标题，用于业务阅读；路径是更稳定的匹配键。 |
| GA4 会话来源/媒介 | `singleLineText` | GA4 session source / medium。它是平台会话口径，可能与 Shopify Landing Site、Referring Site 或订单来源不同。 |
| GA4 首次来源/媒介 | `singleLineText` | GA4 first user source / medium。表示首次获客来源，不应当作最终成交来源。 |
| GA4 交易 ID | `singleLineText` | purchase 事件中的 transaction_id，用于与 Shopify 订单匹配。应保证每笔订单唯一且只发送一次。 |

## 客户生命周期

客户生命周期状态表。一行代表一位客户当前的调研、激活、持续使用、退款和推荐状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| 生命周期 ID | `autoNumber` | Airtable 自动生成的生命周期编号；不要人工修改。 |
| 客户 | `multipleRecordLinks` | 该生命周期记录所属客户。 |
| 售前问卷已完成 | `checkbox` | 勾选表示客户已经完成购买前/购买后第一阶段调查。 |
| 使用后问卷已完成 | `checkbox` | 勾选表示客户已经完成实际使用后的第二阶段调查。 |
| 激活日期 | `dateTime` | 客户首次完成关键使用或被确认激活的日期。 |
| 持续使用 | `checkbox` | 勾选表示客户在后续调研中仍持续使用产品。 |
| 已退款 | `checkbox` | 勾选表示客户或关联订单已发生退款。 |
| 推荐意向 | `singleSelect` | 客户是否愿意推荐产品；来自使用后调研。 |
| 第一阶段完成时间 | `dateTime` | Google Cloud确认第一阶段问卷有效完成的时间；用于Klaviyo流程触发与延保审核。 |
| 第二阶段完成时间 | `dateTime` | Google Cloud确认第二阶段问卷有效完成的时间；只有匹配S1资格后才写入。 |
| 对应S1订单ID | `singleLineText` | 与问卷邮箱匹配的S1 Shopify订单ID；人工售后核验延保时使用。 |
| 延保天数 | `number` | 当前已满足的延保天数：完成第一阶段为180，完成两阶段合计360；最终执行由售后人工确认。 |
| 延保审核状态 | `singleSelect` | 人工售后处理状态。Google Cloud写入“待审核”；售后确认后改为“已确认”，无法匹配时标记“需人工匹配”或“驳回”。 |
| 问卷回写来源 | `singleSelect` | 本条问卷完成与延保结果的写入来源，用于区分Google Cloud自动回写和人工补录。 |
| 问卷最后同步时间 | `dateTime` | Google Cloud最近一次成功更新该客户问卷/延保状态的时间。 |

## 红人合作

红人合作项目表。一行代表一次合作，记录寄样、费用、内容交付、发布时间、使用权限及结算状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| 合作 ID | `singleLineText` | 合作项目唯一标识，用于去重和跨系统匹配；不要随意修改。 |
| 红人 | `multipleRecordLinks` | 本次合作对应的红人。 |
| 产品 | `singleSelect` | 本次合作主要推广或寄送的产品。 |
| 合作项目 | `singleLineText` | 本次合作所属活动、批次或项目名称。 |
| 合作类型 | `singleSelect` | 合作商业模式，例如赠品、固定费用、Affiliate 或组合方式。 |
| 合作状态 | `singleSelect` | 合作从开发、谈判、寄样、制作、发布到完成的当前阶段。 |
| 首次联系日期 | `date` | 第一次向该红人发起本次合作联系的日期。 |
| 确认合作日期 | `date` | 双方确认合作条件或达成协议的日期。 |
| 寄样日期 | `date` | 产品实际寄出的日期。 |
| 寄样订单 | `multipleRecordLinks` | 用于寄送样品的 Shopify 订单。 |
| 固定费用 | `currency` | 本次合作约定的固定现金费用。 |
| 产品成本 | `currency` | 寄样产品的内部成本，不等同零售价。 |
| 物流成本 | `currency` | 本次合作寄样产生的运输和相关费用。 |
| 佣金比例 | `percent` | Affiliate 销售佣金比例。 |
| 已付佣金 | `currency` | 已向红人支付的销售佣金金额。 |
| 优惠码 | `singleLineText` | 本次合作专属优惠码，用于识别订单。 |
| 推广链接 | `url` | 本次合作专属 Affiliate Link 或带 UTM 的链接。 |
| 交付内容 | `multilineText` | 约定的内容数量、形式、平台和其他交付要求。 |
| 内容截止日期 | `date` | 红人应完成或提交内容的截止日期。 |
| 计划发布时间 | `date` | 双方计划公开发布内容的日期。 |
| 实际发布时间 | `date` | 内容实际公开发布的日期。 |
| 使用权限 | `singleSelect` | 品牌获得的内容使用范围和期限。 |
| 允许白名单投放 | `checkbox` | 勾选表示品牌可通过红人账号进行授权广告投放。 |
| 付款状态 | `singleSelect` | 固定费或相关合作款项的当前支付状态。 |
| 总成本 | `formula` | 固定费用、产品成本、物流成本和已付佣金的公式汇总；不要人工修改。 |
| 内容资产 | `multipleRecordLinks` | 本次合作实际产生的内容。 |
| 归因触点 | `multipleRecordLinks` | 与本次合作有关的订单归因触点。 |
| 广告 | `multipleRecordLinks` | 广告表“红人合作”字段的反向链接，表示本次合作对应的广告；由关联关系自动维护。 |
| 关联广告 | `multipleRecordLinks` | 本次红人合作产生或授权投放的广告。 |
| 合作来源/供应商 | `singleLineText` | 本次合作由品牌直谈、钛动、Shopify Collabs 或其他供应商促成；无法判断时填“待确认”。 |
| 来源确认状态 | `singleSelect` | 合作来源的确认程度；自动化无法可靠推断洽谈方时保留“待确认”。 |
| 广告合作方式 | `singleSelect` | 该红人内容进入广告投放的方式。 |

## 广告系列

跨平台广告系列主档。一行代表一个平台账户下的一个 Campaign，用于保存预算、状态、UTM 和落地页信息。

| 字段 | 类型 | 说明 |
|---|---|---|
| 广告系列唯一键 | `singleLineText` | 系统唯一键：平台\|账户 ID\|广告系列 ID，用于 Make 自动更新和防止重复；不要人工修改。 |
| 平台 | `singleSelect` | 广告系列所属投放平台。 |
| 账户 ID | `singleLineText` | 广告平台账户 ID，用于区分自投、代投及不同市场账户。 |
| 广告系列 ID | `singleLineText` | 平台分配的 Campaign ID。 |
| 广告系列名称 | `singleLineText` | 广告平台中的 Campaign 名称。 |
| 投放目标 | `singleLineText` | 广告系列的投放目标，例如销售、流量、视频观看。 |
| 产品 | `singleSelect` | 广告系列主要推广的产品。 |
| 状态 | `singleSelect` | 广告系列当前状态，例如草稿、启用、暂停或结束。 |
| 开始日期 | `date` | 广告系列计划或实际开始投放的日期。 |
| 结束日期 | `date` | 广告系列计划或实际结束投放的日期。 |
| 每日预算 | `currency` | 平台设置的每日预算；按该广告账户币种记录。 |
| 币种 | `singleLineText` | 广告账户使用的币种，例如 USD。 |
| UTM 来源 | `singleLineText` | utm_source 的计划值，用于识别流量平台。 |
| UTM 媒介 | `singleLineText` | utm_medium 的计划值，用于识别付费媒介类型。 |
| UTM 广告系列 | `singleLineText` | utm_campaign 的计划值，用于跨系统匹配 Campaign。 |
| 落地页链接 | `url` | 广告系列主要使用的落地页 URL。 |
| 最后同步时间 | `dateTime` | 该广告系列数据最近一次从广告平台同步的时间。 |
| 备注 | `multilineText` | 记录无法结构化表达的投放背景、异常或调整说明。 |
| 广告 | `multipleRecordLinks` | 该广告系列包含的广告单元。 |
| 每日表现 | `multipleRecordLinks` | 该广告系列对应的日级表现记录。 |
| 账户类型 | `singleSelect` | 广告账户的运营归属，用于区分品牌自投与代理商代投。 |

## 广告

广告单元主档。一行代表一条平台广告，连接广告系列、内容资产、UTM、优惠码和归因触点。

| 字段 | 类型 | 说明 |
|---|---|---|
| 广告唯一键 | `singleLineText` | 系统唯一键：平台\|账户 ID\|广告 ID，用于 Make 自动更新和防止重复；不要人工修改。 |
| 平台 | `singleSelect` | 该广告所属投放平台。 |
| 账户 ID | `singleLineText` | 广告平台账户 ID，用于区分自投、代投及不同市场账户。 |
| 广告系列 | `multipleRecordLinks` | 该广告所属广告系列。 |
| 广告系列 ID | `singleLineText` | 平台分配的 Campaign ID，用于跨系统匹配。 |
| 广告组 ID | `singleLineText` | 平台分配的 Ad Set 或 Ad Group ID。 |
| 广告组名称 | `singleLineText` | 平台中的 Ad Set 或 Ad Group 名称。 |
| 广告 ID | `singleLineText` | 平台分配的广告唯一 ID。 |
| 广告名称 | `singleLineText` | 广告平台中的广告名称。 |
| 内容资产 | `multipleRecordLinks` | 该广告使用的可复用内容或创意资产。 |
| 创意 ID | `singleLineText` | 平台分配的 Creative ID。 |
| 创意版本 | `singleLineText` | 用于区分同一内容的不同文案、剪辑、封面或广告版本。 |
| 状态 | `singleSelect` | 广告当前状态，例如启用、暂停、结束或被拒。 |
| 落地页链接 | `url` | 用户点击该广告后进入的落地页 URL。 |
| UTM 来源 | `singleLineText` | utm_source 的实际值。 |
| UTM 媒介 | `singleLineText` | utm_medium 的实际值。 |
| UTM 广告系列 | `singleLineText` | utm_campaign 的实际值。 |
| UTM 内容 | `singleLineText` | utm_content 的实际值，用于区分广告或创意。 |
| UTM 关键词 | `singleLineText` | utm_term 的实际值，可用于关键词、受众或广告组区分。 |
| 优惠码 | `singleLineText` | 该广告使用或对应的优惠码，用于辅助订单归因。 |
| 最后同步时间 | `dateTime` | 该广告主档最近一次从广告平台同步的时间。 |
| 备注 | `multilineText` | 记录投放异常、素材调整或无法结构化表达的信息。 |
| 每日表现 | `multipleRecordLinks` | 该广告对应的日级表现记录。 |
| 归因触点 | `multipleRecordLinks` | 与该广告有关的订单归因触点。 |
| 是否合创广告 | `checkbox` | 勾选表示该广告使用了创作者身份、合作帖子、白名单或 Partnership Ad 能力。 |
| 合创红人 | `multipleRecordLinks` | 该广告对应的创作者；未知红人会由 Make 自动新增到红人表。 |
| 红人合作 | `multipleRecordLinks` | 该广告对应的红人合作项目，用于汇总费用、内容与广告表现。 |
| 合作来源/供应商 | `singleLineText` | 促成本次合创广告的团队或供应商；无法由规则判断时填“待确认”。 |
| 平台红人显示名 | `singleLineText` | Meta 广告接口返回的创作者名称或账号名原值，保留用于排查和人工确认。 |
| Instagram 用户 ID | `singleLineText` | 合创广告中 Instagram 创作者的稳定平台 ID。 |
| Facebook 主页 ID | `singleLineText` | 合创广告中 Facebook Page 的稳定平台 ID。 |
| Meta 帖子 ID | `singleLineText` | 广告所复用的 Meta/Instagram 帖子 ID，用于匹配内容资产和去重。 |
| 账户类型 | `singleSelect` | 广告账户的运营归属，用于区分品牌自投、钛动代投及其他供应商账户。 |
| 红人合作 2 | `multipleRecordLinks` | 红人合作表“关联广告”字段的反向链接。当前与“红人合作”字段功能相近，暂保留以避免影响后续合创 API 自动化；待测试完成后再决定是否合并。 |
| 合创资料状态 | `formula` | 自动判断合创广告的资料闭环程度，用于筛选待补红人身份、待建合作关系的广告。 |

## 广告每日表现

广告日级表现事实表。一行代表某一天、某个平台账户和某条广告的表现；每日自动同步，业务判断优先参考 Shopify 归因指标。

| 字段 | 类型 | 说明 |
|---|---|---|
| 表现唯一键 | `singleLineText` | 系统唯一键：日期\|平台\|账户 ID\|广告 ID，用于每日自动更新和防止重复；不要人工修改。 |
| 日期 | `date` | 该行广告表现对应的自然日。 |
| 平台 | `singleSelect` | 数据来源广告平台。 |
| 账户 ID | `singleLineText` | 广告平台账户 ID，用于区分自投、代投及不同市场账户。 |
| 广告系列 | `multipleRecordLinks` | 对应的广告系列主档。 |
| 广告 | `multipleRecordLinks` | 对应的广告主档。 |
| 广告系列 ID | `singleLineText` | 平台分配的 Campaign ID。 |
| 广告组 ID | `singleLineText` | 平台分配的 Ad Set 或 Ad Group ID。 |
| 广告 ID | `singleLineText` | 平台分配的广告唯一 ID。 |
| 币种 | `singleLineText` | 金额指标使用的广告账户币种。 |
| 曝光量 | `number` | 广告被展示的总次数；同一用户可重复计算。 |
| 触达人数 | `number` | 看到广告的去重用户数；并非所有平台都提供。 |
| 点击数 | `number` | 广告平台记录的点击次数；具体点击口径以平台为准。 |
| 落地页浏览量 | `number` | 用户点击后成功加载落地页的次数；通常低于点击数。 |
| 广告花费 | `currency` | 广告平台返回的实际消耗，按账户币种记录。 |
| 平台加购数 | `number` | 广告平台归因的加购次数；受平台归因窗口和模型影响。 |
| 平台发起结账数 | `number` | 广告平台归因的发起结账次数；不等同 Shopify 实际结账人数。 |
| 平台购买数 | `number` | 广告平台归因的购买次数；可能与 Shopify 订单数不同。 |
| 平台归因收入 | `currency` | 广告平台自身归因的购买收入，用于平台优化参考，不等同 Shopify 实际收入。 |
| Shopify 订单数 | `number` | 依据 UTM、Click ID、优惠码等证据归因到该广告的 Shopify 订单数。 |
| Shopify 归因收入 | `currency` | 归因到该广告的 Shopify 订单收入，优先作为业务判断口径。 |
| 最后同步时间 | `dateTime` | 该日级记录最近一次由 Make 更新的时间。 |
| 备注 | `multilineText` | 记录异常、数据缺失、口径调整或人工补充说明。 |
| CTR | `formula` | 点击率：点击数 ÷ 曝光量；由公式自动计算。 |
| CPC | `formula` | 单次点击成本：广告花费 ÷ 点击数；由公式自动计算。 |
| CPM | `formula` | 千次曝光成本：广告花费 ÷ 曝光量 × 1000；由公式自动计算。 |
| 平台 ROAS | `formula` | 平台归因收入 ÷ 广告花费；用于平台优化参考。 |
| Shopify ROAS | `formula` | Shopify 归因收入 ÷ 广告花费；优先作为实际业务回报判断指标。 |
| 账户类型 | `singleSelect` | 日级表现所属账户的运营归属，便于汇总自投与代投表现。 |
| 归因数据状态 | `formula` | 自动判断该日广告记录是否已经具备 Shopify 对账数据。 |
| 归因收入差额 | `formula` | 平台归因收入减去 Shopify 归因收入，用于识别平台报告与实际订单口径差异。 |
| 归因订单差额 | `formula` | 平台购买数减去 Shopify 订单数。正数表示平台归因高于 Shopify 可识别订单，负数表示 Shopify 归因更高。 |

## GA4运营与用户行为

GA4 日级运营与用户行为汇总表。一行代表某日期、某分析粒度和某维度值的汇总数据，用于补充 Shopify 无法完整提供的访问、互动、页面路径和漏斗行为。GA4 属于行为分析与归因平台数据，不是交易账本；订单、退款和实际收入以 Shopify 为准。GA4 与 Shopify 不一致属于平台统计口径差异；偏差较大时优先排查 GA4 事件、Consent Mode、跨域、时区、归因窗口、广告拦截和重复触发，不应直接修改 Shopify 实际订单。

| 字段 | 类型 | 说明 |
|---|---|---|
| 汇总唯一键 | `singleLineText` | 唯一键建议为：日期\|分析粒度\|维度值\|国家/地区\|设备类别，用于自动同步去重；不要人工修改。 |
| 日期 | `date` | GA4 汇总数据对应的自然日；必须与 Shopify 报表使用同一时区后再比较。 |
| 分析粒度 | `singleSelect` | 该行数据的汇总层级。不同粒度的行不可直接相加，否则会重复计算用户、会话和转化。 |
| 维度值 | `singleLineText` | 当前分析粒度对应的名称，例如 Paid Search、google / cpc、某广告系列、某落地页或某用户分群。 |
| 主要渠道组 | `singleLineText` | GA4 默认渠道组或自定义渠道组。渠道划分受 GA4 规则影响，可能与 Shopify 渠道分类不同。 |
| 会话来源 | `singleLineText` | GA4 session source，表示本次会话来源；与首次用户来源不是同一口径。 |
| 会话媒介 | `singleLineText` | GA4 session medium，例如 cpc、organic、email、referral。 |
| 会话广告系列 | `singleLineText` | GA4 session campaign。依赖 UTM、自动标记和平台连接，缺失时可能显示 not set。 |
| 落地页 | `multilineText` | 会话开始时的落地页路径或完整地址，用于分析第一屏和页面承接效果。 |
| 页面路径/标题 | `multilineText` | 页面级分析使用的路径与标题；页面数据属于 GA4 浏览行为，不等同 Shopify 商品访问报表。 |
| 首次用户来源 | `singleLineText` | GA4 first user source，表示该用户首次被 GA4 识别时的来源；它与当前会话来源、Shopify 订单来源可能不同。 |
| 首次用户媒介 | `singleLineText` | GA4 first user medium，用于首次获客分析；不应与最终成交来源混用。 |
| 首次用户广告系列 | `singleLineText` | GA4 first user campaign。受 Cookie、Consent Mode、跨设备及首次访问识别影响。 |
| 国家/地区 | `singleLineText` | GA4 根据访问环境推断的国家/地区，可能与 Shopify 收货国家不同。 |
| 设备类别 | `singleSelect` | GA4 device category，用于比较桌面、手机和平板的浏览与转化差异。 |
| 商品 ID / SKU | `singleLineText` | GA4 ecommerce item_id。必须尽量与 Shopify SKU 对齐，否则产品级浏览和订单无法可靠对账。 |
| 商品名称 | `singleLineText` | GA4 ecommerce item_name。商品改名可能造成同一 SKU 出现多个名称，产品分析优先使用商品 ID / SKU。 |
| 活跃用户数 | `number` | GA4 Active users。属于 GA4 识别到的用户，受 Cookie、Consent Mode、跨设备和广告拦截影响，不等同真实自然人数或 Shopify 客户数。 |
| 新用户数 | `number` | GA4 New users。Cookie 被清除、换设备或未登录会导致同一人被重复识别。 |
| 会话数 | `number` | GA4 Sessions。一位用户可产生多次会话，不等同用户数。 |
| 互动会话数 | `number` | GA4 Engaged sessions：持续超过阈值、发生关键事件或达到一定页面浏览条件的会话；以 GA4 当前配置为准。 |
| 互动率 | `percent` | GA4 Engagement rate = 互动会话数 ÷ 会话数。用于比较流量质量，不代表购买率。 |
| 平均互动时长（秒） | `number` | GA4 平均互动时长，单位秒；只统计网页处于前台并被 GA4 识别的互动时间，不等同用户实际阅读时长。 |
| 浏览次数 | `number` | GA4 Views，包括重复页面浏览；不等同去重访客数。 |
| 每位活跃用户浏览次数 | `number` | GA4 Views per active user，用于判断浏览深度；不同分析粒度不可相加。 |
| 产品查看用户数 | `number` | 分析期内触发 view_item 的去重 GA4 用户数。受事件埋点、Cookie 和 Consent Mode 影响，不等同 Shopify 商品访问人数。 |
| 加购用户数 | `number` | 分析期内触发 add_to_cart 的去重 GA4 用户数。快捷购买可能绕过加购，因此加购人数可以低于开始结账人数。 |
| 开始结账用户数 | `number` | 分析期内触发 begin_checkout 的去重 GA4 用户数。Shopify 快捷购买、Buy Now、购物车抽屉和结账跨域会影响事件顺序与完整性。 |
| 购买用户数 | `number` | 分析期内被 GA4 识别到 purchase 的去重用户数。它不是 Shopify 实际买家数；未同意追踪、跨设备、事件丢失或重复触发都会产生差异。 |
| 只看产品用户数 | `number` | 用户分群：分析期内触发 view_item，但未触发 add_to_cart、begin_checkout 或 purchase。必须用用户级细分计算，不能用事件数直接相减。 |
| 加购未结账用户数 | `number` | 用户分群：分析期内触发 add_to_cart，但未触发 begin_checkout 或 purchase。快捷购买用户可能不会进入该分群。 |
| 结账放弃用户数 | `number` | 用户分群：分析期内触发 begin_checkout，但未触发 purchase。若结账域名或 purchase 追踪不完整，该人数会被平台高估。 |
| 高意向未购用户数 | `number` | 用户分群：分析期内触发 view_item、add_to_cart 或 begin_checkout 中至少一个，但未触发 purchase。它包含“只看产品、加购未结账、结账放弃”等人群，不可再与这些分群相加。 |
| 已购用户数 | `number` | 用户分群：分析期内触发 purchase 的去重 GA4 用户数。仅代表 GA4 观察到的买家，最终买家数量以 Shopify 为准。 |
| GA4购买事件数 | `number` | GA4 purchase 事件数或 transactions 指标。重复触发会高估，追踪丢失会低估；与 Shopify 订单数不一致属于平台口径差异。 |
| GA4购买收入 | `currency` | GA4 purchase 事件上报的收入。可能因币种、税费、运费、退款、重复或缺失事件与 Shopify 不同，仅用于行为和归因分析。 |
| Shopify订单数 | `number` | 同一日期和维度下可归因的 Shopify 实际订单数，是销售事实口径。与 GA4 不一致时保留两套数据，不回写修改 Shopify。 |
| Shopify净收入 | `currency` | 同一日期和维度下 Shopify 实际净收入，考虑退款与订单状态后作为业务判断口径。GA4 收入只做行为和归因参考。 |
| 同步来源 | `singleSelect` | 该行数据的提取或同步方式。用户级路径优先使用 GA4 BigQuery；日级汇总可使用 GA4 Data API。 |
| 最后同步时间 | `dateTime` | 该汇总记录最近一次更新的时间，用于判断数据是否已完成延迟回补。 |
| 备注 | `multilineText` | 记录埋点异常、数据阈值、not set、Consent Mode、时区、跨域、退款或其他平台口径说明。 |
| GA4订单差额 | `formula` | GA4购买事件数减 Shopify订单数。该差额反映平台追踪与交易事实口径差异，不代表 Shopify 漏单。 |
| GA4收入差额 | `formula` | GA4购买收入减 Shopify净收入。偏差可能来自退款、税费、运费、币种、重复/缺失事件及归因窗口。 |
| 订单偏差率 | `formula` | GA4购买事件与 Shopify订单数差额的绝对值 ÷ Shopify订单数。Shopify 为分母和交易事实基准。 |
| 数据口径状态 | `formula` | 自动标记 GA4 与 Shopify 订单口径。偏差率达到 10% 标记为“平台口径偏差较大”，应排查 GA4/GTM/Consent/跨域等平台追踪问题；实际订单仍以 Shopify 为准。 |
| GA4购买转化率 | `formula` | GA4观察到的购买用户数 ÷ 活跃用户数。仅用于比较行为趋势，不等同 Shopify 实际订单转化率。 |
| 商品查看至加购率 | `formula` | 加购用户数 ÷ 产品查看用户数。快捷购买可能绕过 add_to_cart，因此该指标需结合结账路径判断。 |
| 结账至购买率 | `formula` | GA4购买用户数 ÷ 开始结账用户数。结账跨域或 purchase 事件缺失会人为压低该指标。 |


