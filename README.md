# 찻당 Chatdang 백엔드 (FastAPI)

'저당' 표시만 믿고 사는 소비자를 위해, 바코드·성분표 사진으로 **표시 문구와 실제 혈당 부담의 차이**를
1회 섭취량 기준으로 보여주고 **같은 계열의 대체품**을 추천하는 API예요.

## 폴더 구조

```
app/
  main.py        API 엔드포인트
  data.py        데이터 불러오기·합치기 (공공데이터 + 사진 AI + SynTitan 추정값)
  analyze.py     제품 분석: 점수 + 숨은 탄수화물 + 대체품
  score.py       혈당부하(GL) 점수, 원료 분류표, 식약처 1회 섭취참고량
  parse.py       원재료 문자열 파서
  vision.py      포장지 사진 → 원재료·영양성분 (Claude API)
  public_api.py  로컬에 없는 바코드를 공공 API(C005·HACCP·C002)로 실시간 조회
data/            ← 아래 파일을 넣어 주세요 (없는 파일은 건너뜀)
  products.json         공공데이터 제품 DB (노트북 02)
  photo_products.json   바코드 사진 AI 결과
  sauce_products.json   소스 사진 AI 결과 (시연 제품)
  nutrition_filled.csv  SynTitan 정리 + 추정 모델로 채운 영양성분
```

## 데이터 흐름

바코드 → ① 로컬 DB → ② 공공 API 실시간 조회 → ③ 못 찾으면 `404 needPhoto` → 사진 촬영 → `POST /api/analyze/photo`

영양성분 출처(`product.nutritionSource`): `label`(공공데이터 표시값) / `photo_ai`(사진에서 읽음) / `estimated`(SynTitan 정리 데이터로 추정 — 화면에 '추정' 표시)

## API (프론트용)

배포 주소 뒤에 `/docs`를 붙이면 모든 API를 브라우저에서 바로 눌러볼 수 있어요.

| 메서드 | 주소 | 설명 |
|---|---|---|
| GET | `/` | 서버 상태 (제품 수, 키 설정 여부) |
| GET | `/api/products/barcode/{barcode}?grams=` | 바코드 분석. 모르는 제품이면 404 + `needPhoto: true` |
| GET | `/api/products/{id}?grams=` | id로 분석 (검색 결과·대체품 클릭 시) |
| GET | `/api/search?q=쌈장` | 제품명 검색 |
| POST | `/api/analyze/photo` | 사진 1~4장(`files`), 선택: `barcode`, `grams` → 분석 + `issues`(확인 필요 항목) |
| GET | `/api/demo` | 시연 제품 4개 분석 결과 |
| GET | `/api/compare?ids=a,b&grams=15` | 같은 양으로 비교 |

### 분석 결과 형식 (`/api/products/...`, `/api/analyze/photo`, `/api/demo`의 각 항목)

```json
{
  "product": {"id", "name", "barcode", "category", "frontClaims": ["저당"],
              "per100g": {"carb": 34, "sugar": 3, "fiber": null, "sweeteners": {"allulose": 14.8}},
              "ingredients": [...], "nutritionSource": "photo_ai",
              "nutritionEstimated": false, "needsCheck": false},
  "family": "고추장·비빔장",
  "hiddenCarbPer100g": 16.2,
  "result": {"score": 6, "level": "낮음", "servingGrams": 10, "servingNote": "혼합장 10g (식약처 1회 섭취참고량)",
             "gl": {"min", "mid", "max"}, "hiddenCarbGrams": 1.6, "hiddenShare": 0.86,
             "lowSugarLabel": true, "breakdown": [...], "reasons": ["..."]},
  "alternatives": [{"id", "name", "barcode", "hiddenCarbPer100g": 0.7, "score": 1,
                    "reason": "숨은 탄수화물 100g당 16.2g → 0.7g · 알룰로스 10.1g(혈당 영향 거의 없음)"}]
}
```

화면 제안: 소스는 1회 섭취량이 작아 `score`가 낮게 나오므로 **`hiddenCarbPer100g`와 `result.hiddenShare`(숨은 비중)**를 크게 보여주세요.
`nutritionEstimated`가 true면 '추정' 라벨을, `needsCheck`가 true면 '확인 필요' 라벨을 붙여 주세요.

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env      # 키 채우기
uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

## 배포 (Render)

1. GitHub에 **Private** 저장소로 올리기 (`.env`는 `.gitignore`로 제외됨)
2. Render → New → Blueprint → 저장소 선택 (`render.yaml` 자동 인식)
3. Environment에서 `ANTHROPIC_API_KEY`, `FOODSAFETY_KEY`, `DATA_GO_KR_KEY` 입력
4. 배포 후 `https://<서비스이름>.onrender.com/docs` 확인

무료 플랜은 15분간 요청이 없으면 잠들어요. 첫 요청이 30초~1분 걸릴 수 있으니 **시연 직전에 한 번 열어 깨워 두세요.**

## 데이터 출처

- 한국식품안전관리인증원 HACCP 제품이미지 및 포장지표기정보 (공공데이터포털)
- 식품의약품안전처 식품안전나라 C005·C002, 식품영양성분DB
- 팀이 직접 촬영한 저당 제품 포장지 사진 (Claude로 판독)
- 큐빅(CUBIG) SynTitan DTS로 정리한 데이터 기반 영양성분 추정
