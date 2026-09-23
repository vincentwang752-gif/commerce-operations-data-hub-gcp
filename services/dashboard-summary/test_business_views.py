import unittest
from business_views import build_views, VIEW_NAMES
from view_writer import requests_for_views


class ViewsTest(unittest.TestCase):
    def tables(self):
        return {"客户": [{"记录 ID": "c", "客户名称": "Demo", "Shopify 客户 ID": "1"}],
                "订单": [{"记录 ID": "o", "订单 ID": "100", "客户": '["c"]', "付款状态": "paid", "订单收入": 100, "退款金额": 10, "币种": "USD"}],
                "红人": [{"记录 ID": "r", "红人名称": "Creator"}], "内容资产": [], "归因触点": [], "客户生命周期": []}

    def test_customer_order_join_and_currency(self):
        t = self.tables()
        t["订单"].append({**t["订单"][0], "记录 ID": "o2", "订单 ID": "101", "币种": "EUR"})
        row = build_views(t, "now")[VIEW_NAMES[0]][1]
        self.assertEqual(row[3], 2)
        self.assertEqual(row[4], "EUR 90.00；USD 90.00")

    def test_multiple_final_touches_no_revenue_duplication(self):
        t = self.tables()
        t["归因触点"] = [{"订单": '["o"]', "红人": '["r"]', "是否最终触点": True}] * 2
        result = build_views(t, "now")
        self.assertEqual(result[VIEW_NAMES[2]][1][7], 0)
        self.assertEqual(result[VIEW_NAMES[1]][1][11], "多个最终触点，待核对")

    def test_cancelled_excluded_and_duplicate_orders_fail_closed(self):
        t = self.tables()
        t["订单"][0]["是否取消"] = True
        self.assertEqual(build_views(t, "now")[VIEW_NAMES[0]][1][3], 0)
        t["订单"].append(dict(t["订单"][0]))
        self.assertEqual(len(build_views(t, "now")[VIEW_NAMES[1]]), 1)

    def test_survey_completion_not_approval(self):
        t = self.tables()
        t["客户生命周期"] = [{"客户": '["c"]', "售前问卷已完成": True, "延保天数": 180, "延保审核状态": "待审核"}]
        row = build_views(t, "now")[VIEW_NAMES[0]][1]
        self.assertEqual(row[7], "仅阶段1完成")
        self.assertEqual(row[9], "待审核")
        self.assertIn("人工", row[10])

    def test_broken_link_does_not_fallback_to_another_customer(self):
        t = self.tables()
        t["订单"][0].update({"客户": '["missing"]', "Shopify 客户 ID": "1"})
        self.assertEqual(build_views(t, "now")[VIEW_NAMES[1]][1][1], "待匹配")

    def test_refunded_missing_amount_not_counted(self):
        t = self.tables()
        t["订单"][0].update({"付款状态": "REFUNDED", "退款金额": ""})
        self.assertEqual(build_views(t, "now")[VIEW_NAMES[1]][1][7], "")

    def test_writer_keeps_formula_like_names_as_text(self):
        t = self.tables()
        t["客户"][0]["客户名称"] = '=IMPORTDATA("https://example.invalid")'
        writes = requests_for_views(build_views(t, "now"), {})
        customer_write = next(w["updateCells"] for w in writes if "updateCells" in w)
        self.assertIn("stringValue", customer_write["rows"][1]["values"][0]["userEnteredValue"])

    def test_stages_on_different_records_require_review(self):
        t = self.tables()
        t["客户生命周期"] = [{"客户": '["c"]', "售前问卷已完成": True}, {"客户": '["c"]', "使用后问卷已完成": True}]
        self.assertIn("按订单核对", build_views(t, "now")[VIEW_NAMES[0]][1][7])


if __name__ == "__main__":
    unittest.main()
