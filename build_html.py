#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1099 薪资勘误看板 - 自动构建脚本
从飞书多维表格拉取数据，更新 HTML 中的嵌入式数据
用于 GitHub Actions 定时任务
"""

import json
import os
import re
import urllib.request
from collections import defaultdict

# ─── 配置 ───
APP_ID = os.environ["FEISHU_APP_ID"]
APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BASE_TOKEN = "UaqrweyDGicDldkNhUzcS82dnTd"
TABLE_ID = "tblWfNL6VuMjKVwG"

FIELD_MAP = {
    "month": "月份", "date_range": "时间区间",
    "region": "大区", "actual": "本期实发工时/h", "due": "本期应发工时/h",
    "backpay": "补发工时/h", "ratio": "出错占比率",
}
WEEK_DATE_MAP = {
    "2026.06.22-2026.06.28": "W1",
    "2026.06.29-2026.07.05": "W2",
    "2026.07.06-2026.07.12": "W3",
    "2026.07.13-2026.07.19": "W4",
}
REASON_COUNT = {
    "打卡机/系统故障": "打卡机/系统故障",
    "员工漏打卡": "员工漏打卡",
    "未及时录入指纹": "未及时录入指纹",
    "考勤专员数据差异": "考勤专员数据差异",
}
REASON_HOURS = {
    "打卡机/系统故障 (1)": "打卡机/系统故障",
    "员工漏打卡 (1)": "员工漏打卡",
    "未及时录入指纹 (1)": "未及时录入指纹",
    "考勤专员数据差异 (1)": "考勤专员数据差异",
}

# ─── 工具函数 ───
def f(v):
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "—"): return 0.0
    try: return float(s)
    except: return 0.0

def api_get(url):
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=data, headers={"Content-Type": "application/json"})
    token = json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]
    req2 = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req2).read())

def fetch_all():
    records = []
    pt = None
    base = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records"
    while True:
        url = base + (f"?page_token={pt}" if pt else "")
        r = api_get(url)
        if r["code"] != 0: break
        records.extend(r["data"]["items"])
        if not r["data"].get("has_more"): break
        pt = r["data"]["page_token"]
    return records

# ─── 聚合 ───
def aggregate(records):
    rows = []
    for item in records:
        fld = item["fields"]
        dr_raw = str(fld.get(FIELD_MAP["date_range"], "")).strip()
        dr_short = dr_raw.split("(")[0] if "(" in dr_raw else dr_raw
        wk = WEEK_DATE_MAP.get(dr_short, "")
        mo = str(fld.get(FIELD_MAP["month"], "")).strip()
        rg = str(fld.get(FIELD_MAP["region"], "")).strip()
        ac = f(fld.get(FIELD_MAP["actual"]))
        du = f(fld.get(FIELD_MAP["due"]))
        bp = f(fld.get(FIELD_MAP["backpay"]))
        if not rg: continue

        reasons = []
        accounted = 0.0
        for fkey, name in REASON_HOURS.items():
            h = f(fld.get(fkey))
            if h > 0:
                c = sum(int(float(fld.get(ckey, 0) or 0)) for ckey, cname in REASON_COUNT.items() if cname == name)
                if c == 0: c = 1
                reasons.append({"reason": name, "count": c, "backpay_hours": h})
                accounted += h
        for fkey, name in REASON_COUNT.items():
            c = sum(1 for _ in [0] if fld.get(fkey))
            try: c = int(float(fld.get(fkey, 0) or 0))
            except: c = 0
            if c > 0 and not any(r["reason"] == name for r in reasons):
                reasons.append({"reason": name, "count": c, "backpay_hours": 0})
        remaining = bp - accounted
        if remaining > 0.01:
            for r in reasons:
                if r["backpay_hours"] == 0:
                    r["backpay_hours"] = round(remaining, 2); break

        rows.append({"week_label": wk, "month": mo, "date_range": dr_raw, "region": rg,
                     "actual_hours": ac, "due_hours": du, "backpay_hours": bp, "reasons": reasons})

    wk_map = defaultdict(list)
    for r in rows:
        if r["week_label"] in ("W1", "W2", "W3", "W4"):
            wk_map[r["week_label"]].append(r)
        else:
            wk_map["_u"].append(r)

    weekly = []
    for lbl in ["W1", "W2", "W3", "W4"]:
        if lbl not in wk_map: continue
        wrs = wk_map[lbl]
        rd = defaultdict(lambda: {"actual_hours": 0, "due_hours": 0, "backpay_hours": 0,
                                   "reasons": defaultdict(lambda: {"count": 0, "backpay_hours": 0})})
        for dr in wrs:
            rg = dr["region"]
            rd[rg]["actual_hours"] += dr["actual_hours"]
            rd[rg]["due_hours"] += dr["due_hours"]
            rd[rg]["backpay_hours"] += dr["backpay_hours"]
            for rs in dr["reasons"]:
                rd[rg]["reasons"][rs["reason"]]["count"] += rs["count"]
                rd[rg]["reasons"][rs["reason"]]["backpay_hours"] += rs["backpay_hours"]
        rs_map = {}
        for rg, d in sorted(rd.items()):
            rl = [{"reason": k, "count": v["count"], "backpay_hours": round(v["backpay_hours"], 2)}
                  for k, v in sorted(d["reasons"].items(), key=lambda x: -x[1]["backpay_hours"])
                  if v["backpay_hours"] > 0]
            er = round(d["backpay_hours"] / d["due_hours"] * 100, 2) if d["due_hours"] > 0 else 0
            rs_map[rg] = {"actual_hours": round(d["actual_hours"], 2),
                          "due_hours": round(d["due_hours"], 2),
                          "backpay_hours": round(d["backpay_hours"], 2),
                          "error_ratio": er, "reasons": rl}
        weekly.append({"label": lbl, "month": wrs[0]["month"],
                       "date_range": wrs[0]["date_range"], "regions": rs_map})

    all_regions = sorted(set(r["region"] for r in rows))

    monthly = defaultdict(lambda: defaultdict(lambda: {"actual_hours": 0, "due_hours": 0, "backpay_hours": 0,
        "reasons": defaultdict(lambda: {"count": 0, "backpay_hours": 0})}))
    for r in rows:
        m, rg = r["month"], r["region"]
        monthly[m][rg]["actual_hours"] += r["actual_hours"]
        monthly[m][rg]["due_hours"] += r["due_hours"]
        monthly[m][rg]["backpay_hours"] += r["backpay_hours"]
        for rs in r["reasons"]:
            if rs["backpay_hours"] > 0:
                monthly[m][rg]["reasons"][rs["reason"]]["count"] += rs["count"]
                monthly[m][rg]["reasons"][rs["reason"]]["backpay_hours"] += rs["backpay_hours"]

    mj = {}
    for m in sorted(monthly.keys()):
        mj[m] = {}
        for rg in all_regions:
            if rg in monthly[m]:
                d = monthly[m][rg]
                rl = [{"reason": k, "count": v["count"], "backpay_hours": round(v["backpay_hours"], 2)}
                      for k, v in sorted(d["reasons"].items(), key=lambda x: -x[1]["backpay_hours"])
                      if v["backpay_hours"] > 0]
                er = round(d["backpay_hours"] / d["due_hours"] * 100, 2) if d["due_hours"] > 0 else 0
                mj[m][rg] = {"actual_hours": round(d["actual_hours"], 2),
                             "due_hours": round(d["due_hours"], 2),
                             "backpay_hours": round(d["backpay_hours"], 2),
                             "error_ratio": er, "reasons": rl}
            else:
                mj[m][rg] = {"actual_hours": 0, "due_hours": 0, "backpay_hours": 0,
                             "error_ratio": 0, "reasons": []}

    return {"weeks": weekly, "regions": all_regions, "monthly": mj}

# ─── 主流程 ───
if __name__ == "__main__":
    print("Fetching records from Feishu Bitable...")
    records = fetch_all()
    print(f"  Got {len(records)} records")

    data = aggregate(records)
    print(f"  Aggregated: {len(data['weeks'])} weeks, {len(data['regions'])} regions")

    # Read template HTML
    html_file = "index.html"
    if not os.path.exists(html_file):
        # Try alternative name
        for f in os.listdir("."):
            if f.endswith(".html") and "1099" in f:
                html_file = f
                break
    with open(html_file, "r", encoding="utf-8") as f:
        html = f.read()

    # Inject data
    new_data = "const DATA = " + json.dumps(data, ensure_ascii=False) + ";"
    html = re.sub(r"const DATA = \{.*?\};", new_data, html, flags=re.DOTALL)

    # Update timestamp
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y.%m.%d %H:%M CST")
    html = re.sub(r"更新于 [\d.]+.*?</strong>", f"更新于 {now}</strong>", html)

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Updated {html_file} at {now}")
    print("Done.")
