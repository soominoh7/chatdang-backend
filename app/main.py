"""찻당 Chatdang 백엔드 API

실행:  uvicorn app.main:app --reload
문서:  http://localhost:8000/docs  (여기서 바로 눌러보며 테스트 가능)
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import data, public_api, vision
from .analyze import analyze, public_view

app = FastAPI(title="Chatdang API", version="1.0",
              description="'저당' 표시와 실제 혈당 부담의 차이를 보여주는 찻당 백엔드")

origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Process-Time-Ms"])


@app.middleware("http")
async def timing(request: Request, call_next):
    """모든 응답에 서버 처리 시간(ms)을 붙여요 → 속도 검증용"""
    t = time.perf_counter()
    res = await call_next(request)
    res.headers["X-Process-Time-Ms"] = str(round((time.perf_counter() - t) * 1000))
    return res


LIVE_WAIT = 1.5            # 모르는 바코드: 공공 API를 최대 1.5초만 기다리고 바로 사진 촬영으로
_pool = ThreadPoolExecutor(max_workers=4)
_live_jobs = {}            # 바코드 → 진행 중인 조회 (늦게 끝나도 결과는 저장돼서 다음엔 바로 나와요)
_not_found = set()         # 공공 API에도 없던 바코드 (다시 기다리지 않음)


def _live_lookup(code):
    try:
        live = public_api.lookup_barcode(code)
    except Exception:
        live = None
    if live and live.get("name"):
        return data.add_product(live)
    _not_found.add(code)
    return None

STATS = data.load()

# 시연 제품 (바코드) — 시연 순서대로
DEMO_BARCODES = [
    "8801392136085",   # 해찬들 저당 쌈장 → 대체품 비비드 비빔장
    "8801392141607",   # 해찬들 저당 소불고기 양념 → 대체품 비비드 데리야끼
    "8801117376307",   # 마이구미 포도 ZERO% ('설탕제로'인데 숨은 탄수화물)
    "8804433103817",   # 라라스윗 딥크림 웨하스 미니스 ('당류 2.8g'인데 숨은 탄수화물)
    "8801094082406",   # 코카콜라 제로 (진짜 괜찮은 선택)
]


@app.get("/api/ping")
def ping():
    """서버 깨우기용 (앱을 열자마자 한 번 호출, 자동 접속용)"""
    return {"ok": True}


@app.get("/")
def health():
    return {"status": "ok", **STATS, "visionKey": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "publicApiKey": bool(os.environ.get("FOODSAFETY_KEY"))}


@app.get("/api/products/barcode/{barcode}")
def by_barcode(barcode: str, grams: float | None = Query(None, description="1회 섭취량(g). 비우면 식약처 기준")):
    """바코드 → 분석 결과. 못 찾으면 404 + needPhoto=true (프론트는 사진 촬영 화면으로)"""
    code = "".join(ch for ch in barcode if ch.isdigit())
    p = data.BY_BARCODE.get(code)
    if not p and code not in _not_found:
        job = _live_jobs.get(code)
        if job is None or (job.done() and job.result() is None):
            job = _live_jobs[code] = _pool.submit(_live_lookup, code)
        try:
            p = job.result(timeout=LIVE_WAIT)
        except FutTimeout:
            p = None   # 오래 걸리면 기다리지 않고 바로 사진 촬영으로 (조회는 뒤에서 계속)
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
    t = time.perf_counter()
    try:
        ai = vision.call_claude(images)
    except Exception as e:
        raise HTTPException(502, f"사진 분석에 실패했어요: {e}")
    p, issues = vision.to_product(ai, barcode)
    p = data.add_product(p)
    res = analyze(p, grams)
    res["issues"] = issues
    res["aiRaw"] = ai
    res["aiMs"] = round((time.perf_counter() - t) * 1000)   # AI가 사진 읽는 데 걸린 시간
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
