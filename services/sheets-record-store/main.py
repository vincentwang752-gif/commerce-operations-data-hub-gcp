"""Private, serialized Google Sheets record gateway for the commerce services.

Deploy with one instance, one Gunicorn worker and concurrency=1. Record IDs
survive migration; writes change only supplied fields. Cloud Run IAM protects
the endpoint. No Airtable credentials are needed by this service.
"""
import hashlib
import json
import os
import threading
from copy import deepcopy
from urllib.parse import quote

import google.auth
from google.auth.transport.requests import AuthorizedSession
from flask import Flask, jsonify, request
from formula import matches
from writer_lock import writer_lock

app = Flask(__name__)
lock = threading.Lock()
CONFIG_PATH = os.getenv('SHEETS_CONFIG_PATH', 'tables.json')
RECORD_ID = '记录 ID'
# Optional, formula-owned display columns. Never returned or written as records.
DISPLAY_FIELDS = {'广告': {'广告系列名称'}, '广告每日表现': {'广告系列名称'}}


def column(index):
    result = ''
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def encode(value):
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value


def decode(value, kind):
    if value == '' or value is None:
        return None
    if kind in ('multipleRecordLinks', 'multipleSelects', 'multipleAttachments', 'lookup', 'rollup') and isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            if kind in ('multipleRecordLinks', 'multipleAttachments'):
                raise ValueError('Invalid JSON in structured field')
    return value


