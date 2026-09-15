"""Build deployment config locally in Cloud Shell; never commit output."""
import argparse
import json
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--spreadsheet', required=True)
p.add_argument('--output', required=True)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
schema = json.loads((root / 'schema/airtable-schema.json').read_text())
keys = {'客户':['客户唯一键'], '订单':['订单 ID'], '红人':['红人唯一键'],
        '归因触点':['触点唯一键'], '客户生命周期':['客户'],
        'GA4运营与用户行为':['汇总唯一键'], '广告每日表现':['表现唯一键']}
mapping = {'AIRTABLE_ORDERS_TABLE':'订单', 'AIRTABLE_CUSTOMERS_TABLE':'客户',
           'AIRTABLE_CREATORS_TABLE':'红人', 'AIRTABLE_TOUCHPOINTS_TABLE':'归因触点',
           'AIRTABLE_LIFECYCLE_TABLE':'客户生命周期', 'AIRTABLE_TABLE_ID':'GA4运营与用户行为'}
ids = {}
for name in ['shopify-airtable-sync', 's1-voc-sync', 'ga4-airtable-sync']:
    service = json.loads(subprocess.check_output(['gcloud','run','services','describe',name,
                                                 '--region=asia-east1','--format=json'], text=True))
    for env in service['spec']['template']['spec']['containers'][0].get('env', []):
        if env['name'] in mapping and env.get('value', '').startswith('tbl'):
            ids[mapping[env['name']]] = env['value']
for table in schema['tables']:
    table['spreadsheet_id'] = a.spreadsheet
    table['key_fields'] = keys.get(table['name'], [])
    if table['name'] in ids:
        table['id'] = ids[table['name']]
output = Path(a.output)
with output.open('x') as f:
    json.dump(schema, f, ensure_ascii=False)
output.chmod(0o600)
print('CONFIG_CREATED; no secrets included')
