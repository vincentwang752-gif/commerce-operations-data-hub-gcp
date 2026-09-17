import unittest
from datetime import date
from metrics import summarize


class SummaryTests(unittest.TestCase):
    def order(self, **changes):
        return {"记录 ID": "rec1", "订单 ID": "o1", "下单时间": "2026-09-01T20:00:00Z",
                "币种": "USD", "付款状态": "PAID", "订单收入": 90, "折扣金额": 10,
                "退款金额": 20, **changes}

    def test_net_not_double_discounted_and_local_day(self):
        out = summarize({"订单": [self.order()]}, date(2026, 9, 17))
        self.assertEqual(out["经营日汇总"][1][0], "2026-09-02")
        self.assertEqual(out["经营日汇总"][1][-1], 70)

    def test_duplicate_order_excluded(self):
        out = summarize({"订单": [self.order(), self.order()]})
        self.assertEqual(len(out["经营日汇总"]), 1)

    def test_authorized_and_cancelled_excluded(self):
        for change in [{"付款状态": "AUTHORIZED"}, {"是否取消": True}]:
            self.assertEqual(len(summarize({"订单": [self.order(**change)]})["经营日汇总"]), 1)

    def test_multi_final_never_duplicates_revenue(self):
        touch = {"是否最终触点": True, "订单": '["rec1"]', "红人": '["creator1"]'}
        out = summarize({"订单": [self.order()], "归因触点": [touch, touch]})
        self.assertEqual(out["归因日汇总"][1][-2:], [1, 70])
        self.assertEqual(out["归因日汇总"][1][4], "多条最终触点，待核对")

    def test_t4_weighted_components_and_nulls(self):
        out = summarize({"GA4运营与用户行为": [
            {"日期": "2026-09-13", "分析粒度": "全站", "会话数": 10, "平均互动时长（秒）": 3},
            {"日期": "2026-09-14", "分析粒度": "全站", "会话数": 50},
        ]}, date(2026, 9, 17))
        self.assertEqual(len(out["网站日汇总"]), 2)
        self.assertEqual(out["网站日汇总"][1][3], 30)
        self.assertEqual(out["网站日汇总"][1][2], "")

    def test_no_pii_output(self):
        out = summarize({"订单": [self.order(**{"客户邮箱": "private@example.invalid"})]})
        self.assertNotIn("private@example.invalid", str(out))


if __name__ == "__main__":
    unittest.main()
