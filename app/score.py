"""혈당 부담 점수 · 원료 분류 · 대체품 (노트북 03에서 옮김)"""
import re

INGREDIENT_TABLE = [
    # name,              match words,                                   kind,      gi
    # 식이섬유: 이름에 '덱스트린'이 들어가도 소화되지 않아 혈당 영향이 거의 없음 → 반드시 '말토덱스트린'보다 먼저
    ("난소화성말토덱스트린(식이섬유)", ["난소화성말토덱스트린", "난소화성덱스트린", "저항성말토덱스트린", "저항성덱스트린"], "zero", 0),
    ("폴리덱스트로스(식이섬유)", ["폴리덱스트로스"],                       "zero",     0),
    ("말토덱스트린",      ["말토덱스트린"],                                "hidden",  95),
    ("환원물엿(당알코올)", ["환원물엿", "말티톨시럽", "말티톨액"],          "polyol",  52),
    ("말티톨",            ["말티톨"],                                     "polyol",  35),
    ("소르비톨",          ["소르비톨", "솔비톨"],                          "polyol",   9),
    ("자일리톨",          ["자일리톨"],                                   "polyol",  13),
    ("에리스리톨",        ["에리스리톨", "에리트리톨"],                    "zero",     0),
    ("이소말트",          ["이소말트"],                                   "polyol",   2),
    ("락티톨",            ["락티톨"],                                     "polyol",   6),
    ("만니톨",            ["만니톨"],                                     "zero",     0),
    ("알룰로스",          ["알룰로스", "알룰로오스", "사이코스"],          "zero",     0),
    ("스테비아",          ["스테비", "효소처리스테비아"],                  "zero",     0),
    ("수크랄로스",        ["수크랄로스"],                                 "zero",     0),
    ("아스파탐",          ["아스파탐"],                                   "zero",     0),
    ("아세설팜칼륨",      ["아세설팜"],                                   "zero",     0),
    ("나한과",            ["나한과"],                                     "zero",     0),
    ("물엿",              ["물엿", "콘시럽", "옥수수시럽", "맥아시럽"],     "sugar",   90),
    ("포도당",            ["포도당", "결정포도당"],                        "sugar",  100),
    ("올리고당",          ["올리고당"],                                   "sugar",   30),
    ("과당",              ["과당", "액상과당", "고과당"],                  "sugar",   25),
    ("설탕",              ["설탕", "백설탕", "정백당", "황설탕", "흑설탕", "원당", "자당"], "sugar", 65),
    ("꿀",                ["꿀", "벌꿀"],                                 "sugar",   60),
    ("조청",              ["조청"],                                       "sugar",   90),
    ("덱스트린",          ["덱스트린"],                                   "hidden",  90),
    ("전분",              ["전분", "변성전분", "감자전분", "옥수수전분", "타피오카전분"], "hidden", 80),
    ("밀가루",            ["소맥분", "밀가루"],                            "hidden",  70),
    ("쌀가루",            ["쌀가루", "찹쌀가루"],                          "hidden",  80),
]

