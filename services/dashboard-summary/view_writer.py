"""Write only explicitly owned, generated business tabs in the source workbook."""
from business_views import OWNER, VIEW_NAMES


def requests_for_views(outputs, props):
    requests, ids = [], {p["sheetId"] for p in props.values()}
    for index, name in enumerate(VIEW_NAMES):
        rows = outputs[name]
        width = len(rows[0])
        existing = props.get(name)
        if existing:
            # The caller must separately verify sheet developerMetadata ownership.
            sid = existing["sheetId"]
            height = max(len(rows), existing["gridProperties"]["rowCount"])
        else:
            sid = max(ids | {100}) + 1
            ids.add(sid)
            height = max(1000, len(rows))
            requests.append({"addSheet": {"properties": {"sheetId": sid, "title": name,
                "gridProperties": {"rowCount": height, "columnCount": width}}}})
            requests.append({"createDeveloperMetadata": {"developerMetadata": {
                "metadataKey": "generated_view_owner", "metadataValue": OWNER,
                "location": {"sheetId": sid}, "visibility": "DOCUMENT"}}})
        requests.append({"updateSheetProperties": {"properties": {"sheetId": sid, "index": index,
            "gridProperties": {"rowCount": height, "columnCount": max(width, (existing or {}).get("gridProperties", {}).get("columnCount", 0)),
                               "frozenRowCount": 1, "frozenColumnCount": 2}},
            "fields": "index,gridProperties"}})
        def cell(v):
            if v is None or v == "": return {}
            return {"userEnteredValue": {"numberValue" if isinstance(v, (int, float)) else "stringValue": v}}
        requests.append({"updateCells": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": height,
            "startColumnIndex": 0, "endColumnIndex": width}, "rows": [{"values": [cell(v) for v in r]} for r in rows], "fields": "userEnteredValue"}})
        requests.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"backgroundColor": {"red": .93, "green": .94, "blue": .95},
                "textFormat": {"bold": True}, "wrapStrategy": "WRAP"},
                "note": "自动关联业务视图，请勿在此手工维护。每天随汇总任务更新；原始表保留。金额只代表已同步范围，含税运费减退款，空白历史退款按0。问卷完成不等于延保已审核；归因是现有证据，不是完整用户旅程。"},
            "fields": "userEnteredFormat,note"}})
        requests.append({"setBasicFilter": {"filter": {"range": {"sheetId": sid, "startRowIndex": 0,
            "endRowIndex": len(rows), "startColumnIndex": 0, "endColumnIndex": width}}}})
        requests.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1},
            "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP"}}, "fields": "userEnteredFormat.wrapStrategy"}})
        requests.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": width},
            "properties": {"pixelSize": 160}, "fields": "pixelSize"}})
        for col, title in enumerate(rows[0]):
            if title == "邮箱" or "下一步" in title or "分币种" in title or "缺口" in title:
                requests.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": col, "endIndex": col+1},
                    "properties": {"pixelSize": 250}, "fields": "pixelSize"}})
        if name == VIEW_NAMES[1]:
            requests.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": 7, "endColumnIndex": 8},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}}, "fields": "userEnteredFormat.numberFormat"}})
    return requests
