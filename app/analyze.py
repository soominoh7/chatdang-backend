"""제품 하나 분석: 점수 + 숨은 탄수화물 + 대체품"""
from . import data
from .score import calculate_score, similarity

# 대체품은 같은 계열 안에서만 (노트북 03 소스 시연 셀과 같은 기준)
FAMILY = {
    "고추장·비빔장": ("고추장", "비빔장", "쌈장", "초장", "볶음고추장"),
    "간장·데리야끼·불고기": ("데리야끼", "불고기", "굴소스", "제육", "돈카츠", "돈까스", "간장", "갈비"),
    "토마토·케찹·바비큐": ("케찹", "케첩", "토마토", "바비큐", "바베큐", "파스타"),
    "매운 소스": ("핫소스", "칠리", "숯불매콤", "마라"),
    "드레싱": ("드레싱", "마요"),
    "떡볶이": ("떡볶이",),
    "팝콘·과자": ("팝콘", "과자", "쿠키", "웨하스", "칩"),
    "초콜릿·캔디": ("초코", "캔디", "젤리", "구미"),
}


def family_of(p):
    name = str(p.get("name") or "").replace(" ", "")
    for fam, words in FAMILY.items():
        if any(w in name for w in words):
            return fam
    return None


def hidden_per100(p):
    """100g당 숨은 탄수화물 = 탄수화물 − 당류 − 식이섬유 − 알룰로스·당알코올 (영양성분 없으면 None)"""
    n = p.get("per100g") or {}
    if n.get("carb") is None:
        return None
    sw = sum(v for v in (n.get("sweeteners") or {}).values() if v)
    return round(max(0.0, n["carb"] - (n.get("sugar") or 0) - (n.get("fiber") or 0) - sw), 1)


def needs_check(p):
    """AI가 감미료 칸을 못 읽어서 숨은 탄수화물이 부풀려졌을 가능성 (실물 라벨 확인 필요)"""
    n = p.get("per100g") or {}
    if n.get("carb") is None or n.get("sweeteners"):
        return False
    text = " ".join(map(str, (p.get("frontClaims") or []) + (p.get("ingredientsFlat") or []) + [p.get("name")]))
    mentions = any(w in text.lower() for w in ("알룰로스", "allulose", "말티톨", "에리스리톨", "당알코올", "이소말트"))
    return mentions and (hidden_per100(p) or 0) > 8


def public_view(p):
    """프론트로 보낼 제품 정보 (내부용 필드 제외)"""
    keys = ("id", "name", "barcode", "category", "maker", "manufacturer", "source", "per100g",
            "ingredients", "frontClaims", "servingSize", "nutritionSource", "images")
    out = {k: p.get(k) for k in keys if p.get(k) not in (None, "", [], {})}
    out["nutritionEstimated"] = p.get("nutritionSource") == "estimated"
    out["needsCheck"] = needs_check(p)
    return out


GOOD_ENOUGH = 4.0      # 숨은 탄수화물이 100g당 이 값 미만이면 '이미 괜찮은 선택' → 대체품 안 보여줌
MIN_GAIN = 2.0         # 대체품은 숨은 탄수화물이 최소 이만큼(g/100g) 줄어야 추천


def find_alternatives(p, grams=None, k=3):
    base_h = hidden_per100(p)
    if base_h is not None and base_h < GOOD_ENOUGH:
        return []
    fam = family_of(p)
    base_score = calculate_score(p, grams)
    g = base_score["servingGrams"]
    cands = []
    for q in data.PRODUCTS:
        if q is p or q.get("barcode") and q.get("barcode") == p.get("barcode"):
            continue
        qh = hidden_per100(q)
        # 추정값 제품은 추천하지 않음 (실제 라벨·사진 값이 있는 제품만)
        if qh is None or needs_check(q) or q.get("nutritionSource") == "estimated":
            continue
        if fam:
            if family_of(q) != fam:
                continue
            sim = None
        else:
            if p.get("category") and q.get("category") and p["category"] != q["category"]:
                continue
            sim = similarity(p, q)
            if sim < 0.2:
                continue
        if base_h is not None and qh > base_h - MIN_GAIN:
            continue
        r = calculate_score(q, g)
        if base_h is None and base_score["score"] is not None and (r["score"] or 0) >= base_score["score"]:
            continue
        why = []
        if base_h is not None:
            why.append(f"숨은 탄수화물 100g당 {base_h}g → {qh}g")
        zeros = [b["ingredient"] for b in r["breakdown"] if b["kind"] == "zero"]
        if zeros:
            why.append(f"{', '.join(zeros[:2])} 사용")
        sw = (q.get("per100g") or {}).get("sweeteners") or {}
        if sw.get("allulose") and "알룰로스" not in zeros:
            why.append(f"알룰로스 {sw['allulose']}g(혈당 영향 거의 없음)")
        cands.append({
            "id": q["id"], "name": q.get("name"), "barcode": q.get("barcode"),
            "hiddenCarbPer100g": qh, "score": r["score"], "level": r["level"],
            "nutritionEstimated": q.get("nutritionSource") == "estimated",
            "reason": " · ".join(why) or "같은 계열에서 혈당 부담이 더 낮아요",
            "_sort": (q.get("nutritionSource") == "estimated", qh, -(sim or 0)),
        })
    cands.sort(key=lambda c: c["_sort"])
    for c in cands:
        c.pop("_sort")
    return cands[:k]


def analyze(p, grams=None):
    r = calculate_score(p, grams)
    n = p.get("per100g") or {}
    sw = n.get("sweeteners") or {}
    if n.get("carb") and sw:
        names = {"allulose": "알룰로스", "sugar_alcohol": "당알코올"}
        parts = [f"{names.get(k, k)} {v}g" for k, v in sw.items() if v]
        r["reasons"].append(f"탄수화물 {n['carb']}g(100g당) 중 {', '.join(parts)}은(는) 혈당을 거의 올리지 않거나 적게 올려서 계산에서 따로 봤어요.")
    if needs_check(p):
        r["reasons"].append("감미료가 들어 있다고 표시됐는데 함량을 읽지 못했어요. 숨은 탄수화물이 실제보다 크게 나왔을 수 있어요.")
    if p.get("nutritionSource") == "estimated":
        r["reasons"].append("이 제품의 영양성분은 비슷한 제품으로 추정한 값이에요(큐빅 SynTitan 정리 데이터 기반). 성분표를 찍으면 정확해져요.")
    h = hidden_per100(p)
    return {
        "product": public_view(p),
        "family": family_of(p),
        "goodChoice": h is not None and h < GOOD_ENOUGH and not needs_check(p),
        "hiddenCarbPer100g": hidden_per100(p),
        "result": r,
        "alternatives": find_alternatives(p, grams),
    }