# 원료별 쉬운 설명 (설문: 가장 보고 싶은 정보 1위 '원재료·감미료의 쉬운 설명')
EXPLAIN = {
    "말토덱스트린": "전분을 잘게 분해한 가루예요. 단맛은 거의 없지만 포도당만큼 빠르게 혈당을 올려요.",
    "덱스트린": "전분을 분해해 만든 탄수화물이에요. '당류'로 표시되지 않지만 혈당을 빠르게 올려요.",
    "전분": "감자·옥수수 등에서 뽑은 탄수화물로, 걸쭉하게 만들 때 써요. '당류'로 안 잡히지만 혈당을 올려요.",
    "밀가루": "밀을 빻은 가루로 대부분 전분이에요. '당류'로 표시되지 않지만 혈당을 올려요.",
    "쌀가루": "쌀을 빻은 가루로 대부분 전분이에요. '당류'로 표시되지 않지만 혈당을 올려요.",
    "환원물엿(당알코올)": "물엿을 가공한 당알코올이에요. 설탕보다는 덜하지만 혈당을 꽤 올리고, 많이 먹으면 배탈이 날 수 있어요.",
    "말티톨": "설탕 대신 쓰는 당알코올이에요. 혈당을 설탕의 절반 정도 올리고, 많이 먹으면 배탈이 날 수 있어요.",
    "소르비톨": "과일에도 있는 당알코올이에요. 혈당 영향은 작지만 많이 먹으면 배탈이 날 수 있어요.",
    "자일리톨": "껌에 많이 쓰는 당알코올이에요. 혈당 영향은 작지만 많이 먹으면 배탈이 날 수 있어요.",
    "이소말트": "사탕·과자에 쓰는 당알코올이에요. 혈당 영향은 작지만 많이 먹으면 배탈이 날 수 있어요.",
    "락티톨": "당알코올의 한 종류예요. 혈당 영향은 작지만 많이 먹으면 배탈이 날 수 있어요.",
    "에리스리톨": "당알코올이지만 거의 흡수되지 않고 그대로 배출돼서 혈당을 거의 올리지 않아요.",
    "만니톨": "당알코올의 한 종류로 혈당을 거의 올리지 않아요. 많이 먹으면 배탈이 날 수 있어요.",
    "알룰로스": "자연에도 조금 있는 희소당이에요. 단맛은 있지만 몸에서 거의 쓰이지 않아 혈당을 거의 올리지 않아요.",
    "스테비아": "스테비아 잎에서 뽑은 감미료예요. 아주 적은 양으로 단맛을 내고 혈당을 올리지 않아요.",
    "수크랄로스": "설탕보다 수백 배 단 인공감미료예요. 아주 조금만 들어가고 혈당을 올리지 않아요.",
    "아스파탐": "설탕보다 훨씬 단 인공감미료예요. 아주 조금만 들어가고 혈당을 올리지 않아요.",
    "아세설팜칼륨": "설탕보다 훨씬 단 인공감미료예요. 아주 조금만 들어가고 혈당을 올리지 않아요.",
    "나한과": "나한과 열매에서 뽑은 감미료예요. 혈당을 거의 올리지 않아요.",
    "난소화성말토덱스트린(식이섬유)": "이름은 비슷하지만 소화되지 않는 식이섬유예요. 혈당을 거의 올리지 않아요.",
    "폴리덱스트로스(식이섬유)": "소화되지 않는 식이섬유예요. 혈당을 거의 올리지 않아요.",
    "물엿": "전분을 분해한 끈적한 시럽으로 포도당이 많아요. 혈당을 빠르게 올려요.",
    "포도당": "혈당 그 자체예요. 가장 빠르게 혈당을 올려요.",
    "올리고당": "단맛이 덜한 당이에요. 설탕보다는 덜하지만 혈당을 올려요.",
    "과당": "과일의 단맛 성분이에요. 혈당은 덜 올리지만 많이 먹으면 몸에 부담이 될 수 있어요.",
    "설탕": "가장 흔한 당이에요. 혈당을 빠르게 올려요.",
    "꿀": "대부분 당(포도당·과당)이에요. 혈당을 올려요.",
    "조청": "곡물을 졸여 만든 시럽으로 엿당·포도당이 많아요. 혈당을 빠르게 올려요.",
}


def classify(ingredient_name):
    """원재료 이름 → 분류표 항목 (없으면 None)"""
    name = re.sub(r"\s", "", str(ingredient_name))
    for std, words, kind, gi in INGREDIENT_TABLE:
        if any(w in name for w in words):
            return {"std": std, "kind": kind, "gi": gi}
    return None


