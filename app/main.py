"""찻당 Chatdang 백엔드 API

실행:  uvicorn app.main:app --reload
문서:  http://localhost:8000/docs  (여기서 바로 눌러보며 테스트 가능)
"""
import os

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import data, public_api, vision
from .analyze import analyze, public_view

app = FastAPI(title="Chatdang API", version="1.0",
              description="'저당' 표시와 실제 혈당 부담의 차이를 보여주는 찻당 백엔드")

origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])

STATS = data.load()

# 시연 제품 (바코드) — 시연 순서대로
DEMO_BARCODES = [
    "8801392136085",   # 해찬들 저당 쌈장 (메인)
    "8809219699676",   # 비비드키친 저칼로리 비빔장 (대체품)
    "8801392141607",   # 저당 소불고기 양념
    "8809210344483",   # 비비드키친 저당 데리야끼 (반대 사례)
]


@app.get("/")
def health():
    return {"status": "ok", **STATS, "visionKey": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "publicApiKey": bool(os.environ.get("FOODSAFETY_KEY"))}


@app.get("/api/products/barcode/{barcode}")
def by_barcode(barcode: str, grams: float | None = Query(None, description="1회 섭취량(g). 비우면 식약처 기준")):
    """바코드 → 분석 결과. 못 찾으면 404 + needPhoto=true (프론트는 사진 촬영 화면으로)"""
    code = "".join(ch for ch in barcode if ch.isdigit())
    p = data.BY_BARCODE.get(code)
    if not p:
        live = public_api.lookup_barcode(code)
        if live and live.get("name"):
            p = data.add_product(live)
    if not p:
        raise HTTPException(404, detail={"needPhoto": True, "message": "아직 모르는 제품이에요. 성분표 사진을 찍어 주세요."})
    res = analyze(p, grams)
    res["needPhoto"] = (p.get("per100g") or {}).get("carb") is None
    return res


@app.get("/api/products/{product_id}")
def by_id(product_id: str, grams: float | None = None):
    p = data.BY_ID.get(product_id)
    if not p:
        raise HTTPException(404, "제품을 찾을 수 없어요")
    return analyze(p, grams)


@app.get("/api/search")
def search(q: str, limit: int = 20):
    """제품명 검색 (영양성분이 있는 제품이 먼저)"""
    return [{"id": p["id"], "name": p.get("name"), "barcode": p.get("barcode"), "category": p.get("category"),
             "hasNutrition": (p.get("per100g") or {}).get("carb") is not None,
             "nutritionEstimated": p.get("nutritionSource") == "estimated"}
            for p in data.search(q, limit)]


@app.post("/api/analyze/photo")
async def analyze_photo(files: list[UploadFile] = File(..., description="포장지 사진 1~4장 (앞면·뒷면)"),
                        barcode: str | None = Form(None), grams: float | None = Form(None)):
    """성분표 사진 → AI가 읽기 → 분석 결과 (+ 확인이 필요한 항목 issues)"""
    if not files:
        raise HTTPException(400, "사진을 1장 이상 올려 주세요")
    images = [await f.read() for f in files[:4]]
    try:
        ai = vision.call_claude(images)
    except Exception as e:
        raise HTTPException(502, f"사진 분석에 실패했어요: {e}")
    p, issues = vision.to_product(ai, barcode)
    p = data.add_product(p)
    res = analyze(p, grams)
    res["issues"] = issues
    res["aiRaw"] = ai
    return res


@app.get("/api/demo")
def demo(grams: float | None = None):
    """시연 제품 분석 결과 (바코드 순서대로)"""
    return [analyze(data.BY_BARCODE[b], grams) for b in DEMO_BARCODES if b in data.BY_BARCODE]


@app.get("/api/compare")
def compare(ids: str = Query(..., description="쉼표로 구분한 제품 id"), grams: float = 15):
    """여러 제품을 같은 양으로 비교"""
    out = []
    for i in ids.split(","):
        p = data.BY_ID.get(i.strip()) or data.BY_BARCODE.get(i.strip())
        if p:
            r = analyze(p, grams)
            out.append({"product": public_view(p), "hiddenCarbPer100g": r["hiddenCarbPer100g"], "result": r["result"]})
    return {"servingGrams": grams, "items": out}
