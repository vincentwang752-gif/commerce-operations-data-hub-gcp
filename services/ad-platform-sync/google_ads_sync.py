"""Google Ads SELECT reporting to the existing private Sheets record gateway.

Campaign-day is the sole spend grain (including Performance Max). No ad-day
spend is emitted. Credentials are short-lived runtime tokens; no key files.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo


def http(url, token=None, payload=None, headers=None):
    headers = dict(headers or {})
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    for attempt in range(4):
        req = urllib.request.Request(url, data=None if payload is None else
                                     json.dumps(payload).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=110) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 3:
                # Do not log credential headers or business response bodies.
                raise RuntimeError(f'HTTP {exc.code} from {req.host}') from None
            time.sleep(2 ** attempt)


def runtime_token():
    return http('http://metadata.google.internal/computeMetadata/v1/instance/'
                'service-accounts/default/token', headers={'Metadata-Flavor':'Google'})['access_token']


def ads_token():
    target = os.environ['GOOGLE_ADS_SERVICE_ACCOUNT']
    if not re.fullmatch(r'[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com', target):
        raise ValueError('Invalid reporting service account')
    return http('https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/'
                + target + ':generateAccessToken', runtime_token(),
                {'scope':['https://www.googleapis.com/auth/adwords'],
                 'lifetime':'3600s'})['accessToken']


def query(token, cid, sql):
    if not sql.startswith('SELECT ') or ';' in sql:
        raise ValueError('Only single SELECT statements allowed')
    result = http(f'https://googleads.googleapis.com/v25/customers/{cid}/googleAds:searchStream',
                  token, {'query':sql})
    return [row for batch in result for row in batch.get('results', [])]


def money(micros):
    return float(Decimal(str(micros or 0)) / Decimal(1000000))


def account_config():
    accounts = json.loads(os.environ['GOOGLE_ADS_ACCOUNTS_JSON'])
    seen = set()
    if not accounts:
        raise ValueError('No accounts configured')
    for account in accounts:
        cid = account['customer_id']
        if not re.fullmatch(r'\d{10}', cid) or cid in seen:
            raise ValueError('Invalid or duplicate account ID')
        if account['account_type'] not in ('自投', '代投', '品牌自投', '代理商代投'):
            raise ValueError('Unknown account type')
        seen.add(cid)
    return accounts


class Store:
    def __init__(self):
        self.url = os.environ['SHEETS_STORE_URL'].rstrip('/')
        if not self.url.startswith('https://') or not self.url.endswith('.run.app'):
            raise ValueError('Private Cloud Run store URL required')

    def call(self, payload):
        from urllib.parse import urlencode
        url = ('http://metadata.google.internal/computeMetadata/v1/instance/'
               'service-accounts/default/identity?' + urlencode({'audience':self.url}))
        req = urllib.request.Request(url, headers={'Metadata-Flavor':'Google'})
        with urllib.request.urlopen(req, timeout=20) as response:
            token = response.read().decode()
        return http(self.url + '/records', token, payload)

    def upsert(self, table, key, fields):
        if not fields:
            return []
        result = []
        for start in range(0, len(fields), 30):
            chunk = fields[start:start + 30]
            reply = self.call({'method':'PATCH', 'table':table, 'payload':{
                'performUpsert':{'fieldsToMergeOn':[key]},
                'records':[{'fields':f} for f in chunk]}})['records']
            if len(reply) != len(chunk):
                raise RuntimeError('Incomplete storage response')
            for sent, saved in zip(chunk, reply):
                if any(saved['fields'].get(k) != v for k, v in sent.items()):
                    raise RuntimeError('Stored fields differ from submitted fields')
            result.extend(reply)
        return result

    def read(self, table, formula):
        records, offset = [], None
        while True:
            params = {'filterByFormula':formula, 'pageSize':100}
            if offset:
                params['offset'] = offset
            reply = self.call({'method':'GET', 'table':table, 'params':params})
            records.extend(reply.get('records', []))
            offset = reply.get('offset')
            if not offset:
                return records

    def check_day(self, cid, day):
        formula = f"AND({{账户 ID}}='{cid}',{{日期}}='{day}',{{平台}}='Google Ads')"
        rows = self.read('广告每日表现', formula)
        keys = [r['fields'].get('表现唯一键', '') for r in rows]
        prefix = f'{day}|google_ads|{cid}|campaign|'
        if len(keys) != len(set(keys)) or any(not k.startswith(prefix) for k in keys):
            raise ValueError('Duplicate or legacy ad-day rows: stop to prevent double counting')
        return rows


def extract(token, account, day):
    cid = account['customer_id']
    metadata = query(token, cid, 'SELECT customer.id, customer.currency_code, customer.time_zone FROM customer')
    if len(metadata) != 1 or metadata[0]['customer']['id'] != cid:
        raise ValueError('Account identity mismatch')
    customer = metadata[0]['customer']
    campaigns = query(token, cid, 'SELECT campaign.id, campaign.name, campaign.status, '
                      'campaign.advertising_channel_type FROM campaign')
    ads = query(token, cid, 'SELECT campaign.id, ad_group.id, ad_group.name, '
                'ad_group_ad.ad.id, ad_group_ad.ad.name, ad_group_ad.ad.final_urls, '
                'ad_group_ad.status FROM ad_group_ad')
    daily = query(token, cid, 'SELECT campaign.id, metrics.impressions, metrics.clicks, '
                  f"metrics.cost_micros FROM campaign WHERE segments.date = '{day}'")
    purchases = query(token, cid, 'SELECT campaign.id, segments.conversion_action_category, metrics.conversions, '
                      'metrics.conversions_value FROM campaign '
                      f"WHERE segments.date = '{day}' AND segments.conversion_action_category = 'PURCHASE'")
    return customer, campaigns, ads, daily, purchases


def transform(account, day, extracted, synced_at):
    customer, campaigns, ads, daily, purchases = extracted
    cid = account['customer_id']
    common = {'平台':'Google Ads', '账户 ID':cid, '账户类型':account['account_type'],
              '最后同步时间':synced_at}
    campaign_rows = [dict(common, **{'广告系列唯一键':f'google_ads|{cid}|{r["campaign"]["id"]}',
        '广告系列 ID':r['campaign']['id'], '广告系列名称':r['campaign']['name'],
        '状态':r['campaign']['status'], '币种':customer['currencyCode']}) for r in campaigns]
    ad_rows = []
    for row in ads:
        ad = row['adGroupAd']['ad']
        ad_rows.append(dict(common, **{'广告唯一键':f'google_ads|{cid}|{row["adGroup"]["id"]}|{ad["id"]}',
            '广告系列 ID':row['campaign']['id'], '广告组 ID':row['adGroup']['id'],
            '广告组名称':row['adGroup']['name'], '广告 ID':ad['id'],
            '广告名称':ad.get('name', ''), '状态':row['adGroupAd']['status'],
            '落地页链接':next(iter(ad.get('finalUrls', [])), '')}))
    totals = {}
    for row in purchases:
        target = totals.setdefault(row['campaign']['id'], [Decimal(0), Decimal(0)])
        target[0] += Decimal(str(row.get('metrics', {}).get('conversions', 0)))
        target[1] += Decimal(str(row.get('metrics', {}).get('conversionsValue', 0)))
    daily_rows = []
    present = {r['campaign']['id'] for r in daily}
    daily = list(daily) + [{'campaign':{'id':k}} for k in totals if k not in present]
    for row in daily:
        campaign_id = row['campaign']['id']
        metrics = row.get('metrics', {})
        count, revenue = totals.get(campaign_id, (0, 0))
        impressions = int(metrics.get('impressions', 0))
        clicks = int(metrics.get('clicks', 0))
        cost = money(metrics.get('costMicros', 0))
        daily_rows.append(dict(common, **{
            '表现唯一键':f'{day}|google_ads|{cid}|campaign|{campaign_id}',
            '日期':day, '广告系列 ID':campaign_id, '币种':customer['currencyCode'],
            '曝光量':impressions, '点击数':clicks,
            '广告花费':cost, 'CTR':clicks/impressions if impressions else None,
            'CPC':cost/clicks if clicks else None,
            'CPM':cost*1000/impressions if impressions else None,
            '平台 ROAS':float(revenue)/cost if cost else None,
            '平台购买数':float(count), '平台归因收入':float(revenue)}))
    return campaign_rows, ad_rows, daily_rows


def main():
    if os.environ.get('READ_ONLY') != 'true':
        raise ValueError('READ_ONLY=true must be explicitly configured')
    now = datetime.now(timezone.utc)
    day = os.getenv('SYNC_DATE') or (now.astimezone(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=4)).isoformat()
    parsed = datetime.strptime(day, '%Y-%m-%d').date()
    if parsed > now.astimezone(ZoneInfo('Asia/Shanghai')).date() - timedelta(days=4):
        raise ValueError('Only T-4 or older dates are allowed')
    token = ads_token()
    # Read both accounts fully before changing any destination records.
    batches = [(a, extract(token, a, day)) for a in account_config()]
    if os.getenv('WRITE_ENABLED') != 'true':
        for account, extracted in batches:
            rows = transform(account, day, extracted, now.isoformat())
            print(json.dumps({'status':'READ_VALIDATED', 'date':day,
                              'account_type':account['account_type'],
                              'counts':[len(r) for r in rows],
                              'cost':sum(r['广告花费'] for r in rows[2])}, ensure_ascii=False))
        return
    store = Store()
    for account, _ in batches:
        store.check_day(account['customer_id'], day)
    for account, extracted in batches:
        campaigns, ads, daily = transform(account, day, extracted, now.isoformat())
        saved = store.upsert('广告系列', '广告系列唯一键', campaigns)
        links = {r['fields']['广告系列 ID']:r['id'] for r in saved}
        for row in ads + daily:
            row['广告系列'] = [links[row['广告系列 ID']]]
        store.upsert('广告', '广告唯一键', ads)
        store.upsert('广告每日表现', '表现唯一键', daily)
        verified = {r['fields']['表现唯一键']:r['fields']
                    for r in store.check_day(account['customer_id'], day)}
        for row in daily:
            saved_row = verified.get(row['表现唯一键'], {})
            for field in ('曝光量', '点击数', '广告花费', '平台购买数', '平台归因收入'):
                if Decimal(str(saved_row.get(field))) != Decimal(str(row[field])):
                    raise RuntimeError('Fresh read verification failed: ' + field)
        print(json.dumps({'status':'SYNCED', 'date':day, 'account_type':account['account_type'],
                          'campaigns':len(campaigns), 'ads':len(ads), 'campaign_days':len(daily),
                          'currency':extracted[0]['currencyCode'], 'timezone':extracted[0]['timeZone']},
                         ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
