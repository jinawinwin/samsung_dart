"""
삼성전자 사업보고서 원본 데이터 수집 스크립트 (2000년 ~ 최신, 자동 증분 업데이트)
====================================================================

동작 순서
---------
1. corpCode.xml API로 종목코드(005930, 삼성전자)에 해당하는 corp_code를 찾는다.
2. list.json (공시검색) API로 지정된 연도 범위의 "사업보고서"(정기공시) 접수번호(rcept_no)를 찾는다.
3. 연도별로 이미 데이터가 저장되어 있으면 건너뛴다 (증분 업데이트).
4. fnlttXbrl.xml API로 재무제표 원본 XBRL 압축파일을 시도해서 받는다.
   - XBRL이 존재하지 않는(의무화 이전) 연도라면, document.xml API로
     원본 공시서류(비-XBRL 원문 zip)를 대신 받아 별도 폴더에 저장한다.

필요 환경변수
-------------
- DART_API_KEY      : OpenDART 인증키 (필수)
- START_YEAR        : 수집 시작 회계연도 (선택, 기본값 2000)
- END_YEAR          : 수집 종료 회계연도 (선택, 기본값: 현재연도)
- FORCE_REDOWNLOAD  : "1"로 설정하면 이미 받은 연도도 다시 받는다 (선택, 기본값: 미설정)

주기적으로(예: 매달) 이 스크립트를 다시 실행하면:
- 이미 받은 과거 연도는 건드리지 않고,
- 아직 없던 연도(예: 새로 제출된 최신 사업보고서)만 새로 채워 넣는다.
"""

import io
import os
import sys
import time
import zipfile
from datetime import datetime

import requests

DART_BASE = "https://opendart.fss.or.kr/api"
STOCK_CODE = "005930"  # 삼성전자 보통주 종목코드
PBLNTF_DETAIL_TY = "A001"  # 사업보고서 (정기공시 상세유형)
REPRT_CODE_ANNUAL = "11011"  # 사업보고서 보고서 코드
REQUEST_INTERVAL_SEC = 1.0  # API 호출 간 최소 대기시간

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
XBRL_DIR = os.path.join(DATA_DIR, "xbrl")
ORIGINAL_DOC_DIR = os.path.join(DATA_DIR, "original_docs")
CORP_CODE_XML_PATH = os.path.join(DATA_DIR, "CORPCODE.xml")


def get_api_key() -> str:
    key = os.environ.get("DART_API_KEY")
    if not key:
        print("오류: 환경변수 DART_API_KEY가 설정되어 있지 않습니다.", file=sys.stderr)
        sys.exit(1)
    return key


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(XBRL_DIR, exist_ok=True)
    os.makedirs(ORIGINAL_DOC_DIR, exist_ok=True)


def already_have_year(year: int) -> bool:
    """해당 연도의 데이터(XBRL 또는 원본 공시서류)가 이미 있는지 확인."""
    prefix = f"{year}_"
    for d in (XBRL_DIR, ORIGINAL_DOC_DIR):
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.startswith(prefix) and name.endswith(".zip"):
                return True
    return False


def download_corp_code_map(api_key: str) -> str:
    """전체 corp_code 목록을 받아 삼성전자(005930)의 corp_code를 반환한다."""
    print("[1/3] corpCode.xml 다운로드 중...")
    resp = requests.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=30)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")

    with open(CORP_CODE_XML_PATH, "wb") as f:
        f.write(xml_bytes)

    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if stock_code == STOCK_CODE:
            corp_code = item.findtext("corp_code").strip()
            corp_name = item.findtext("corp_name").strip()
            print(f"  -> 찾음: {corp_name} (corp_code={corp_code})")
            return corp_code

    print("오류: 종목코드 005930(삼성전자)에 해당하는 corp_code를 찾지 못했습니다.", file=sys.stderr)
    sys.exit(1)


