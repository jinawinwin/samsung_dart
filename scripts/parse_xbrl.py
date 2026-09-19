"""
XBRL 원본 파일에서 핵심 재무 계정을 뽑아 연도별 CSV로 정리하는 스크립트
====================================================================

data/xbrl/{year}_{rcept_no}/ 폴더 안의 XBRL 인스턴스 문서(.xbrl 또는 확장자가
xbrl 계열인 xml 파일)를 찾아, 아래 핵심 계정(concept)의 "연결(CFS), 세그먼트 없음,
당해 회계연도 기준" 값을 추출한다.

추출 대상 계정 (K-IFRS 표준 태그의 로컬네임 기준, 네임스페이스 무시)
- Revenue                      : 매출액
- OperatingIncomeLoss          : 영업이익(손실)
- ProfitLoss                   : 당기순이익(손실)
- Assets                       : 자산총계
- Liabilities                  : 부채총계
- Equity                       : 자본총계

주의
----
- 한국 상장사 XBRL 택소노미는 연도/개정에 따라 태그 구성이 조금씩 다를 수 있어
  이 스크립트는 "최대한 찾아본다" 수준의 휴리스틱입니다. 값이 비어있거나
  이상해 보이면 해당 연도의 원본 XBRL을 직접 열어 태그명을 확인해야 할 수 있습니다.
- 세그먼트(사업부문별) 값은 제외하고, 회사 전체(연결 기준) 값만 추출하려고 시도합니다.

출력
----
data/processed/financials.csv  (연도, 매출액, 영업이익, 당기순이익, 자산총계, 부채총계, 자본총계)
"""

import csv
import os
import re
import xml.etree.ElementTree as ET
from glob import glob

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
XBRL_DIR = os.path.join(DATA_DIR, "xbrl")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
OUTPUT_CSV = os.path.join(PROCESSED_DIR, "financials.csv")

# (컬럼명, 찾을 태그 로컬네임 후보들 - 여러 후보 중 먼저 발견되는 것 사용)
TARGET_CONCEPTS = {
    "revenue": ["Revenue", "revenue", "RevenueFromContractsWithCustomers"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["ProfitLoss"],
    "total_assets": ["Assets"],
    "total_liabilities": ["Liabilities"],
    "total_equity": ["Equity"],
}

DURATION_CONCEPTS = {"revenue", "operating_income", "net_income"}  # 기간(duration) 값
INSTANT_CONCEPTS = {"total_assets", "total_liabilities", "total_equity"}  # 시점(instant) 값


def local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def find_instance_file(extract_dir: str):
    """압축 해제된 폴더에서 XBRL 인스턴스 문서로 보이는 파일을 찾는다."""
    candidates = []
    for path in glob(os.path.join(extract_dir, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        lower = path.lower()
        if lower.endswith((".xbrl", ".xml")):
            candidates.append(path)

    # xbrli:xbrl 루트를 가진 파일을 우선 (실제 인스턴스 문서)
    for path in candidates:
        try:
            for _event, elem in ET.iterparse(path, events=("start",)):
                if local_name(elem.tag) == "xbrl":
                    return path
                break
        except ET.ParseError:
            continue
    return None


def parse_contexts(root):
    """context id -> {'instant':..., 'start':..., 'end':..., 'has_segment': bool}"""
    contexts = {}
    for ctx in root.iter():
        if local_name(ctx.tag) != "context":
            continue
        ctx_id = ctx.get("id")
        info = {"instant": None, "start": None, "end": None, "has_segment": False}
        for child in ctx.iter():
            name = local_name(child.tag)
            if name == "instant":
                info["instant"] = (child.text or "").strip()
            elif name == "startDate":
                info["start"] = (child.text or "").strip()
            elif name == "endDate":
                info["end"] = (child.text or "").strip()
            elif name == "segment":
                info["has_segment"] = True
        contexts[ctx_id] = info
    return contexts


def is_full_year_duration(start: str, end: str) -> bool:
    if not start or not end:
        return False
    try:
        sy, sm, sd = [int(x) for x in start.split("-")]
        ey, em, ed = [int(x) for x in end.split("-")]
    except ValueError:
        return False
    return sm == 1 and sd == 1 and em == 12 and ed == 31 and ey == sy


def extract_year_data(instance_path: str, fiscal_year: int) -> dict:
    result = {key: None for key in TARGET_CONCEPTS}
    try:
        tree = ET.parse(instance_path)
    except ET.ParseError:
        return result
    root = tree.getroot()
    contexts = parse_contexts(root)

    for key, tag_candidates in TARGET_CONCEPTS.items():
        is_duration = key in DURATION_CONCEPTS
        found_value = None
        for elem in root.iter():
            name = local_name(elem.tag)
            if name not in tag_candidates:
                continue
            ctx_ref = elem.get("contextRef")
            if not ctx_ref or ctx_ref not in contexts:
                continue
            ctx = contexts[ctx_ref]
            if ctx["has_segment"]:
                continue  # 세그먼트(부문별) 값은 제외, 회사 전체 값만
            if is_duration:
                if not is_full_year_duration(ctx["start"], ctx["end"]):
                    continue
                if not (ctx["end"] or "").startswith(str(fiscal_year)):
                    continue
            else:
                if not ctx["instant"] or not ctx["instant"].startswith(str(fiscal_year)):
                    continue
            text = (elem.text or "").strip()
            if not text:
                continue
            try:
                value = float(text)
            except ValueError:
                continue
            # sign 속성(부호 반전) 처리
            if elem.get("sign") == "-":
                value = -value
            found_value = value
            break
        result[key] = found_value
    return result


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    if not os.path.isdir(XBRL_DIR):
        print("경고: data/xbrl 폴더가 없습니다. 먼저 크롤링 스크립트를 실행하세요.")
        return

    rows = []
    for entry in sorted(os.listdir(XBRL_DIR)):
        full_path = os.path.join(XBRL_DIR, entry)
        if not os.path.isdir(full_path):
            continue
        m = re.match(r"^(\d{4})_", entry)
        if not m:
            continue
        fiscal_year = int(m.group(1))

        instance_file = find_instance_file(full_path)
        if not instance_file:
            print(f"  {fiscal_year}년: XBRL 인스턴스 문서를 찾지 못함 - 건너뜀 ({entry})")
            continue

        data = extract_year_data(instance_file, fiscal_year)
        data["fiscal_year"] = fiscal_year
        rows.append(data)
        print(f"  {fiscal_year}년: 매출액={data['revenue']}, 영업이익={data['operating_income']}, 순이익={data['net_income']}")

    rows.sort(key=lambda r: r["fiscal_year"])

    fieldnames = ["fiscal_year", "revenue", "operating_income", "net_income",
                  "total_assets", "total_liabilities", "total_equity"]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})

    print(f"\n완료: {len(rows)}개 연도 파싱 -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
