"""Read-only migration export. Run in company Cloud Shell; never commit output.

Uses the existing Secret Manager token. Emits counts/field names, never values.
An incomplete export fails rather than being treated as an empty source table.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import quote

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--secret', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    destination = Path(args.output).resolve()
    repo = Path(__file__).resolve().parents[1]
    if destination == repo or repo in destination.parents:
        raise ValueError('Export must be outside the public repository')
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    token = subprocess.check_output(['gcloud', 'secrets', 'versions', 'access',
                                    'latest', '--secret=' + args.secret], text=True).strip()
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + token
    schema = json.loads((repo / 'schema/airtable-schema.json').read_text())
    report = []
    for table in schema['tables']:
        records, offset = [], None
        while True:
            params = {'pageSize': 100}
            if offset:
                params['offset'] = offset
            response = session.get('https://api.airtable.com/v0/' + args.base + '/' +
                                   quote(table['name'], safe=''), params=params, timeout=60)
            response.raise_for_status()
            page = response.json()
            records.extend(page['records'])
            offset = page.get('offset')
            time.sleep(0.35)
            if not offset:
                break
        if len({r['id'] for r in records}) != len(records):
            raise ValueError('Duplicate source record IDs in ' + table['name'])
        extras = sorted({field for r in records for field in r['fields']} -
                        {field['name'] for field in table['fields']})
        path = destination / (table['name'] + '.json')
        with path.open('x', encoding='utf-8') as stream:
            json.dump(records, stream, ensure_ascii=False)
        os.chmod(path, 0o600)
        result = {'table': table['name'], 'records': len(records), 'extra_fields': extras}
        report.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    (destination / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False))
    print('EXPORT_COMPLETE. Source data unchanged. Review extra_fields before import.')


if __name__ == '__main__':
    main()
