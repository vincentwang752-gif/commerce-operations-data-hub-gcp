"""The physical column order must never become a write contract."""
import unittest
from copy import deepcopy
from main import SheetsStore


class GridStore(SheetsStore):
    def __init__(self, headers, cells):
        super().__init__({'tables': [{'name': '广告', 'spreadsheet_id': 'test',
            'fields': [{'name': n, 'type': 'singleLineText'}
                       for n in ['广告唯一键', '广告名称']],
            'key_fields': ['广告唯一键']}]}, None)
        self.cells = [headers] + cells
        self.writes = []

    def grid(self, table):
        return {'columnCount': 4, 'rowCount': 100, 'sheetId': 1}

    def api(self, method, table, suffix, **kwargs):
        if method == 'GET':
            return {'values': deepcopy(self.cells)}
        self.writes.extend(kwargs['json']['data'])
        return {}


class LayoutTests(unittest.TestCase):
    def test_reordered_read_and_patch(self):
        store = GridStore(['广告名称', '记录 ID', '广告唯一键'], [['Ad', 'r1', 'key1']])
        result = store.list_records('广告', {})
        self.assertEqual(result['records'][0], {'id': 'r1', 'fields': {'广告唯一键': 'key1', '广告名称': 'Ad'}})
        store.write_records('广告', {'fields': {'广告名称': 'Updated'}}, 'r1')
        self.assertEqual(store.writes, [{'range': "'广告'!A2", 'values': [['Updated']]}])

    def test_insert_id_at_actual_position(self):
        store = GridStore(['广告名称', '广告唯一键', '记录 ID'], [])
        created = store.write_records('广告', {'fields': {'广告唯一键': 'key2', '广告名称': 'New'}})
        self.assertEqual(store.writes[0], {'range': "'广告'!C2", 'values': [[created['id']]]})
        self.assertEqual({w['range'] for w in store.writes}, {"'广告'!A2", "'广告'!B2", "'广告'!C2"})

    def test_optional_formula_column_is_not_part_of_record(self):
        store = GridStore(['广告系列名称', '广告名称', '广告唯一键', '记录 ID'],
                          [['Campaign', 'Ad', 'key1', 'r1']])
        self.assertNotIn('广告系列名称', store.list_records('广告', {})['records'][0]['fields'])
        store.write_records('广告', {'fields': {'广告名称': 'New'}}, 'r1')
        self.assertEqual(store.writes[0]['range'], "'广告'!B2")
        with self.assertRaises(ValueError):
            store.write_records('广告', {'fields': {'广告系列名称': 'bad'}}, 'r1')

    def test_invalid_headers_fail_closed(self):
        for headers in [['广告名称', '记录 ID'], ['广告名称', '记录 ID', '广告名称'],
                        ['广告名称', '记录 ID', 'wrong'],
                        ['广告名称', '记录 ID', '广告唯一键', 'unknown']]:
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                GridStore(headers, []).write_records('广告', {'fields': {'广告唯一键': 'k'}})

    def test_old_order_and_duplicate_ids(self):
        store = GridStore(['记录 ID', '广告唯一键', '广告名称'], [['r1', 'k', 'Ad']])
        self.assertEqual(store.list_records('广告', {})['records'][0]['id'], 'r1')
        store.cells.append(['r1', 'k2', 'Other'])
        with self.assertRaises(ValueError):
            store.read(store.table('广告'))


if __name__ == '__main__':
    unittest.main()
