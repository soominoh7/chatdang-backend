"""포장지 사진 → 원재료·영양성분 (Claude API)"""
import base64
import io
import json
import os
import re

import httpx
from PIL import Image, ImageOps

from .parse import parse_rawmtrl

MODEL = os.environ.get("VISION_MODEL", "claude-haiku-5-5")
# 첫 시도에서 영양정보를 못 읽으면(둥근 통·반사·작은 글씨) 더 정확한 모델로 한 번 더 시도
FALLBACK_MODEL = os.environ.get("VISION_FALLBACK_MODEL", "claude-sonnet-5-5")

PROMPT = """너는 한국 식품 포장지를 읽는 도우미야. 사진들은 모두 같은 제품의 앞면/뒷면이야.
사진에 보이는 글자만 그대로 옮기고, 안 보이는 값은 null로 둬. 추측해서 채우지 마.
아래 JSON 하나만 출력해.
{
 "product_name": "제품명(앞면 기준)",
 "maker": "제조사 또는 판매원",
 "food_type": "식품유형(예: 소스, 과자, 초콜릿가공품)",
 "barcode": "바코드 숫자",
 "front_claims": ["저당", "제로슈거", "알룰로스" 같은 앞면 광고 문구들],
 "ingredients_text": "원재료명 칸 전체를 적힌 그대로",
 "nutrition": {
   "basis_type": "100g | serving | total 중 하나 (영양정보가 무엇 기준인지)",
   "basis_amount_g": 영양정보 기준량 g 숫자 (100g당이면 100),
   "serving_size_g": 1회 제공량 g (있으면),
   "total_size_g": 총 내용량 g,
   "carb_g": 탄수화물 g, "sugar_g": 당류 g,
   "fiber_g": 식이섬유 g, "sugar_alcohol_g": 당알코올 g, "allulose_g": 알룰로스 g
 }
}
'1g 미만'은 0.5로 적어. ml 제품이면 ml을 g처럼 숫자만 적어.
둥근 병·통에 붙은 라벨이라 글자가 휘거나 가장자리가 잘려 있을 수 있어. 여러 장이면 서로 이어 붙여 읽어.
영양정보 표(탄수화물·당류·당알코올·알룰로스)를 가장 먼저, 가장 꼼꼼히 읽어. 원재료명은 읽히는 부분까지만 적어도 돼."""


def _shrink(raw, size=2000):   # 성분표 글자가 작아서 너무 줄이면 못 읽어요 (Claude는 긴 변 약 1500~2000px까지 활용)
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def _num(x):
    try:
        return float(re.sub(r"[^\d.]", "", str(x))) if x not in (None, "") else None
    except ValueError:
        return None


def _ask(model, content, key):
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=45,
                   headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": model, "max_tokens": 3000, "messages": [{"role": "user", "content": content}]})
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def _has_nutrition(ai):
    n = (ai or {}).get("nutrition") or {}
    return _num(n.get("carb_g")) is not None


def call_claude(images: list[bytes]) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY가 설정되지 않았어요")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": _shrink(b)}}
               for b in images[:4]]
    content.append({"type": "text", "text": PROMPT})
    ai = _ask(MODEL, content, key)
    if not _has_nutrition(ai) and FALLBACK_MODEL and FALLBACK_MODEL != MODEL:
        try:
            ai2 = _ask(FALLBACK_MODEL, content, key)
            if _has_nutrition(ai2) or not ai:
                ai = ai2
                ai["_model"] = FALLBACK_MODEL
        except Exception:
            pass
    return ai


def to_product(ai: dict, barcode: str | None = None) -> tuple[dict, list[str]]:
    """AI 결과 → 우리 제품 형식 + 확인 필요 목록"""
    n = ai.get("nutrition") or {}
    basis = _num(n.get("basis_amount_g")) or (100 if str(n.get("basis_type")).startswith("100") else None)
    conv = lambda v: None if _num(v) is None or not basis else round(_num(v) * 100 / basis, 2)
    per100 = {"carb": conv(n.get("carb_g")), "sugar": conv(n.get("sugar_g")), "fiber": conv(n.get("fiber_g")),
              "sweeteners": {k: conv(n.get(f"{k}_g")) for k in ("sugar_alcohol", "allulose") if conv(n.get(f"{k}_g")) is not None}}
    names, flat = parse_rawmtrl(ai.get("ingredients_text"))
    code = barcode or re.sub(r"\D", "", str(ai.get("barcode") or "")) or None

    issues = []
    c, s = per100["carb"], per100["sugar"]
    if c is None:
        issues.append("영양성분표를 읽지 못했어요. 영양정보 칸이 잘 보이게 다시 찍어 주세요.")
    elif not 0 <= c <= 100:
        issues.append(f"탄수화물 값({c}g/100g)이 이상해요. 확인이 필요해요.")
    if c is not None and s is not None and s > c + 0.5:
        issues.append("당류가 탄수화물보다 크게 읽혔어요. 확인이 필요해요.")
    if c is not None and s is not None and c - s > 8 and not per100["sweeteners"] and \
            any(w in str(ai.get("ingredients_text")) + str(ai.get("front_claims")) for w in ("알룰로스", "말티톨", "에리스리톨", "당알코올")):
        issues.append("감미료가 들어 있는데 알룰로스·당알코올 값을 못 읽었어요. 숨은 탄수화물이 크게 나올 수 있어요.")
    if not names:
        issues.append("원재료명을 읽지 못했어요.")

    p = {
        "id": f"photo_{code}" if code else None,
        "name": ai.get("product_name") or "이름 미확인 제품",
        "maker": ai.get("maker"), "category": ai.get("food_type"),
        "source": "photo_ai", "barcode": code,
        "frontClaims": ai.get("front_claims") or [],
        "per100g": per100, "ingredients": names, "ingredientsFlat": flat,
        "servingSize": {},
    }
    return p, issues
