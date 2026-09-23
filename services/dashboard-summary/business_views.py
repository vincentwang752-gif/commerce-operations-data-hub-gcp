"""Readable, recomputed joins. Never change source records or infer attribution."""
from collections import defaultdict
from decimal import Decimal
from metrics import links, number, truth, day

VIEW_NAMES = ("客户跟进总览", "订单来源总览", "红人效果总览")
OWNER = "commerce-business-views-v1"


def unique_index(rows, field):
    groups = defaultdict(list)
    for row in rows:
        key = str(row.get(field) or "").strip()
        if key:
            groups[key].append(row)
    return {k: v[0] for k, v in groups.items() if len(v) == 1}


def joined(values):
    return "；".join(sorted({str(v) for v in values if v not in (None, "")}))


def money(row):
    amount = number(row.get("订单收入"))
    refund = number(row.get("退款金额"))
    if amount is None or not row.get("币种"):
        return None
    if str(row.get("付款状态") or "").upper() not in {"PAID", "PARTIALLY_REFUNDED", "REFUNDED"} or truth(row.get("是否取消")):
        return None
    if str(row.get("付款状态") or "").upper() in {"PARTIALLY_REFUNDED", "REFUNDED"} and refund is None:
        return None
    # Same historical blank-refund convention as the existing dashboard.
    return amount - (refund if refund is not None else Decimal(0))


