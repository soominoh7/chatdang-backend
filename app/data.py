"""데이터 불러오기 · 합치기 · 색인

data/ 폴더에 있는 파일을 읽어요 (없는 파일은 건너뜀)
  - products.json        : 공공데이터(HACCP·C002) 기반 제품 DB
  - photo_products.json  : 바코드 사진을 AI로 읽은 제품
  - sauce_products.json  : 소스 사진을 AI로 읽은 제품 (시연 제품)
  - nutrition_filled.csv : SynTitan(DTS) 정리 + 추정 모델로 채운 영양성분 (실제/추정 구분)
"""
import csv
import json
import os
import re

from .parse import is_empty

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))

# 사진에서 바코드를 잘못 읽은 것 바로잡기 (실물 라벨로 확인함)
BARCODE_FIX = {"5208128361729": "8809599361729", "8804333103817": "8804433103817"}

PRODUCTS: list = []          # 전체 제품
BY_BARCODE: dict = {}        # 바코드 → 제품
BY_ID: dict = {}             # id → 제품


def _read_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _normalize(p):
    """노트북마다 조금씩 다른 형식을 하나로 맞추기"""
    p = dict(p)
    p["id"] = str(p.get("id") or p.get("barcode") or p.get("name"))
    p["barcode"] = None if is_empty(p.get("barcode")) else re.sub(r"\D", "", str(p["barcode"])) or None
    p["barcode"] = BARCODE_FIX.get(p["barcode"], p["barcode"])
    ing = p.get("ingredients") or []
    if len(ing) == 2 and all(isinstance(x, list) for x in ing):      # 예전 사진 셀 저장 형식
        p["ingredients"], p["ingredientsFlat"] = ing[0], ing[1]
    p.setdefault("ingredientsFlat", p.get("ingredients") or [])
    n = p.get("per100g") or {}
    p["per100g"] = {"carb": n.get("carb"), "sugar": n.get("sugar"), "fiber": n.get("fiber"),
                    "sweeteners": {k: v for k, v in (n.get("sweeteners") or {}).items() if v is not None}}
    p.setdefault("servingSize", {})
    if p.get("source") == "photo_ai":
        p["servingSize"] = {}          # 사진의 '총 내용량'이 1회 섭취량으로 잡히는 것 방지 → 식약처 기준표 사용
    p["nutritionSource"] = "label" if p["per100g"]["carb"] is not None else None
    if p["nutritionSource"] and p.get("source") == "photo_ai":
        p["nutritionSource"] = "photo_ai"
    return p


def _richness(p):
    return (p["per100g"]["carb"] is not None) * 2 + bool(p.get("ingredients"))


def _merge(base, new):
    """같은 바코드 제품: 비어 있는 칸만 채우기 (정보가 더 많은 쪽을 기준으로)"""
    if _richness(new) > _richness(base):
        base, new = new, base
    for k in ("name", "category", "maker", "manufacturer"):
        if is_empty(base.get(k)) and not is_empty(new.get(k)):
            base[k] = new[k]
    if not base.get("ingredients") and new.get("ingredients"):
        base["ingredients"], base["ingredientsFlat"] = new["ingredients"], new.get("ingredientsFlat", [])
    if base["per100g"]["carb"] is None and new["per100g"]["carb"] is not None:
        base["per100g"], base["nutritionSource"] = new["per100g"], new["nutritionSource"]
    base["frontClaims"] = base.get("frontClaims") or new.get("frontClaims") or []
    return base


def _apply_estimates():
    """nutrition_filled.csv의 '추정' 값으로 빈 영양성분 채우기"""
    path = os.path.join(DATA_DIR, "nutrition_filled.csv")
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            p = BY_ID.get(str(row.get("id")))
            if not p or p["per100g"]["carb"] is not None:
                continue
            if row.get("탄수화물_100g_출처") == "추정" and not is_empty(row.get("탄수화물_100g")):
                p["per100g"]["carb"] = float(row["탄수화물_100g"])
                if row.get("당류_100g_출처") == "추정" and not is_empty(row.get("당류_100g")):
                    p["per100g"]["sugar"] = float(row["당류_100g"])
                p["nutritionSource"] = "estimated"
                n += 1
            if is_empty(p.get("category")) and not is_empty(row.get("식품유형_정리")):
                p["categoryEstimated"] = row["식품유형_정리"]
    return n


def load():
    PRODUCTS.clear(); BY_BARCODE.clear(); BY_ID.clear()
    for name in ("products.json", "photo_products.json", "sauce_products.json"):
        for raw in _read_json(name):
            p = _normalize(raw)
            if not p.get("name"):
                continue
            if p["barcode"] and p["barcode"] in BY_BARCODE:
                old = BY_BARCODE[p["barcode"]]
                merged = _merge(old, p)
                BY_BARCODE[p["barcode"]] = merged
                BY_ID[old["id"]] = BY_ID[p["id"]] = BY_ID[merged["id"]] = merged
                continue
            if p["id"] in BY_ID:
                continue
            BY_ID[p["id"]] = p
            if p["barcode"]:
                BY_BARCODE[p["barcode"]] = p
    # 병합으로 바뀐 객체 반영
    PRODUCTS[:] = list({id(v): v for v in BY_ID.values()}.values())
    est = _apply_estimates()
    return {"products": len(PRODUCTS), "barcodes": len(BY_BARCODE), "estimated": est}


def search(q, limit=20):
    norm = lambda s: re.sub(r"[^0-9a-zA-Z가-힣]", "", str(s or "")).lower()
    key = norm(q)
    if not key:
        return []
    hits = [p for p in PRODUCTS if key in norm(p.get("name"))]
    hits.sort(key=lambda p: (p["per100g"]["carb"] is None, len(p.get("name") or "")))
    return hits[:limit]


def add_product(p):
    """사진 분석으로 새로 알게 된 제품을 메모리에 등록 (서버 재시작 시 사라짐)"""
    p = _normalize(p)
    if p["barcode"] and p["barcode"] in BY_BARCODE:
        old = BY_BARCODE[p["barcode"]]
        p = _merge(old, p)
        BY_ID[old["id"]] = p
        PRODUCTS[:] = [p if x is old else x for x in PRODUCTS]
    else:
        PRODUCTS.append(p)
    BY_ID[p["id"]] = p
    if p["barcode"]:
        BY_BARCODE[p["barcode"]] = p
    return p
