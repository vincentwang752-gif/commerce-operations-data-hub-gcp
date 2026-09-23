import unittest
from copy import deepcopy
from main import SheetsStore


class MemoryStore(SheetsStore):
    def __init__(self):
        fields = ['客户', '售前问卷已完成', '使用后问卷已完成', '延保天数', '人工备注']
        super().__init__({'tables':[{'name':'客户生命周期', 'spreadsheet_id':'test',
                         'fields':[{'name':f, 'type':'singleLineText'} for f in fields],
                         'key_fields':['客户']}]}, None)
        self.rows = []
        self.calls = []

    def read(self, table, include_layout=False):
        result = (self.rows, len(self.rows) + 2)
        layout = {name:i + 1 for i,name in enumerate(['记录 ID'] + [f['name'] for f in table['fields']])}
        return result + (layout,) if include_layout else result

    def api(self, method, table, suffix, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if suffix == '/values:batchUpdate':
            # Simulate persisted cells; failed writes must not mutate read state.
            for change in kwargs['json']['data']:
                import re
                col, row = re.search(r'!([A-Z]+)(\d+)$', change['range']).groups()
                index = int(row) - 2
                while len(self.rows) <= index:
                    self.rows.append({'id':'', 'fields':{}, '_row':index+2})
                value = change['values'][0][0]
                if col == 'A':
                    self.rows[index]['id'] = value
                else:
                    field = self.config['tables'][0]['fields'][ord(col)-ord('B')]['name']
                    if field == '客户':
                        import json
                        value = json.loads(value)
                    self.rows[index]['fields'][field] = value
        return {}

    def ensure_rows(self, table, required):
        pass


class StoreTests(unittest.TestCase):
    def test_auto_number_is_allocated_once(self):
        store = MemoryStore()
        store.config['tables'][0]['fields'].append({'name':'序号', 'type':'autoNumber'})
        first = store.write_records('客户生命周期', {'fields':{'客户':['c1']}})
        again = store.write_records('客户生命周期', {'fields':{'客户':['c1']}})
        second = store.write_records('客户生命周期', {'fields':{'客户':['c2']}})
        self.assertEqual(first['fields']['序号'], 1)
        self.assertEqual(again['fields']['序号'], 1)
        self.assertEqual(second['fields']['序号'], 2)

    def test_retry_upserts_and_preserves_notes(self):
        store = MemoryStore()
        first = store.write_records('客户生命周期', {'fields':{'客户':['c1'], '人工备注':'已人工确认'}})
        second = store.write_records('客户生命周期', {'fields':{'客户':['c1'], '售前问卷已完成':True}})
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(store.rows), 1)
        self.assertEqual(second['fields']['人工备注'], '已人工确认')
        self.assertTrue(all(update['range'].split('!')[1][0] != 'F' for update in store.calls[-1]['json']['data']))
        self.assertEqual(store.calls[-1]['json']['valueInputOption'], 'RAW')

    def test_late_stage_one_cannot_reduce_warranty(self):
        store = MemoryStore()
        store.write_records('客户生命周期', {'fields':{'客户':['c1'], '使用后问卷已完成':True, '延保天数':360}})
        final = store.write_records('客户生命周期', {'fields':{'客户':['c1'], '售前问卷已完成':True, '延保天数':180}})
        self.assertEqual(final['fields']['延保天数'], 360)
        self.assertTrue(final['fields']['使用后问卷已完成'])

    def test_missing_key_or_unknown_field_fails_before_write(self):
        store = MemoryStore()
        for fields in ({'延保天数':180}, {'客户':['c1'], 'unknown':123}):
            with self.assertRaises(ValueError):
                store.write_records('客户生命周期', {'fields':fields})
        self.assertEqual(store.calls, [])


if __name__ == '__main__':
    unittest.main()