def build_views(tables, stamp):
    customers = unique_index(tables["客户"], "记录 ID")
    shop_customers = unique_index(tables["客户"], "Shopify 客户 ID")
    orders = unique_index(tables["订单"], "订单 ID")
    creators = unique_index(tables["红人"], "记录 ID")
    content = unique_index(tables["内容资产"], "记录 ID")
    touches = defaultdict(list)
    for t in tables["归因触点"]:
        for oid in set(links(t.get("订单"))):
            touches[oid].append(t)
    customer_orders, customer_life = defaultdict(list), defaultdict(list)
    creator_orders, creator_assists = defaultdict(list), defaultdict(set)
    customer_rows, order_rows, creator_rows = [], [], []
    for life in tables["客户生命周期"]:
        keys = links(life.get("客户"))
        if len(keys) == 1 and keys[0] in customers:
            customer_life[keys[0]].append(life)
    for oid, order in orders.items():
        keys = links(order.get("客户"))
        customer = customers.get(keys[0]) if len(keys) == 1 else None
        match = "记录关联" if customer else "未匹配/关联异常"
        if not keys:
            customer = shop_customers.get(str(order.get("Shopify 客户 ID") or ""))
            if customer:
                match = "Shopify客户ID匹配"
        if customer:
            customer_orders[customer["记录 ID"]].append(order)
        ts = touches.get(order.get("记录 ID"), [])
        finals = [t for t in ts if truth(t.get("是否最终触点"))]
        final = finals[0] if len(finals) == 1 else None
        creator_keys = links(final.get("红人")) if final else []
        selected = creator_keys[0] if len(creator_keys) == 1 and creator_keys[0] in creators else None
        for t in ts:
            for key in set(links(t.get("红人"))):
                if key in creators:
                    creator_assists[key].add(oid)
        net = money(order)
        if selected and net is not None:
            creator_orders[selected].append(order)
        evidence = (final.get("归因方式") or "归因方式未记录") if final else ("多个最终触点，待核对" if finals else "未记录最终触点")
        names = joined(creators[k].get("红人名称") for t in ts for k in links(t.get("红人")) if k in creators)
        assets = joined(content[k].get("内容名称") for t in ts for k in links(t.get("内容资产")) if k in content)
        action = []
        if not customer: action.append("核对客户关联")
        if len(finals) > 1: action.append("核对最终触点冲突")
        if creator_keys and not selected: action.append("核对最终红人关联")
        if names and not assets: action.append("补内容证据，不自动分摊")
        order_rows.append([oid, customer.get("客户名称", "") if customer else "待匹配", order.get("主产品", ""),
            day(order.get("下单时间")), order.get("付款状态", ""), order.get("履约状态") or "未记录", order.get("币种", ""),
            float(net) if net is not None else "", "纳入" if net is not None else "排除/金额待核对", names or "未关联红人",
            creators[selected].get("红人名称") if selected else "未分配", evidence,
            assets or "未关联内容", len(ts), order.get("UTM 来源", ""), order.get("UTM 媒介", ""),
            order.get("UTM 广告系列", ""), order.get("优惠码", ""), joined(action) or "无待处理项", match,
            customer.get("邮箱", "") if customer else order.get("客户邮箱", ""), order.get("记录 ID", ""), stamp])
    for key, customer in customers.items():
        os = customer_orders[key]
        ls = customer_life[key]
        amounts = defaultdict(lambda: Decimal(0))
        valid = []
        for order in os:
            net = money(order)
            if net is not None:
                valid.append(order)
                amounts[order["币种"]] += net
        stage1 = any(truth(x.get("售前问卷已完成")) for x in ls)
        stage2 = any(truth(x.get("使用后问卷已完成")) for x in ls)
        stage = "两阶段完成" if stage1 and stage2 else "仅阶段1完成" if stage1 else "仅阶段2完成" if stage2 else "未记录完成"
        if stage1 and stage2 and len(ls) > 1:
            stage = "两阶段有记录，需按订单核对"
        action = []
        if len(ls) > 1: action.append("多条问卷状态，需按订单核对")
        if not os: action.append("无已关联订单")
        if stage2 and not stage1: action.append("核对阶段1记录")
        if any(x.get("延保审核状态") != "已确认" for x in ls): action.append("延保待人工核对")
        latest = max(os, key=lambda o: str(o.get("下单时间") or ""), default={})
        customer_rows.append([customer.get("客户名称") or "未命名客户", customer.get("邮箱", ""), customer.get("国家/地区", ""),
            len(valid), joined(f"{cur} {amount:,.2f}" for cur, amount in amounts.items()),
            day(latest.get("下单时间")), latest.get("主产品", ""), stage,
            joined(x.get("延保天数") for x in ls), joined(x.get("延保审核状态") or "未记录" for x in ls) or "无延保记录",
            joined(action) or "无待处理项", joined(o.get("订单 ID") for o in os),
            joined(x.get("对应S1订单ID") for x in ls), len(ls), customer.get("Shopify 客户 ID", ""), key, stamp])
    for key, creator in creators.items():
        assets = [c for c in content.values() if key in links(c.get("红人"))]
        amounts = defaultdict(lambda: Decimal(0))
        for order in creator_orders[key]:
            amounts[order["币种"]] += money(order)
        platforms = links(creator.get("平台"))
        creator_rows.append([creator.get("红人名称") or "未命名红人", creator.get("账号名称", ""), joined(platforms) if platforms else creator.get("平台", ""),
            creator.get("负责人", ""), creator.get("引入方/供应商", ""), len(assets), len(creator_assists[key]),
            len(creator_orders[key]), joined(f"{cur} {amount:,.2f}" for cur, amount in amounts.items()),
            joined(c.get("内容名称") for c in assets), joined(c.get("产品") for c in assets),
            joined(c.get("内容链接") for c in assets), creator.get("默认优惠码", ""), creator.get("默认推广链接", ""),
            "已有内容关联；广告需明确素材关联" if assets else "待运营补录内容链接及产品", key, stamp])
    return {
        VIEW_NAMES[0]: [["客户名称", "邮箱", "国家/地区", "已付款订单数（已同步）", "退款后金额（分币种）", "最近下单日期", "最近购买产品", "问卷完成状态", "已记录延保天数", "延保审核状态", "下一步处理", "关联订单ID", "问卷对应S1订单ID", "问卷状态记录数", "Shopify客户ID", "客户记录ID", "视图更新时间UTC"]] + sorted(customer_rows, key=lambda r: r[5], reverse=True),
        VIEW_NAMES[1]: [["订单ID", "客户名称", "主产品", "下单日期", "付款状态", "履约状态", "币种", "退款后订单金额", "金额统计状态", "触点关联红人", "最终归因红人", "最终归因证据", "关联内容", "触点数", "UTM来源", "UTM媒介", "UTM广告系列", "优惠码", "下一步处理", "客户匹配依据", "客户邮箱", "订单记录ID", "视图更新时间UTC"]] + sorted(order_rows, key=lambda r: r[3], reverse=True),
        VIEW_NAMES[2]: [["红人名称", "账号名称", "平台", "负责人", "引入方/供应商", "已关联内容数", "涉及订单数（不等于成交归因）", "最终归因已付款订单数", "最终归因退款后金额（分币种）", "关联内容名称", "推广产品", "内容链接", "默认优惠码", "默认推广链接", "关联缺口", "红人记录ID", "视图更新时间UTC"]] + sorted(creator_rows, key=lambda r: r[7], reverse=True),
    }
