"""PII-free dashboard summaries derived from the existing Chinese Sheets schema.

No source writes. Revenue is order total less refunds (tax/shipping included),
not merchandise net sales. Dates use Asia/Shanghai for orders; GA4 dates retain
the property's calendar. Unknowns remain explicit instead of fabricated zeros.
"""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def truth(value):
    return value is True or str(value).strip().lower() in {"true", "1"}


def number(value):
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def day(value):
    if not value:
        return ""
    try:
        if isinstance(value, (int, float)):
            return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
        text = str(value)
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
        return dt.date().isoformat()
    except (ValueError, OverflowError):
        return ""


def links(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (ValueError, TypeError):
        return []


def summarize(tables, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    cutoff = (today - timedelta(days=4)).isoformat()
    issues = []
    orders = {}
    duplicate_ids = set()
    for row in tables.get("订单", []):
        key = str(row.get("订单 ID", "")).strip()
        if not key:
            issues.append(["订单", "缺少订单ID", 1])
            continue
        if key in orders:
            duplicate_ids.add(key)
        else:
            orders[key] = row
    for key in duplicate_ids:
        del orders[key]
    if duplicate_ids:
        issues.append(["订单", "重复订单ID，已从指标排除", len(duplicate_ids)])

    creators = {r.get("记录 ID"): r.get("红人名称") or "未命名红人"
                for r in tables.get("红人", [])}
    final_by_order = defaultdict(list)
    for touch in tables.get("归因触点", []):
        if truth(touch.get("是否最终触点")):
            for key in set(links(touch.get("订单"))):
                final_by_order[key].append(touch)

    sales = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0)])
    attribution = defaultdict(lambda: [0, Decimal(0)])
    for row in orders.values():
        dt = day(row.get("下单时间"))
        currency = str(row.get("币种") or "未记录")
        paid = str(row.get("付款状态", "")).upper()
        amount, refund = number(row.get("订单收入")), number(row.get("退款金额"))
        # Shopify serializer uses blank refund for historical zero; disclose this.
        refund = refund if refund is not None else Decimal(0)
        if not dt or amount is None or currency == "未记录":
            issues.append(["订单", "日期、金额或币种缺失，已排除", 1])
            continue
        if truth(row.get("是否取消")) or paid not in {"PAID", "PARTIALLY_REFUNDED", "REFUNDED"}:
            continue
        net = amount - refund
        product = row.get("主产品") or "未分类"
        country = row.get("国家/地区") or "未记录"
        values = sales[(dt, currency, product, country)]
        values[0] += 1
        values[1] += amount
        values[2] += refund
        values[3] += net
        candidates = final_by_order.get(row.get("记录 ID"), [])
        creator, method, status = "未关联红人", "未记录", "无最终触点"
        if len(candidates) > 1:
            status = "多条最终触点，待核对"
        elif candidates:
            touch = candidates[0]
            ids = links(touch.get("红人"))
            method = touch.get("归因方式") or "历史未记录"
            if len(ids) == 1:
                creator = creators.get(ids[0], "红人关联缺失")
            elif len(ids) > 1:
                creator = "多红人关联，待核对"
            status = ("Collabs平台确认" if method == "Shopify Collabs 平台归因"
                      else "规则匹配" if method in {"优惠码", "Coupon", "UTM", "点击 ID"}
                      else "历史或其他来源")
        values = attribution[(dt, currency, creator, method, status)]
        values[0] += 1
        values[1] += net

    lifecycle = defaultdict(int)
    seen = set()
    for row in tables.get("客户生命周期", []):
        key = row.get("记录 ID")
        if not key or key in seen:
            issues.append(["问卷", "生命周期记录ID缺失或重复", 1])
            continue
        seen.add(key)
        one, two = truth(row.get("售前问卷已完成")), truth(row.get("使用后问卷已完成"))
        if not (one or two):
            continue
        # Counts are lifecycle records, NOT submitted forms or distinct invitations.
        stage = "两阶段完成" if one and two else "仅阶段1完成" if one else "仅阶段2完成"
        review = row.get("延保审核状态") or "未记录"
        warranty = number(row.get("延保天数"))
        dt = day(row.get("第二阶段完成时间") if two else row.get("第一阶段完成时间"))
        lifecycle[(dt or "未记录", stage, review, str(warranty) if warranty is not None else "未记录")] += 1

    web, web_seen = [], set()
    for row in tables.get("GA4运营与用户行为", []):
        dt = day(row.get("日期"))
        if row.get("分析粒度") != "全站" or not dt or dt > cutoff:
            continue
        if dt in web_seen:
            raise ValueError("Duplicate GA4 whole-site date; summary not written")
        web_seen.add(dt)
        values = [number(row.get(k)) for k in ["会话数", "互动会话数", "平均互动时长（秒）", "浏览次数", "GA4购买事件数", "活跃用户数"]]
        sessions, engaged, duration, views, purchases, active = values
        total_duration = sessions * duration if sessions is not None and duration is not None else None
        web.append([dt, sessions, engaged, total_duration, views, purchases, active])
    counts = defaultdict(int)
    for source, reason, count in issues:
        counts[(source, reason)] += count
    result = {
        "经营日汇总": [["日期", "币种", "主产品", "国家地区", "已付款订单数", "订单总额", "退款金额", "退款后订单金额"]] +
            [list(k) + v for k, v in sorted(sales.items())],
        "归因日汇总": [["日期", "币种", "红人", "归因方式", "证据状态", "已付款订单数", "退款后订单金额"]] +
            [list(k) + v for k, v in sorted(attribution.items())],
        "问卷完成汇总": [["最近阶段完成日期", "完成阶段", "延保审核状态", "已记录延保天数", "生命周期记录数"]] +
            [list(k) + [v] for k, v in sorted(lifecycle.items())],
        "网站日汇总": [["日期", "会话数", "互动会话数", "互动总时长秒", "浏览次数", "购买事件数", "当日活跃用户数"]] + sorted(web),
        "数据说明": [["范围", "说明", "数值"]] + [[a, b, c] for (a, b), c in sorted(counts.items())] + [
            ["GA4", "仅纳入T-4及以前，平台日期保留原属性时区", cutoff],
            ["金额", "订单总额已含折扣，减退款；含税运费，不等同商品净销售额。历史空白退款按0处理。", ""],
            ["归因", "每单只计一次金额。多条最终触点不分配给某位红人，单列待核对。", ""],
            ["问卷", "按生命周期记录统计，非表单提交次数；缺邀请人数，不计算回收率。", ""],
            ["GA4", "不可加总每日活跃用户为跨日去重用户。互动时长须用总时长除会话数。", ""],
            ["跨平台", "GA4行为/归因口径与Shopify交易口径不同，差异需先核对时区、覆盖和平台规则，不能直接视为丢单。", ""],
        ],
    }
    # Google Sheets JSON requires ordinary numeric values.
    return {name: [[float(x) if isinstance(x, Decimal) else "" if x is None else x for x in row]
                   for row in rows] for name, rows in result.items()}
