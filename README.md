# Samsung Electronics DART Analytics (수집 → 분석 → 대시보드, 자동 업데이트)

[![대시보드 바로가기](https://img.shields.io/badge/🔗_대시보드_바로가기-jinawinwin.github.io%2Fsamsung__dart-1B2430?style=for-the-badge)](https://jinawinwin.github.io/samsung_dart/)
삼성전자(005930)의 사업보고서를 **2000년부터 최신까지** [OpenDART](https://opendart.fss.or.kr) API로 수집하고,
핵심 재무 계정을 파싱해 지표를 계산한 뒤, **GitHub Pages 대시보드**로 보여주는 완전 자동화 파이프라인입니다.
매달 자동 실행되어 새 데이터가 나오면 대시보드도 자동으로 갱신됩니다.

## 전체 파이프라인

매달 GitHub Actions가 순서대로 실행합니다.

1. **`scripts/crawl_dart_xbrl.py`** — DART에서 원본 XBRL(또는 원본 공시서류) 수집 → `data/xbrl/`, `data/original_docs/`
2. **`scripts/parse_xbrl.py`** — XBRL에서 매출액·영업이익·순이익·자산·부채·자본 추출 → `data/processed/financials.csv`
3. **`scripts/analyze.py`** — YoY 성장률, 영업이익률, 순이익률, ROE, ROA, 부채비율 계산
   - 사람이 읽는 리포트 → `reports/latest.md`
   - 대시보드용 데이터 → `docs/data.json`
4. 위 결과를 자동 커밋 → `docs/`가 GitHub Pages로 서빙되어 **대시보드가 자동 갱신**됩니다.

## 최초 설정 (1회만)

1. 이 폴더 전체를 본인의 **public** GitHub 저장소에 올립니다.
2. **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `DART_API_KEY` / Value: OpenDART 인증키
3. **Settings → Actions → General → Workflow permissions** → "Read and write permissions" 선택
4. **Settings → Pages**
   - Source: "Deploy from a branch"
   - Branch: `main` / 폴더: `/docs` 선택 후 저장
   - 잠시 후 `https://<계정>.github.io/<저장소이름>/` 주소가 생성됩니다.

## 실행 방법

- **최초 1회 전체 수집**: Actions 탭 → `Crawl Samsung Electronics DART XBRL` → **Run workflow**.
  `start_year`/`end_year`를 비워두면 2000년~현재연도 전체를 수집·파싱·분석까지 한 번에 처리합니다.
- **이후 자동 업데이트**: 매달 1일 자동 실행되며, 새로 제출된 사업보고서만 추가로 반영하고
  리포트/대시보드도 함께 갱신됩니다.
- **특정 연도 다시 받기**: 수동 실행 시 `force_redownload`를 `true`로 지정.

## 대시보드 보기

Pages 설정 후 `https://<계정>.github.io/<저장소이름>/`로 접속하면 됩니다.
연도별 매출·영업이익·순이익 추이 차트, 수익성 지표(영업이익률/순이익률/ROE/ROA/부채비율) 차트,
전체 연도 표를 볼 수 있습니다. 데이터는 `docs/data.json`을 그대로 읽어 그리므로,
저장소에 반영된 최신 값이 곧 화면에 보이는 값입니다.

## 자동 리포트 확인

매 실행마다 `reports/latest.md`가 최신 내용으로 갱신됩니다. GitHub 저장소에서 이 파일을 열어보면
가장 최근 연도 요약과 연도별 표를 마크다운으로 바로 읽을 수 있습니다.

## 필요할 때 대화로 분석 요청하기 (Claude)

저장소가 public이므로, 다음처럼 하시면 언제든 최신 데이터로 대화 분석을 요청할 수 있습니다.

- `docs/data.json` 또는 `data/processed/financials.csv`의 **raw 링크**
  (예: `https://raw.githubusercontent.com/<계정>/<저장소>/main/docs/data.json`)를 대화에 붙여넣고
  "이 데이터로 최근 3개년 수익성 변화 분석해줘" 같이 요청하시면 그 자리에서 분석해 드립니다.
- 또는 `reports/latest.md`의 GitHub 링크를 붙여넣고 요약/해석을 요청하셔도 됩니다.

## 로컬에서 전체 파이프라인 직접 실행

```bash
pip install -r requirements.txt
export DART_API_KEY="여기에_인증키"
python scripts/crawl_dart_xbrl.py   # 수집
python scripts/parse_xbrl.py        # 파싱
python scripts/analyze.py           # 지표 계산 + 리포트/대시보드 데이터 생성
# docs/index.html을 브라우저로 직접 열면 로컬에서도 대시보드 확인 가능
```

## 저장소에 올리는 방법 (아직 GitHub 저장소가 없다면)

```bash
cd dart-samsung-xbrl
git init
git add .
git commit -m "init: DART analytics pipeline"
git branch -M main
git remote add origin https://github.com/<본인계정>/<저장소이름>.git
git push -u origin main
```

## 참고 / 주의사항

- OpenDART는 요청 빈도 제한이 있어 스크립트 내에서 호출 사이 1초씩 대기합니다.
- 사업보고서는 회계연도 종료 후 통상 3월 중 제출되므로, 회계연도 `YYYY`의 공시는
  `YYYY+1`년 1~6월 사이에서 검색합니다.
- **XBRL 원본이 없는 옛날 연도**는 `data/original_docs/`에 원본 공시서류로 대체 저장되며,
  이 연도는 `financials.csv`에 값이 비어있을 수 있습니다 (파싱 대상이 XBRL이기 때문).
- **파싱은 휴리스틱입니다.** 한국 상장사 XBRL 택소노미는 연도/개정에 따라 태그 구성이 조금씩
  달라질 수 있어, 일부 연도의 값이 비거나 부정확할 수 있습니다. 중요한 의사결정 전에는
  `reports/latest.md`나 대시보드 수치를 원본 공시(DART)와 대조해 확인하시길 권합니다.
- 저장소가 public이므로 XBRL 원본, 리포트, 대시보드 데이터가 모두 공개됩니다.
  (DART 공시 자체가 이미 공개 정보이므로 데이터 자체의 민감도는 낮지만, 참고해 주세요.)
