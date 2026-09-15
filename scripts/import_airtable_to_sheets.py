"""Import a private backup into a pre-created Sheet, preserving record IDs.

Run in company Cloud Shell. No customer values or tokens are logged.
Refuses any existing destination row that differs from the backup.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
from urllib.parse import quote
import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--backup', required=True)
    p.add_argument('--spreadsheet', required=True)
    p.add_argument('--service-account', required=True)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    user_token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
    r = requests.post('https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/' +
                      a.service_account + ':generateAccessToken',
                      headers={'Authorization': 'Bearer ' + user_token},
                      json={'scope': ['https://www.googleapis.com/auth/spreadsheets'], 'lifetime': '3600s'}, timeout=60)
    r.raise_for_status()
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + r.json()['accessToken']
    url = 'https://sheets.googleapis.com/v4/spreadsheets/' + a.spreadsheet

    def call(method, path='', **kwargs):
        for attempt in range(6):
            res = session.request(method, url + path, timeout=90, **kwargs)
            if res.status_code not in (429, 500, 502, 503, 504):
                res.raise_for_status()
                return res.json()
            time.sleep(2 ** attempt)
        raise RuntimeError('Sheets unavailable; rerun safely after recovery')

    schema = json.loads((Path(__file__).resolve().parents[1] / 'schema/airtable-schema.json').read_text())
    meta = call('GET', params={'fields': 'sheets.properties'})
    sheets = {s['properties']['title']: s['properties'] for s in meta['sheets']}
    plans = []
    for table in schema['tables']:
        name = table['name']
        prop = sheets[name]
        headers = ['记录 ID'] + [f['name'] for f in table['fields']]
        records = json.loads((Path(a.backup) / (name + '.json')).read_text())
        if len({r['id'] for r in records}) != len(records):
            raise ValueError('Duplicate source IDs: ' + name)
        def encode(v):
            return json.dumps(v, ensure_ascii=False, separators=(',', ':')) if isinstance(v, (list, dict)) else ('' if v is None else v)
        rows = [[r['id']] + [encode(r['fields'].get(f)) for f in headers[1:]] for r in records]
        if len(rows) + 1 > prop['gridProperties']['rowCount']:
            raise ValueError('Insufficient destination rows: ' + name)
        end = ''
        n = len(headers)
        while n:
            n, rem = divmod(n - 1, 26)
            end = chr(65 + rem) + end
        rng = "'" + name.replace("'", "''") + "'!A1:" + end + str(prop['gridProperties']['rowCount'])
        live = call('GET', params={'ranges': rng, 'fields': 'sheets.data.rowData.values(userEnteredValue,dataValidation)'})
        actual = []
        for row in live['sheets'][0].get('data', [{}])[0].get('rowData', []):
            values = []
            for cell in row.get('values', []):
                if cell.get('dataValidation') or 'formulaValue' in cell.get('userEnteredValue', {}):
                    raise ValueError('Unexpected validation/formula: ' + name)
                values.append(next(iter(cell.get('userEnteredValue', {}).values()), ''))
            actual.append(values + [''] * (len(headers) - len(values)))
        while actual and not any(v != '' for v in actual[-1]):
            actual.pop()
        if not actual or actual[0] != headers:
            raise ValueError('Header mismatch: ' + name)
        if actual[1:] != rows[:len(actual)-1]:
            raise ValueError('Destination differs; no overwrite allowed: ' + name)
        plans.append((name, end, rows, len(actual)-1))
        print(json.dumps({'table': name, 'source': len(rows), 'existing': len(actual)-1}, ensure_ascii=False), flush=True)
    if not a.apply:
        print('PREFLIGHT_OK; no writes')
        return
    for name, end, rows, existing in plans:
        for start in range(existing, len(rows), 250):
            chunk = rows[start:start+250]
            rng = "'" + name.replace("'", "''") + "'!A" + str(start+2) + ':' + end + str(start+1+len(chunk))
            call('POST', '/values:batchUpdate', json={'valueInputOption': 'RAW', 'data': [{'range': rng, 'values': chunk}]})
            time.sleep(1.1)
        if rows:
            rng = "'" + name.replace("'", "''") + "'!A2:" + end + str(len(rows)+1)
            got = call('GET', '/values/' + quote(rng, safe=''), params={'valueRenderOption': 'UNFORMATTED_VALUE'}).get('values', [])
            got = [r + [''] * (len(rows[0])-len(r)) for r in got]
            if got != rows:
                raise ValueError('Verification failed: ' + name)
        print(json.dumps({'verified': name, 'records': len(rows)}, ensure_ascii=False), flush=True)
    print('IMPORT_VERIFIED. No source changes; no emails triggered.')


if __name__ == '__main__':
    main()
