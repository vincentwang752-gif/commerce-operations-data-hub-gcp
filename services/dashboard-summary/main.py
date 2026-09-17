"""Read source Sheets and atomically replace only owned dashboard output tabs."""
import os
from datetime import datetime, timezone

import google.auth
from google.auth.transport.requests import AuthorizedSession
from flask import Flask, jsonify
from metrics import summarize

app = Flask(__name__)
SOURCE = os.environ.get("SOURCE_SPREADSHEET_ID", "")
DEST = os.environ.get("SUMMARY_SPREADSHEET_ID", "")
NAMES = ["订单", "红人", "归因触点", "客户生命周期", "GA4运营与用户行为"]
REQUIRED = {
    "订单": {"订单 ID", "下单时间", "币种", "付款状态", "订单收入", "退款金额", "是否取消"},
    "红人": {"红人名称"},
    "归因触点": {"订单", "红人", "是否最终触点", "归因方式"},
    "客户生命周期": {"售前问卷已完成", "使用后问卷已完成", "延保审核状态", "延保天数"},
    "GA4运营与用户行为": {"日期", "分析粒度", "会话数", "互动会话数", "平均互动时长（秒）", "GA4购买事件数"},
}
API = "https://sheets.googleapis.com/v4/spreadsheets/"


def col(n):
    result = ""
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def call(session, method, url, **kwargs):
    response = session.request(method, url, timeout=90, **kwargs)
    response.raise_for_status()
    return response.json()


def refresh(session):
    if not SOURCE or not DEST or SOURCE == DEST:
        raise ValueError("Distinct source and summary spreadsheet IDs required")
    metadata = call(session, "GET", API + SOURCE, params={"fields": "sheets(properties)"})
    props = {s["properties"]["title"]: s["properties"] for s in metadata["sheets"]}
    ranges = []
    # Read at most 50,000 cells per range, without a fixed 1000-row truncation.
    for name in NAMES:
        p = props[name]["gridProperties"]
        columns = p["columnCount"]
        step = max(1, 49000 // columns)
        for start in range(1, p["rowCount"] + 1, step):
            ranges.append((name, f"'{name}'!A{start}:{col(columns)}{min(start+step-1,p['rowCount'])}"))
    tables, headers = {n: [] for n in NAMES}, {}
    for begin in range(0, len(ranges), 10):
        batch = ranges[begin:begin+10]
        result = call(session, "GET", API + SOURCE + "/values:batchGet", params={
            "ranges": [r for _, r in batch], "valueRenderOption": "UNFORMATTED_VALUE"})
        if len(result.get("valueRanges", [])) != len(batch):
            raise ValueError("Incomplete source read")
        for (name, _), value in zip(batch, result["valueRanges"]):
            rows = value.get("values", [])
            if name not in headers:
                if not rows or not rows[0] or rows[0][0] != "记录 ID":
                    raise ValueError("Unexpected source header")
                headers[name], rows = rows[0], rows[1:]
                if not REQUIRED[name].issubset(headers[name]):
                    raise ValueError("Required source columns missing: " + name)
            tables[name].extend(dict(zip(headers[name], row)) for row in rows if any(x != "" for x in row))
    outputs = summarize(tables)
    stamp = datetime.now(timezone.utc).isoformat()
    outputs["数据说明"].extend([["同步", "最近成功汇总时间UTC", stamp]] +
                               [[name, "本次读取原始记录数", len(tables[name])] for name in NAMES])
    dest = call(session, "GET", API + DEST, params={"fields": "sheets(properties)"})
    dp = {s["properties"]["title"]: s["properties"] for s in dest["sheets"]}
    requests = []
    existing_ids = {p["sheetId"] for p in dp.values()}
    for name, rows in outputs.items():
        width = len(rows[0])
        if name not in dp:
            sheet_id = max(existing_ids | {100}) + 1
            existing_ids.add(sheet_id)
            requests.append({"addSheet": {"properties": {"sheetId": sheet_id, "title": name,
                "gridProperties": {"rowCount": max(1000, len(rows)), "columnCount": width,
                                   "frozenRowCount": 1}}}})
        else:
            sheet_id = dp[name]["sheetId"]
            grid = dp[name]["gridProperties"]
            if grid["rowCount"] < len(rows) or grid["columnCount"] < width:
                requests.append({"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                    "gridProperties": {"rowCount": max(len(rows), grid["rowCount"]),
                                       "columnCount": max(width, grid["columnCount"])}},
                    "fields": "gridProperties.rowCount,gridProperties.columnCount"}})
        def cell(value):
            if value == "" or value is None:
                return {}
            return {"userEnteredValue": {"numberValue" if isinstance(value, (int, float)) else "stringValue": value}}
        # A bounded range clears obsolete old output rows atomically with new rows.
        height = max(len(rows), dp.get(name, {}).get("gridProperties", {}).get("rowCount", len(rows)))
        requests.append({"updateCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0,
            "endRowIndex": height, "startColumnIndex": 0, "endColumnIndex": width},
            "rows": [{"values": [cell(v) for v in row]} for row in rows] +
                    [{"values": [{} for _ in range(width)]} for _ in range(height-len(rows))],
            "fields": "userEnteredValue"}})
        requests.append({"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 0, "endColumnIndex": width}, "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": .93, "green": .94, "blue": .95},
                "textFormat": {"bold": True}, "wrapStrategy": "WRAP"}}, "fields": "userEnteredFormat"}})
        requests.append({"updateDimensionProperties": {"range": {"sheetId": sheet_id,
            "dimension": "COLUMNS", "startIndex": 0, "endIndex": width},
            "properties": {"pixelSize": 180}, "fields": "pixelSize"}})
    call(session, "POST", API + DEST + ":batchUpdate", json={"requests": requests})
    # Read back every written value before declaring success; never log records.
    verified = call(session, "GET", API + DEST + "/values:batchGet", params={
        "ranges": [f"'{n}'!A1:{col(len(r[0]))}{len(r)}" for n, r in outputs.items()],
        "valueRenderOption": "UNFORMATTED_VALUE"})
    if len(verified.get("valueRanges", [])) != len(outputs):
        raise ValueError("Incomplete summary readback")
    for (name, expected), actual in zip(outputs.items(), verified["valueRanges"]):
        def padded(rows):
            return [row + [""] * (len(expected[0])-len(row)) for row in rows]
        if padded(actual.get("values", [])) != padded(expected):
            raise ValueError("Summary readback mismatch: " + name)
    return {"updated_at": stamp, "rows": {n: len(r)-1 for n, r in outputs.items()}}


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/")
def run():
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        with AuthorizedSession(credentials) as session:
            return jsonify(refresh(session))
    except Exception as exc:
        # Do not leak source URLs, credentials or source records in error logs.
        app.logger.error("Dashboard refresh failed: %s", type(exc).__name__)
        return jsonify(error="summary_refresh_failed", error_type=type(exc).__name__), 500
