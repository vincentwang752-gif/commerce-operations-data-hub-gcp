import os
import unittest
from unittest.mock import patch
import google_ads_sync as sync


class ReportingTests(unittest.TestCase):
    def fixture(self):
        account = {'customer_id':'1234567890', 'account_type':'品牌自投'}
        extracted = ({'currencyCode':'USD', 'timeZone':'America/Los_Angeles'},
            [{'campaign':{'id':'77', 'name':'PMax', 'status':'ENABLED'}}], [],
            [{'campaign':{'id':'77'}, 'metrics':{'costMicros':'1234567', 'clicks':'3', 'impressions':'10'}}],
            [{'campaign':{'id':'77'}, 'metrics':{'conversions':1.5, 'conversionsValue':300}}])
        return account, extracted

    def test_campaign_grain_includes_pmax_without_ad(self):
        account, extracted = self.fixture()
        campaigns, ads, daily = sync.transform(account, '2026-01-01', extracted, 'now')
        self.assertEqual(len(campaigns), 1)
        self.assertEqual(ads, [])
        self.assertEqual(daily[0]['广告花费'], 1.234567)
        self.assertEqual(daily[0]['平台购买数'], 1.5)
        self.assertNotIn('广告 ID', daily[0])
        self.assertNotIn('Shopify 订单数', daily[0])
        self.assertNotIn('备注', daily[0])

    def test_stable_key_and_account_separation(self):
        account, extracted = self.fixture()
        first = sync.transform(account, '2026-01-01', extracted, 'now')[2][0]
        again = sync.transform(account, '2026-01-01', extracted, 'later')[2][0]
        self.assertEqual(first['表现唯一键'], again['表现唯一键'])
        account['customer_id'] = '9876543210'
        other = sync.transform(account, '2026-01-01', extracted, 'now')[2][0]
        self.assertNotEqual(first['表现唯一键'], other['表现唯一键'])

    def test_duplicate_account_rejected(self):
        with patch.dict(os.environ, {'GOOGLE_ADS_ACCOUNTS_JSON':'[{"customer_id":"1234567890","account_type":"品牌自投"},{"customer_id":"1234567890","account_type":"品牌自投"}]'}):
            with self.assertRaises(ValueError):
                sync.account_config()

    def test_purchase_without_activity_is_retained(self):
        account, extracted = self.fixture()
        extracted = (*extracted[:3], [], extracted[4])
        row = sync.transform(account, '2026-01-01', extracted, 'now')[2][0]
        self.assertEqual(row['平台购买数'], 1.5)
        self.assertEqual(row['广告花费'], 0)
        self.assertIsNone(row['平台 ROAS'])

    def test_legacy_grain_blocks_write(self):
        with patch.dict(os.environ, {'SHEETS_STORE_URL':'https://private.run.app'}):
            store = sync.Store()
        with patch.object(store, 'read', return_value=[{'fields':{'表现唯一键':'2026-01-01|google_ads|1234567890|88'}}]):
            with self.assertRaises(ValueError):
                store.check_day('1234567890', '2026-01-01')

    def test_purchase_only_query(self):
        account, extracted = self.fixture()
        metadata = [{'customer':dict(extracted[0], id=account['customer_id'])}]
        with patch.object(sync, 'query', side_effect=[metadata, [], [], [], []]) as query:
            sync.extract('token', account, '2026-01-01')
        self.assertIn("conversion_action_category = 'PURCHASE'", query.call_args.args[2])
        self.assertIn('segments.conversion_action_category,', query.call_args.args[2].split(' FROM ')[0])

    def test_write_response_must_match(self):
        with patch.dict(os.environ, {'SHEETS_STORE_URL':'https://private.run.app'}):
            store = sync.Store()
        with patch.object(store, 'call', return_value={'records':[{'id':'a','fields':{'key':'wrong'}}]}):
            with self.assertRaises(RuntimeError):
                store.upsert('广告', 'key', [{'key':'right'}])


if __name__ == '__main__':
    unittest.main()
