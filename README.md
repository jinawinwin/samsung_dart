# Samsung Electronics DART Report Crawler (2000 ~ 최신, 자동 업데이트)

삼성전자(005930)의 사업보고서를 **2000년부터 최신까지** [OpenDART](https://opendart.fss.or.kr) API로 수집하고,
매달 자동 실행되어 **새로 제출되는 사업보고서를 계속 채워 넣는** GitHub Actions 기반 크롤러입니다.

## 동작 방식

1. `corpCode.xml` API로 삼성전자의 `corp_code`를 찾습니다.
2. `list.json`(공시검색) API로 각 회계연도의 "사업보고서" 접수번호(`rcept_no`)를 찾습니다.
3. **이미 해당 연도 데이터가 저장되어 있으면 건너뜁니다** (증분 업데이트 - 매번 처음부터 전부 다시 받지 않음).
4. `fnlttXbrl.xml` API로 **재무제표 원본 XBRL** 압축파일을 시도합니다.
   - 한국의 XBRL 공시는 단계적으로 의무화되었기 때문에, **오래된 연도(대략 2019년 이전)는 XBRL 원본이
     DART에 없을 수 있습니다.** 이 경우 `document.xml` API로 **원본 공시서류(비-XBRL 원문 zip)**를
     대신 받아와 `data/original_docs/`에 저장합니다.
   - XBRL을 받은 연도는 `data/xbrl/`에 저장됩니다.

## 폴더 구조 (실행 후)

```
data/
  CORPCODE.xml
  xbrl/
    2020_20210310000736.zip
    2020_20210310000736/         # 압축 해제된 내용
    2021_...zip
    ...
  original_docs/
    2005_...zip                  # XBRL이 없던 연도의 원본 공시서류
    2005_.../
    ...
```

## 최초 설정 (1회만)

1. 이 폴더 전체를 본인의 GitHub 저장소에 올립니다 (아래 "저장소에 올리는 방법" 참고).
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DART_API_KEY`
   - Value: OpenDART에서 발급받은 40자리 인증키
   (인증키가 노출되었다고 생각되면 OpenDART 사이트에서 재발급 받으세요.)
3. 저장소 **Settings → Actions → General → Workflow permissions**에서
   "Read and write permissions"를 선택합니다 (워크플로가 커밋/푸시할 수 있도록).

## 실행 방법

- **최초 1회 전체 수집**: Actions 탭 → `Crawl Samsung Electronics DART XBRL` →
  **Run workflow** 클릭. `start_year`/`end_year`를 비워두면 자동으로 2000년~현재연도 전체를 수집합니다.
  (2000년부터 약 25년치이므로 최초 실행은 다소 시간이 걸릴 수 있습니다.)
- **이후 자동 업데이트**: 별도 조작 없이 **매달 1일**에 자동 실행되며,
  이미 받은 연도는 건너뛰고 **새로 제출된 사업보고서만** 추가로 받아 커밋합니다.
  (실행 주기를 바꾸고 싶으면 `.github/workflows/crawl_dart.yml`의 `cron` 값을 수정하세요.
  사업보고서는 보통 3월에 제출되므로, 원하시면 3~4월에만 더 자주 도는 cron을 추가해도 됩니다.)
- **특정 연도를 다시 받고 싶을 때**: Actions 탭에서 수동 실행 시 `force_redownload`를
  `true`로 설정하면 지정한 연도 범위를 전부 다시 받습니다.

## 로컬에서 직접 실행하고 싶다면

```bash
pip install -r requirements.txt
export DART_API_KEY="여기에_인증키"
# 아래 둘은 생략 가능 (기본값: 2000 ~ 현재연도)
export START_YEAR=2000
export END_YEAR=2026
python scripts/crawl_dart_xbrl.py
```

## 저장소에 올리는 방법 (아직 GitHub 저장소가 없다면)

```bash
cd dart-samsung-xbrl
git init
git add .
git commit -m "init: DART report crawler"
git branch -M main
git remote add origin https://github.com/<본인계정>/<저장소이름>.git
git push -u origin main
```

이후 위 "최초 설정"의 2, 3번(Secret 등록, Actions 권한 설정)을 진행하면 됩니다.

## 참고 / 주의사항

- OpenDART는 요청 빈도 제한이 있어 스크립트 내에서 호출 사이 1초씩 대기합니다.
  2000~현재까지 전체를 처음 받을 때는 시간이 다소 걸립니다.
- 사업보고서는 회계연도 종료 후 통상 3월 중 제출되므로, 회계연도 `YYYY`에 대한 공시는
  `YYYY+1`년 1~6월 사이에서 검색합니다.
- 특정 연도에 정정 사업보고서가 여러 번 제출된 경우, 가장 마지막(최신) 건을 사용합니다.
- **XBRL 원본이 없는 옛날 연도**는 `document.zip`(원본 공시서류)로 대체 저장되며,
  이 파일은 구조화된 XBRL 태그가 아니라 원문 형태(HWP/PDF 변환본 등)일 수 있습니다.
- 저장소가 크게 자라날 수 있으니(특히 최초 25년치 수집 시), GitHub 저장소 용량 제한을 참고하세요.
