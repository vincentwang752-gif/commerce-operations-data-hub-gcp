"""Forward record operations to the private Google Sheets store when enabled."""
import os
import time
from urllib.parse import unquote, urlparse

import requests


def enabled():
    return bool(os.getenv("SHEETS_STORE_URL"))


def request(method, url, **kwargs):
    if not enabled():
        return requests.request(method, url, **kwargs)
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token
    base = os.environ["SHEETS_STORE_URL"].rstrip("/")
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) not in (3, 4) or parts[0] != "v0":
        raise ValueError("Unsupported record URL")
    payload = {
        "method": method.upper(),
        "table": unquote(parts[2]),
        "params": kwargs.get("params", {}),
        "payload": kwargs.get("json", {}),
    }
    if len(parts) == 4:
        payload["record_id"] = unquote(parts[3])
    headers = {"Authorization": "Bearer " + fetch_id_token(Request(), base)}
    for attempt in range(4):
        response = requests.post(base + "/records", headers=headers, json=payload,
                                 timeout=max(kwargs.get("timeout", 20), 90))
        if response.status_code not in (429, 502, 503, 504) or attempt == 3:
            return response
        time.sleep(2 ** attempt)


def get(url, **kwargs):
    if not enabled():
        return requests.get(url, **kwargs)
    return request("GET", url, **kwargs)


def post(url, **kwargs):
    if not enabled():
        return requests.post(url, **kwargs)
    return request("POST", url, **kwargs)


def patch(url, **kwargs):
    if not enabled():
        return requests.patch(url, **kwargs)
    return request("PATCH", url, **kwargs)