def carb_sources(p):
    """제품의 원재료에서 탄수화물 원료 찾기 → [{std, kind, gi, rank(표시순서), raw}]
    하위 성분은 상위 원재료의 순서를 물려받음 (예: 고추장[물엿] → 고추장 자리)"""
    found, seen = [], set()
    top = p.get("ingredients") or []
    flat = p.get("ingredientsFlat") or top
    rank, top_i = 0, -1
    for ing in flat:
        if top_i + 1 < len(top) and ing == top[top_i + 1]:
            top_i += 1
            rank = top_i + 1
        c = classify(ing)
        if c and c["std"] not in seen:
            seen.add(c["std"])
            found.append({**c, "rank": rank or 1, "raw": ing})
    return found



# 1회 섭취량 기본값 — 식약처 1회 섭취참고량 (식품영양성분DB NUTRI_AMOUNT_SERVING에서 확인, 2026.11.9)
# 위에서부터 먼저 맞는 항목을 사용 (구체적인 유형을 앞에)
SERVING_REF = [
    ("덮밥",   165, "덮밥소스 165g (식약처 1회 섭취참고량)"),
    ("카레",   165, "덮밥소스 165g 준용 (식약처 1회 섭취참고량)"),
    ("짜장",   165, "덮밥소스 165g 준용 (식약처 1회 섭취참고량)"),
    ("케첩",    10, "토마토케첩 10g (식약처 1회 섭취참고량)"),
    ("혼합장",  10, "혼합장 10g (식약처 1회 섭취참고량)"),
    ("비빔장",  10, "혼합장 10g 준용 (식약처 1회 섭취참고량)"),
    ("향미유",   5, "향미유 5g (식약처 1회 섭취참고량)"),
    ("드레싱",  15, "소스/드레싱 15g (식약처 1회 섭취참고량)"),
    ("소스",    15, "소스/드레싱 15g (식약처 1회 섭취참고량)"),
    ("과자",    30, "과자 30g (식약처 1회 섭취참고량)"),
    ("스낵",    30, "스낵과자 30g (식약처 1회 섭취참고량)"),
    ("빵",      70, "빵 70g (식약처 1회 섭취참고량)"),
    # 음료류: 1회 섭취참고량 200mL (ml은 g과 같은 숫자로 계산)
    ("음료",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("우유",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("라떼",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("두유",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("주스",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("콜라",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("사이다", 200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("탄산",   200, "음료 200mL (식약처 1회 섭취참고량)"),
    ("에이드", 200, "음료 200mL (식약처 1회 섭취참고량)"),
]
FALLBACK_SERVING = 30   # 위 표에 없는 유형 (임시값)
SUGAR_GI = 65   # 표시된 '당류'의 평균 GI (설탕 계열 가정)

CARB_RANGE = {   # 영양성분이 없을 때 쓰는 식품유형별 100g당 탄수화물 대략 범위 (g)
    "소스": (10, 45), "드레싱": (5, 30), "장": (15, 45), "케첩": (20, 30), "시럽": (40, 90), "잼": (30, 70),
    "음료": (0, 15), "과자": (50, 80), "캔디": (60, 100), "초콜릿": (30, 65), "아이스크림": (15, 35),
}

def carb_range_of(p):
    cat = str(p.get("category") or "") + str(p.get("name") or "")
    for k, v in CARB_RANGE.items():
        if k in cat:
            return v
    return (5, 60)

def default_serving(p):
    """(g, 근거 문장) — 이름을 먼저 보고(비빔장·덮밥 등), 없으면 식품유형으로"""
    for text in (str(p.get("name") or ""), str(p.get("category") or "")):
        for k, g, note in SERVING_REF:
            if k in text:
                return g, note
    return FALLBACK_SERVING, "기본값 30g (식약처 참고량 미확인 유형)"

def serving_of(p, serving_grams=None):
    """(g, 근거 종류, 근거 문장)"""
    if serving_grams:
        return float(serving_grams), "user", "사용자가 선택한 양"
    s = (p.get("servingSize") or {})
    if s.get("value"):
        return float(s["value"]), s.get("basis") or "label", s.get("note") or "포장지 1회 제공량"
    g, note = default_serving(p)
    return float(g), ("reference" if "식약처" in note else "default"), note

IMPACT = lambda gi: "거의 없음" if gi <= 5 else ("낮음" if gi <= 20 else ("중간" if gi <= 55 else "높음"))

def gl_to_score(gl):
    return int(round(min(100, max(0, gl / 25 * 100))))

def level_of(gl):
    return "낮음" if gl <= 10 else ("보통" if gl < 20 else "높음")


def calculate_score(p, serving_grams=None):
    g, s_basis, s_note = serving_of(p, serving_grams)
    n = p.get("per100g") or {}
    carb, sugar, fiber = n.get("carb"), n.get("sugar"), n.get("fiber")
    sweet = n.get("sweeteners") or {}
    srcs = carb_sources(p)
    hidden_srcs = [s for s in srcs if s["kind"] in ("hidden", "polyol")]
    reasons, breakdown = [], [
        {"ingredient": s["std"], "raw": s["raw"], "impact": IMPACT(s["gi"]), "rank": s["rank"], "kind": s["kind"],
         "explain": EXPLAIN.get(s["std"], "")}
        for s in srcs
    ]

    # --- A. 영양성분이 있을 때: GL 계산 ---
    if carb is not None:
        f = g / 100.0
        sugar_g = (sugar or 0) * f
        declared = {k: v * f for k, v in sweet.items() if v}
        # 표시된 당알코올의 GI: 원재료에서 확인된 당알코올 기준 (에리스리톨만 있으면 0, 말티톨이면 35 …, 모르면 40)
        polyol_gis = [x["gi"] for x in srcs if x["kind"] == "polyol"]
        zero_polyol = any(x["std"] in ("에리스리톨", "만니톨") for x in srcs)
        sa_gi = max(polyol_gis) if polyol_gis else (0 if zero_polyol else 40)
        declared_gl = sum(v * (0 if k == "allulose" else sa_gi) / 100 for k, v in declared.items())
        hidden_g = max(0.0, carb * f - sugar_g - (fiber or 0) * f - sum(declared.values()))
        sugar_gl = sugar_g * SUGAR_GI / 100

        if hidden_g > 0 and hidden_srcs:
            gis = [s["gi"] for s in hidden_srcs]
            # 표시 순서 가중 평균(앞에 있을수록 많이 들었다고 가정)
            w = [1 / s["rank"] for s in hidden_srcs]
            gi_mid = sum(gi * wi for gi, wi in zip(gis, w)) / sum(w)
            gi_min, gi_max = min(gis), max(gis)
        elif hidden_g > 0:
            gi_min, gi_mid, gi_max = 0, 40, 80     # 원료를 못 찾음 → 넓은 범위
            reasons.append("당류로 표시되지 않은 탄수화물이 있지만 어떤 원료인지 원재료에서 확인되지 않았어요.")
        else:
            gi_min = gi_mid = gi_max = 0

        base = sugar_gl + declared_gl
        gl_min, gl_mid, gl_max = (base + hidden_g * gi_min / 100, base + hidden_g * gi_mid / 100, base + hidden_g * gi_max / 100)
        total_gl = gl_mid or 0.0001
        hidden_share = round((hidden_g * gi_mid / 100) / total_gl, 2) if gl_mid > 0 else 0.0
        low_sugar = sugar is not None and sugar < 5
        score = gl_to_score(gl_mid)
        rng = None if abs(gl_max - gl_min) < 1 else {"min": gl_to_score(gl_min), "max": gl_to_score(gl_max)}

        if low_sugar and hidden_share >= 0.5 and hidden_g >= 0.5:
            reasons.insert(0, f"당류는 100g당 {sugar}g으로 '저당' 기준을 충족하지만, 혈당 부담의 약 {int(hidden_share*100)}%가 당류로 표시되지 않는 원료에서 와요.")
        for s in sorted(hidden_srcs, key=lambda x: x["rank"])[:2]:
            reasons.append(f"{s['std']}({s['raw']})이(가) 원재료 {s['rank']}번째에 있어요. 혈당 영향: {IMPACT(s['gi'])}.")
        zeros = [s["std"] for s in srcs if s["kind"] == "zero"]
        if zeros:
            reasons.append(f"{', '.join(zeros)}은(는) 혈당에 거의 영향을 주지 않아요.")
        return {
            "score": score, "level": level_of(gl_mid), "range": rng, "servingGrams": g, "servingBasis": s_basis, "servingNote": s_note,
            "gl": {"min": round(gl_min, 1), "mid": round(gl_mid, 1), "max": round(gl_max, 1)},
            "hiddenCarbGrams": round(hidden_g, 1), "hiddenShare": hidden_share, "lowSugarLabel": low_sugar,
            "breakdown": breakdown, "basis": "nutrition", "reasons": reasons,
        }

    # --- B. 영양성분이 없을 때: 식품유형의 일반적인 탄수화물 범위 × 원재료의 GI 범위로 GL 범위 추정 ---
    lo_c, hi_c = carb_range_of(p)
    f = g / 100.0
    gis = [s["gi"] for s in srcs if s["kind"] != "zero"]
    gi_lo, gi_hi = (min(gis), max(gis)) if gis else (0, 30)
    gl_lo, gl_hi = lo_c * f * gi_lo / 100, hi_c * f * gi_hi / 100
    lo, hi = gl_to_score(gl_lo), gl_to_score(gl_hi)
    risky = [s for s in srcs if s["gi"] >= 30]
    for s in sorted(risky, key=lambda x: x["rank"])[:3]:
        reasons.append(f"{s['std']}({s['raw']})이(가) 원재료 {s['rank']}번째에 있어요. 혈당 영향: {IMPACT(s['gi'])}.")
    reasons.append("영양성분 정보가 없어 원재료와 식품유형으로 추정했어요. 성분표를 찍으면 정확해져요.")
    return {
        "score": None, "level": "추정", "range": {"min": lo, "max": hi}, "servingGrams": g, "servingBasis": s_basis, "servingNote": s_note,
        "gl": {"min": round(gl_lo, 1), "mid": None, "max": round(gl_hi, 1)}, "hiddenCarbGrams": None, "hiddenShare": None, "lowSugarLabel": None,
        "breakdown": breakdown, "basis": "ingredients_only", "reasons": reasons,
    }

STOP = {"소스", "용", "맛", "제로", "저당", "슈가", "프리", "골드", "프리미엄", "오리지널", "kg", "g", "ml"}

def name_tokens(name):
    toks = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", str(name or ""))
    out = set()
    for t in toks:
        if t in STOP:
            continue
        out.add(t)
        for k in ("비빔", "불고기", "데리야끼", "바베큐", "돈까스", "떡볶이", "짜장", "카레", "칠리", "마라", "간장", "고추장", "굴", "스테이크", "케첩", "마요", "드레싱", "파스타", "토마토", "크림", "갈비"):
            if k in t:
                out.add(k)
    return out

def similarity(a, b):
    ta, tb = name_tokens(a.get("name")), name_tokens(b.get("name"))
    name_sim = len(ta & tb) / max(1, len(ta | tb))
    ia, ib = set((a.get("ingredients") or [])[:5]), set((b.get("ingredients") or [])[:5])
    ing_sim = len(ia & ib) / max(1, len(ia | ib))
    return 0.6 * name_sim + 0.4 * ing_sim

def comparable_score(r):
    if r["score"] is not None:
        return r["score"]
    return (r["range"]["min"] + r["range"]["max"]) / 2