def find_annual_report_rcept_no(api_key: str, corp_code: str, fiscal_year: int):
    """특정 회계연도의 사업보고서 접수번호(rcept_no)와 제출일을 찾는다."""
    bgn_de = f"{fiscal_year + 1}0101"
    end_de = f"{fiscal_year + 1}0630"  # 정정 제출 등을 감안해 넉넉히 6월까지 조회

    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "pblntf_detail_ty": PBLNTF_DETAIL_TY,
        "page_no": 1,
        "page_count": 100,
    }
    resp = requests.get(f"{DART_BASE}/list.json", params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("status") not in ("000",):
        # 013: 조회된 데이터가 없음 (해당 연도에 사업보고서 없음 - 정상적인 상황일 수 있음)
        if payload.get("status") != "013":
            print(f"  경고: {fiscal_year}년 공시검색 실패 - {payload.get('message')}")
        return None

    rows = payload.get("list", [])
    candidates = [r for r in rows if "사업보고서" in r.get("report_nm", "") and "정정" not in r.get("report_nm", "")]
    if not candidates:
        candidates = [r for r in rows if "사업보고서" in r.get("report_nm", "")]
    if not candidates:
        return None

    candidates.sort(key=lambda r: r.get("rcept_dt", ""))
    chosen = candidates[-1]
    print(f"  -> {fiscal_year}년: {chosen['report_nm']} (rcept_no={chosen['rcept_no']}, 제출일={chosen['rcept_dt']})")
    return chosen["rcept_no"]


def try_download_xbrl(api_key: str, fiscal_year: int, rcept_no: str) -> bool:
    """fnlttXbrl.xml로 원본 XBRL zip을 시도. 성공하면 True."""
    params = {
        "crtfc_key": api_key,
        "rcept_no": rcept_no,
        "reprt_code": REPRT_CODE_ANNUAL,
    }
    resp = requests.get(f"{DART_BASE}/fnlttXbrl.xml", params=params, timeout=60)
    resp.raise_for_status()

    if not resp.content.startswith(b"PK"):  # zip 파일은 'PK'로 시작; 아니면 에러 응답(JSON/XML)
        return False

    zip_filename = f"{fiscal_year}_{rcept_no}.zip"
    zip_path = os.path.join(XBRL_DIR, zip_filename)
    with open(zip_path, "wb") as f:
        f.write(resp.content)

    extract_dir = os.path.join(XBRL_DIR, f"{fiscal_year}_{rcept_no}")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        print(f"  -> XBRL 저장 완료: {zip_path}")
        return True
    except zipfile.BadZipFile:
        os.remove(zip_path)
        return False


def download_original_document(api_key: str, fiscal_year: int, rcept_no: str) -> bool:
    """document.xml로 원본 공시서류(비-XBRL) zip을 받는다. XBRL이 없는 옛날 연도용 폴백."""
    params = {"crtfc_key": api_key, "rcept_no": rcept_no}
    resp = requests.get(f"{DART_BASE}/document.xml", params=params, timeout=60)
    resp.raise_for_status()

    if not resp.content.startswith(b"PK"):
        print(f"  경고: {fiscal_year}년 원본 공시서류도 받지 못했습니다. (rcept_no={rcept_no})")
        return False

    zip_filename = f"{fiscal_year}_{rcept_no}.zip"
    zip_path = os.path.join(ORIGINAL_DOC_DIR, zip_filename)
    with open(zip_path, "wb") as f:
        f.write(resp.content)

    extract_dir = os.path.join(ORIGINAL_DOC_DIR, f"{fiscal_year}_{rcept_no}")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
        print(f"  -> 원본 공시서류(비-XBRL) 저장 완료: {zip_path}")
        return True
    except zipfile.BadZipFile:
        os.remove(zip_path)
        return False


def main():
    api_key = get_api_key()
    ensure_dirs()

    current_year = datetime.now().year
    start_year_env = (os.environ.get("START_YEAR") or "").strip()
    end_year_env = (os.environ.get("END_YEAR") or "").strip()
    start_year = int(start_year_env) if start_year_env else 2000
    end_year = int(end_year_env) if end_year_env else current_year
    force_redownload = os.environ.get("FORCE_REDOWNLOAD") == "1"

    print(f"수집 대상 회계연도: {start_year} ~ {end_year} (기존 데이터 재수집: {force_redownload})")

    corp_code = download_corp_code_map(api_key)
    time.sleep(REQUEST_INTERVAL_SEC)

    print("[2/3] 연도별 사업보고서 조회 및 다운로드 중...")
    xbrl_ok, original_ok, skipped, not_found, failed = 0, 0, 0, 0, 0

    for year in range(start_year, end_year + 1):
        if not force_redownload and already_have_year(year):
            print(f"  {year}년: 이미 존재 - 건너뜀")
            skipped += 1
            continue

        rcept_no = find_annual_report_rcept_no(api_key, corp_code, year)
        time.sleep(REQUEST_INTERVAL_SEC)
        if not rcept_no:
            not_found += 1
            continue

        if try_download_xbrl(api_key, year, rcept_no):
            xbrl_ok += 1
        else:
            time.sleep(REQUEST_INTERVAL_SEC)
            if download_original_document(api_key, year, rcept_no):
                original_ok += 1
            else:
                failed += 1
        time.sleep(REQUEST_INTERVAL_SEC)

    print("\n[3/3] 완료 요약")
    print(f"  - XBRL 원본 확보: {xbrl_ok}건")
    print(f"  - 원본 공시서류로 대체 확보: {original_ok}건")
    print(f"  - 이미 존재해서 건너뜀: {skipped}건")
    print(f"  - 해당 연도 사업보고서 없음: {not_found}건")
    print(f"  - 실패: {failed}건")


if __name__ == "__main__":
    main()
