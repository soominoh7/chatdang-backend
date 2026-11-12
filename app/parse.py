"""원재료 문자열 파서 (노트북 02에서 옮김)"""
import re

OPEN, CLOSE = "([{", ")]}"

COUNTRIES = ("국|국내|수입|외국|미국|중국|호주|캐나다|베트남|태국|칠레|브라질|인도|독일|프랑스|이탈리아|스페인|"
             "뉴질랜드|러시아|아르헨티나|말레이시아|인도네시아|필리핀|터키|튀르키예|덴마크|네덜란드|일본|대만|"
             "헝가리|폴란드|우크라이나|미얀마|파키스탄|페루|멕시코|벨기에|영국|아일랜드|스위스|오스트리아|에콰도르|가나|코트디부아르")
ORIGIN = rf"(?:{COUNTRIES})산"


def is_empty(v):
    return v is None or str(v).strip() in ("", "알수없음", "None", "null", "-", "nan")


def split_outside_parens(text):
    """괄호 밖 쉼표로만 나누기"""
    parts, buf, depth = [], "", 0
    for ch in str(text or ""):
        if ch in OPEN:
            depth += 1
        elif ch in CLOSE:
            depth = max(depth - 1, 0)
        if ch == "," and depth == 0:
            if buf.strip():
                parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf.strip())
    return parts


def is_origin_or_amount(s):
    s = s.strip()
    if re.fullmatch(r"[\d.\s%]+", s) or re.match(rf"^{ORIGIN}\s*:", s):
        return True
    return bool(re.fullmatch(rf"(?:{ORIGIN}|{COUNTRIES})[\s\d.%]*(?:[\(\[].*[\)\]])?", s))


def parse_ingredient(item):
    item = item.strip()
    m = re.match(r"^(.*?)[\(\[\{](.*)[\)\]\}]\s*$", item)
    if not m:
        return {"name": item, "sub": []}
    name, inner = m.group(1).strip(), m.group(2)
    if all(is_origin_or_amount(x) for x in split_outside_parens(inner)):
        return {"name": name or item, "sub": []}
    subs = []
    for s in split_outside_parens(inner):
        s = s.strip()
        if "(" not in s and "[" not in s:
            s = re.sub(r"\s*:\s*" + ORIGIN + r".*$", "", s)
        if s and not is_origin_or_amount(s):
            subs.append(s)
    flat = []
    for s in subs:
        p = parse_ingredient(s)
        flat.append(p["name"])
        flat.extend(p["sub"])
    return {"name": name or item, "sub": flat}


def parse_rawmtrl(text):
    """원재료 문자열 → (상위 원재료 리스트, 하위 성분까지 펼친 리스트)"""
    if is_empty(text):
        return [], []
    top = [parse_ingredient(p) for p in split_outside_parens(text)]
    names = [t["name"] for t in top]
    flat = []
    for t in top:
        flat.append(t["name"])
        flat.extend(t["sub"])
    return names, flat
