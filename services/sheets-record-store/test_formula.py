import unittest
from formula import matches


class FilterTests(unittest.TestCase):
    def test_customer_and_escaped_input(self):
        self.assertTrue(matches("OR({Shopify 客户 ID}='123',LOWER({邮箱})='a@b.com')", {'邮箱':'A@B.COM'}))
        self.assertTrue(matches("{姓名}='O\\'Brien'", {'姓名':"O'Brien"}))
        self.assertFalse(matches("FALSE()", {}))

    def test_coupon_and_touchpoint(self):
        self.assertTrue(matches("UPPER(TRIM({默认优惠码}&''))='CODE'", {'默认优惠码':' code '}))
        query = "AND(FIND('shopify_order_id=123',{UTM 参数}),NOT({订单}),{行为数据来源}='Shopify')"
        fields = {'UTM 参数':'shopify_order_id=123', '行为数据来源':'Shopify'}
        self.assertTrue(matches(query, fields))
        self.assertFalse(matches(query, dict(fields, 订单=['record-1'])))

    def test_reject_unknown_syntax(self):
        for query in ('__import__(\'os\')', '{a}>1', "LOWER({邮箱})='x' garbage"):
            with self.assertRaises(ValueError):
                matches(query, {})


if __name__ == '__main__':
    unittest.main()