class SheetsStore:
    def __init__(self, config, session):
        self.config = config
        self.session = session

    def table(self, name):
        for table in self.config['tables']:
            if name in (table['name'], table.get('id')):
                return table
        raise ValueError('Unknown table')

    def api(self, method, table, suffix, **kwargs):
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{table['spreadsheet_id']}{suffix}"
        response = self.session.request(method, url, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()

    def read(self, table, include_layout=False):
        # The explicit row limit bounds reads and stops a growing table silently
        # dropping records. A full range must be expanded before more writes.
        required_width = len(table['fields']) + 1
        limit = table.get('row_limit', 50000)
        grid = self.grid(table)
        if grid['columnCount'] < required_width:
            raise ValueError('Sheet columns missing; restore schema before syncing')
        display_fields = DISPLAY_FIELDS.get(table['name'], set())
        width = min(grid['columnCount'], required_width + len(display_fields))
        tab = "'" + table['name'].replace("'", "''") + "'"
        address = f"{tab}!A1:{column(width)}{min(limit, grid['rowCount'])}"
        values = self.api('GET', table, '/values/' + quote(address, safe=''),
                          params={'valueRenderOption':'UNFORMATTED_VALUE'}).get('values', [])
        expected = [RECORD_ID] + [f['name'] for f in table['fields']]
        if (not values or len(set(values[0])) != len(values[0])
                or not set(expected).issubset(values[0])
                or not set(values[0]).issubset(set(expected) | display_fields)):
            raise ValueError('Sheet headers changed; restore headers before syncing')
        layout = {name:index + 1 for index, name in enumerate(values[0])}
        if len(values) >= limit:
            raise ValueError('Sheet row limit reached; expand configured range')
        rows = []
        seen = set()
        for row_number, cells in enumerate(values[1:], 2):
            if not any(cell != '' for cell in cells):
                continue
            id_index = layout[RECORD_ID] - 1
            record_id = str(cells[id_index]) if id_index < len(cells) else ''
            if not record_id or record_id in seen:
                raise ValueError('Missing or duplicate record ID')
            seen.add(record_id)
            fields = {}
            for field in table['fields']:
                index = layout[field['name']] - 1
                value = decode(cells[index] if index < len(cells) else '', field['type'])
                if value is not None:
                    fields[field['name']] = value
            rows.append({'id':record_id, 'fields':fields, '_row':row_number})
        result = (rows, len(values) + 1)
        return result + (layout,) if include_layout else result

    def grid(self, table):
        metadata = self.api('GET', table, '', params={'fields':'sheets.properties'})
        for sheet in metadata.get('sheets', []):
            properties = sheet['properties']
            if properties['title'] == table['name']:
                return dict(properties['gridProperties'], sheetId=properties['sheetId'])
        raise ValueError('Configured sheet not found')

    def ensure_rows(self, table, required):
        grid = self.grid(table)
        if required > grid['rowCount']:
            expanded = min(table.get('row_limit', 50000), required + 500)
            self.api('POST', table, ':batchUpdate', json={'requests':[{
                'updateSheetProperties':{'properties':{'sheetId':grid['sheetId'],
                'gridProperties':{'rowCount':expanded}}, 'fields':'gridProperties.rowCount'}}]})

    def list_records(self, name, params):
        allowed = {'filterByFormula', 'offset', 'maxRecords', 'pageSize'}
        if any(k not in allowed and not k.startswith('fields[') for k in params):
            raise ValueError('Unsupported query option')
        table = self.table(name)
        rows, _ = self.read(table)
        requested = [value for key, value in params.items() if key.startswith('fields[')]
        # Airtable's inverse links are computed explicitly in Sheets.
        if table['name'] == '客户' and '关联生命周期' in requested:
            lifecycle, _ = self.read(self.table('客户生命周期'))
            for row in rows:
                row['fields']['关联生命周期'] = [r['id'] for r in lifecycle if row['id'] in r['fields'].get('客户', [])]
        selected = [r for r in rows if matches(params.get('filterByFormula', ''), r['fields'])]
        offset = int(params.get('offset', 0))
        maximum = int(params.get('maxRecords', len(selected)))
        size = min(int(params.get('pageSize', 100)), 100)
        if offset < 0 or maximum < 0 or size < 1:
            raise ValueError('Invalid pagination')
        selected = selected[:maximum]
        page = selected[offset:offset + size]
        result = {'records':[{'id':r['id'], 'fields':{k:v for k,v in r['fields'].items() if not requested or k in requested}} for r in page]}
        if offset + size < len(selected):
            result['offset'] = str(offset + size)
        return result

    def write_records(self, name, payload, record_id=None):
        table = self.table(name)
        rows, next_row, layout = self.read(table, include_layout=True)
        rows = deepcopy(rows)
        by_id = {r['id']:r for r in rows}
        schema = {f['name']:layout[f['name']] for f in table['fields']}
        incoming = payload.get('records') if 'records' in payload else [{'id':record_id, 'fields':payload.get('fields', {})}]
        merge_keys = payload.get('performUpsert', {}).get('fieldsToMergeOn') or table.get('key_fields', [])
        updates, results = [], []
        tab = "'" + table['name'].replace("'", "''") + "'"
        for item in incoming:
            fields = dict(item.get('fields', {}))
            if not fields or any(key not in schema for key in fields):
                raise ValueError('Empty write or unknown field')
            target = by_id.get(item.get('id'))
            if item.get('id') and not target:
                raise ValueError('Record ID not found')
            if not target:
                if not merge_keys or any(fields.get(key) in (None, '', []) for key in merge_keys):
                    raise ValueError('Stable business key is required')
                found = [r for r in rows if all(r['fields'].get(key) == fields[key] for key in merge_keys)]
                if len(found) > 1:
                    raise ValueError('Ambiguous duplicate business key')
                target = found[0] if found else None
            if target is None:
                stable = json.dumps([table['name']] + [fields[k] for k in merge_keys], ensure_ascii=False, sort_keys=True)
                target = {'id':'gs_' + hashlib.sha256(stable.encode()).hexdigest()[:24], 'fields':{}, '_row':next_row}
                if next_row >= table.get('row_limit', 50000):
                    raise ValueError('Sheet row limit reached')
                next_row += 1
                rows.append(target)
                by_id[target['id']] = target
                updates.append({'range':f"{tab}!{column(layout[RECORD_ID])}{target['_row']}", 'values':[[target['id']]]})
                for field in table['fields']:
                    if field['type'] == 'autoNumber':
                        key = field['name']
                        fields[key] = max((int(r['fields'].get(key, 0) or 0) for r in rows), default=0) + 1
            if table['name'] == '客户生命周期':
                prior = target['fields']
                if prior.get('使用后问卷已完成'):
                    fields['使用后问卷已完成'] = True
                    fields['延保天数'] = max(prior.get('延保天数', 0), fields.get('延保天数', 0))
            for key, value in fields.items():
                updates.append({'range':f"{tab}!{column(schema[key])}{target['_row']}", 'values':[[encode(value) if value is not None else '']]})
            target['fields'].update(fields)
            results.append({'id':target['id'], 'fields':dict(target['fields'])})
        # One Google API batch request applies all cell changes atomically.
        if updates:
            self.ensure_rows(table, next_row - 1)
            self.api('POST', table, '/values:batchUpdate', json={'valueInputOption':'RAW', 'data':updates})
        return {'records':results} if 'records' in payload else results[0]


_store = None


def store():
    global _store
    if _store is None:
        with open(CONFIG_PATH, encoding='utf-8') as source:
            config = json.load(source)
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/spreadsheets'])
        _store = SheetsStore(config, AuthorizedSession(credentials))
    return _store


@app.get('/health')
def health():
    return jsonify({'ok':True, 'storage':'google-sheets'})


@app.post('/records')
def records():
    data = request.get_json(silent=True) or {}
    try:
        with lock, writer_lock():
            if data.get('method') == 'GET':
                result = store().list_records(data['table'], data.get('params', {}))
            elif data.get('method') in ('POST', 'PATCH'):
                result = store().write_records(data['table'], data.get('payload', {}), data.get('record_id'))
            else:
                return jsonify({'error':'Unsupported operation'}), 400
        return jsonify(result)
    except (ValueError, KeyError) as exc:
        return jsonify({'error':str(exc)}), 422
    except Exception:
        app.logger.exception('Sheets storage request failed')
        return jsonify({'error':'Sheets write/read failed; retry with the same business key'}), 502
