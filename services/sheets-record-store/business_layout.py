"""Reorder advertising columns under the same mutex as record writes.

Uses existing private tables.json; no credentials or production IDs in source.
Run without --apply to inspect. Native column moves preserve cell metadata.
"""
import argparse
import json
from urllib.parse import quote
from main import store, column, DISPLAY_FIELDS
from writer_lock import writer_lock

PRIORITY = {
    '广告系列': ['广告系列名称', '状态', '每日预算', '投放目标', '产品',
             '账户类型', '平台', '币种', '开始日期', '结束日期', '落地页链接'],
    '广告': ['广告系列名称', '广告组名称', '广告名称', '状态', '账户类型',
           '平台', '落地页链接', '创意版本', '优惠码', '平台红人显示名', '合作来源/供应商'],
    '广告每日表现': ['广告系列名称', '日期', '广告花费', '平台购买数', '平台归因收入',
                 '平台 ROAS', '点击数', 'CTR', 'CPC', '曝光量', 'CPM',
                 '平台加购数', '平台发起结账数', '账户类型', '平台', '币种',
                 '落地页浏览量', '触达人数', 'Shopify 订单数', 'Shopify 归因收入', 'Shopify ROAS'],
}


def technical(name, types):
    return (' ID' in name or '唯一键' in name or
            types.get(name) == 'multipleRecordLinks')


def ordering(headers, types, priority):
    front = [h for h in priority if h in headers]
    business = [h for h in headers if h not in front and not technical(h, types)]
    hidden = [h for h in headers if h not in front and technical(h, types)]
    return front + business + hidden, len(front + business)


def move_requests(sid, old, new):
    current = list(old)
    requests = []
    for destination, name in enumerate(new):
        source = current.index(name)
        if source != destination:
            requests.append({'moveDimension': {'source': {'sheetId': sid,
                'dimension': 'COLUMNS', 'startIndex': source, 'endIndex': source + 1},
                'destinationIndex': destination}})
            current.insert(destination, current.pop(source))
    return requests


def name_formula(headers, source_headers):
    # Join on platform + account + campaign, never a campaign name alone.
    def ref(heads, name, tab=''):
        letter = column(heads.index(name) + 1)
        return f"{tab}{letter}2:{letter}"
    names = ['平台', '账户 ID', '广告系列 ID']
    own = '&"|"&'.join(ref(headers, n) for n in names)
    other = '&"|"&'.join(ref(source_headers, n, "'广告系列'!") for n in names)
    source = ref(source_headers, '广告系列名称', "'广告系列'!")
    key = ref(headers, '记录 ID')
    return f'=ARRAYFORMULA(IF({key}="","",IFNA(VLOOKUP({own},{{{other},{source}}},2,FALSE),"（待补名称）")))'


def main(apply=False):
    service = store()
    with writer_lock():
        plan = {}; requests = []; originals = {}
        for name, priority in PRIORITY.items():
            table = service.table(name)
            records, _ = service.read(table)
            originals[name] = records
            grid = service.grid(table); sid = grid['sheetId']
            tab = "'" + name + "'"
            headers = service.api('GET', table, '/values/' + quote(f'{tab}!A1:{column(grid["columnCount"])}1', safe=''))['values'][0]
            # Read native metadata before moving columns. Do not reconstruct cells.
            native = service.api('GET', table, '', params={'ranges': f'{tab}!A1:{column(len(headers))}3',
                'fields': 'sheets(data(rowData(values(userEnteredValue,dataValidation,chipRuns,userEnteredFormat))))'})
            assert native.get('sheets')
            new_headers = headers + [h for h in DISPLAY_FIELDS.get(name, set()) if h not in headers]
            if len(new_headers) > grid['columnCount']:
                requests.append({'appendDimension': {'sheetId': sid, 'dimension': 'COLUMNS',
                    'length': len(new_headers) - grid['columnCount']}})
            if len(new_headers) > len(headers):
                requests.append({'updateCells': {'start': {'sheetId': sid, 'rowIndex': 0, 'columnIndex': len(headers)},
                    'rows': [{'values': [{'userEnteredValue': {'stringValue': h}} for h in new_headers[len(headers):]]}],
                    'fields': 'userEnteredValue'}})
            types = {f['name']: f['type'] for f in table['fields']}
            ordered, visible = ordering(new_headers, types, priority)
            requests.extend(move_requests(sid, new_headers, ordered))
            plan[name] = {'headers': ordered, 'visible': visible, 'sid': sid, 'rows': grid['rowCount']}
        for name, p in plan.items():
            sid = p['sid']; width = len(p['headers'])
            requests.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS',
                'startIndex': 0, 'endIndex': width}, 'properties': {'hiddenByUser': False}, 'fields': 'hiddenByUser'}})
            requests.append({'updateDimensionProperties': {'range': {'sheetId': sid, 'dimension': 'COLUMNS',
                'startIndex': p['visible'], 'endIndex': width}, 'properties': {'hiddenByUser': True}, 'fields': 'hiddenByUser'}})
            frozen = 3 if name == '广告' else 1
            requests.append({'updateSheetProperties': {'properties': {'sheetId': sid,
                'gridProperties': {'frozenRowCount': 1, 'frozenColumnCount': frozen}},
                'fields': 'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}})
            for i,h in enumerate(p['headers'][:p['visible']]):
                pixels = 260 if '名称' in h else (140 if h in ('日期', '平台归因收入') else 115)
                if h in ('备注','落地页链接'): pixels = 260
                requests.append({'updateDimensionProperties': {'range': {'sheetId':sid,'dimension':'COLUMNS',
                    'startIndex':i,'endIndex':i+1},'properties':{'pixelSize':pixels},'fields':'pixelSize'}})
            requests.append({'repeatCell': {'range': {'sheetId':sid,'startRowIndex':0,'endRowIndex':1,
                'startColumnIndex':0,'endColumnIndex':p['visible']}, 'cell': {'userEnteredFormat': {
                'backgroundColor': {'red':0.93,'green':0.94,'blue':0.95},
                'textFormat': {'bold':True},'wrapStrategy':'WRAP','verticalAlignment':'MIDDLE'}},
                'fields':'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold,userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment'}})
            if name in DISPLAY_FIELDS:
                formula = name_formula(p['headers'], plan['广告系列']['headers'])
                requests.append({'updateCells': {'start': {'sheetId':sid,'rowIndex':1,'columnIndex':0},
                    'rows':[{'values':[{'userEnteredValue':{'formulaValue':formula}}]}], 'fields':'userEnteredValue'}})
                requests.append({'updateCells': {'start': {'sheetId':sid,'rowIndex':0,'columnIndex':0},
                    'rows':[{'values':[{'note':'仅展示：按平台、账户 ID、广告系列 ID 自动查找名称。待补名称表示尚无匹配主档；不是无广告归因。此列不参与同步写入。'}]}], 'fields':'note'}})
        if not apply:
            print(json.dumps({'plan':plan,'request_count':len(requests)},ensure_ascii=False)); return
        service.api('POST', service.table('广告'), ':batchUpdate', json={'requests':requests})
        for name in plan:
            after, _ = service.read(service.table(name))
            if after != originals[name]:
                raise RuntimeError(f'Original record data changed: {name}; inspect before further changes')
            print(name, 'REORDER_VERIFIED', len(after), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
