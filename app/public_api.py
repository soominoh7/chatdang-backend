"""로컬 DB에 없는 바코드를 공공 API로 실시간 조회 (키가 있을 때만)

바코드 → 식품안전나라 C005(품목제조보고번호) → HACCP(원재료·영양성분) / C002(원재료)
"""
import os
import re

import httpx

from .parse import is_empty, parse_ingredient, parse_rawmtrl, split_outside_parens

HACCP_URL = "https://apis.data.go.kr/B553748/CertImgListServiceV3/getCertImgListServiceV3"
FOODSAFETY_BASE = "http://openapi.foodsafetykorea.go.kr/api"
TIMEOUT = 8


def _foodsafety(service_id, cond, end=5):
    key = os.environ.get("FOODSAFETY_KEY")
    if not key:
        return []
    url = f"{FOODSAFETY_BASE}/{key}/{service_id}/json/1/{end}/" + "&".join(f"{k}={v}" for k, v in cond.items())
    try:
        return httpx.get(url, timeout=TIMEOUT).json().get(service_id, {}).get("row", []) or []
    except Exception:
        return []


def _haccp(report_no):
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        return None
    try:
        r = httpx.get(HACCP_URL, timeout=TIMEOUT,
                      params={"ServiceKey": key, "returnType": "json", "prdlstReportNo": report_no, "numOfRows": 5})
        items = r.json().get("body", {}).get("items", [])
        items = [x.get("item", x) for x in items]
        return items[0] if items else None
    except Exception:
        return None


def _nutrient(text):
    out = {}
    t = str(text or "")
    for key, label in {"carb": "탄수화물", "sugar": r"당류", "fiber": "식이섬유",
                       "sugar_alcohol": "당알코올|당알콜", "allulose": "알룰로스"}.items():
        m = re.search(rf"(?:{label})\s*[:：]?\s*([\d.]+)\s*(mg|g)", t)
        if m:
            v = float(m.group(1))
            out[key] = v / 1000 if m.group(2) == "mg" else v
    basis = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|ml|mL)\s*당(?!류)", t)
    return out, (float(basis.group(1)) if basis else None)


def lookup_barcode(barcode):
    rows = _foodsafety("C005", {"BAR_CD": barcode})
    if not rows:
        return None
    row = rows[0]
    rn = row.get("PRDLST_REPORT_NO")
    p = {"id": rn or barcode, "barcode": barcode, "name": row.get("PRDLST_NM"),
         "category": row.get("PRDLST_DCNM"), "source": "c005", "per100g": {}, "ingredients": []}
    it = _haccp(rn) if rn else None
    if it:
        p["source"] = "c005+haccp"
        p["ingredients"], p["ingredientsFlat"] = parse_rawmtrl(it.get("rawmtrl"))
        p["images"] = [u for u in (it.get("imgurl1"), it.get("imgurl2")) if not is_empty(u)]
        n, basis = _nutrient(it.get("nutrient"))
        if n and basis:
            f = 100 / basis
            conv = lambda k: round(n[k] * f, 2) if k in n else None
            p["per100g"] = {"carb": conv("carb"), "sugar": conv("sugar"), "fiber": conv("fiber"),
                            "sweeteners": {k: conv(k) for k in ("sugar_alcohol", "allulose") if k in n}}
    if not p["ingredients"] and rn:
        c = _foodsafety("C002", {"PRDLST_REPORT_NO": rn})
        if c:
            names = split_outside_parens(c[0].get("RAWMTRL_NM"))
            parsed = [parse_ingredient(x) for x in names]
            p["ingredients"] = [x["name"] for x in parsed]
            p["ingredientsFlat"] = [y for x in parsed for y in [x["name"], *x["sub"]]]
            p["source"] += "+c002"
    return p
