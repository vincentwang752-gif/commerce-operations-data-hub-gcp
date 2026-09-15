"""Read all tables and optionally rewrite an unchanged key; no emails."""
import argparse
import subprocess
import requests

p = argparse.ArgumentParser()
p.add_argument('--url', required=True)
p.add_argument('--verify-write', action='store_true')
a = p.parse_args()
t = subprocess.check_output(['gcloud','auth','print-identity-token'], text=True).strip()
s = requests.Session()
s.headers['Authorization'] = 'Bearer ' + t

def call(data):
    r = s.post(a.url.rstrip('/') + '/records', json=data, timeout=110)
    if r.status_code != 200:
        raise RuntimeError('Gateway check failed: HTTP ' + str(r.status_code))
    return r.json()

for name in ['客户','订单','红人','内容资产','归因触点','客户生命周期','红人合作','广告系列','广告','广告每日表现','GA4运营与用户行为']:
    j = call({'method':'GET','table':name,'params':{'maxRecords':1}})
    print(name, 'READ_OK', len(j['records']), flush=True)
    if a.verify_write and name == '客户':
        record = j['records'][0]
        key = record['fields']['客户唯一键']
        updated = call({'method':'PATCH','table':name,'record_id':record['id'],
                        'payload':{'fields':{'客户唯一键':key}}})
        assert updated['id'] == record['id']
        assert updated['fields']['客户唯一键'] == key
        again = call({'method':'GET','table':name,'params':{'maxRecords':1}})
        assert again == j
        print('UNCHANGED_KEY_WRITE_VERIFIED', flush=True)
print('GATEWAY_CHECK_OK')
