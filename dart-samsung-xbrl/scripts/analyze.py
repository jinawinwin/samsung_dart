"""
재무 지표 계산 + 리포트/대시보드 데이터 생성 스크립트
====================================================

data/processed/financials.csv를 읽어:
1. 연도별 YoY 성장률, 영업이익률, 순이익률, ROE, 부채비율을 계산
2. 사람이 읽는 요약 리포트를 reports/latest.md 로 생성
3. 대시보드(docs/)에서 사용할 data.json 을 docs/data.json 으로 생성

금액 단위는 XBRL 원본 그대로(원 단위)이며, 리포트에서는 조 단위로 환산해 표시한다.
"""

import csv
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_CSV = os.path.join(BASE_DIR, "data", "processed", "financials.csv")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
REPORT_MD = os.path.join(REPORTS_DIR, "latest.md")
DASHBOARD_JSON = os.path.join(DOCS_DIR, "data.json")


def to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_rows():
    rows = []
    if not os.path.exists(PROCESSED_CSV):
        return rows
    with open(PROCESSED_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "fiscal_year": int(r["fiscal_year"]),
                "revenue": to_float(r.get("revenue")),
                "operating_income": to_float(r.get("operating_income")),
                "net_income": to_float(r.get("net_income")),
                "total_assets": to_float(r.get("total_assets")),
                "total_liabilities": to_float(r.get("total_liabilities")),
                "total_equity": to_float(r.get("total_equity")),
            })
    rows.sort(key=lambda r: r["fiscal_year"])
    return rows


def pct(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 2)


def yoy(curr, prev):
    if curr is None or prev in (None, 0):
        return None
    return round((curr - prev) / prev * 100, 2)


def krw_to_trillion(value):
    if value is None:
        return None
    return round(value / 1_000_000_000_000, 2)


def compute_metrics(rows):
    enriched = []
    prev = None
    for r in rows:
        m = dict(r)
        m["revenue_yoy_pct"] = yoy(r["revenue"], prev["revenue"]) if prev else None
        m["operating_income_yoy_pct"] = yoy(r["operating_income"], prev["operating_income"]) if prev else None
        m["net_income_yoy_pct"] = yoy(r["net_income"], prev["net_income"]) if prev else None
        m["operating_margin_pct"] = pct(r["operating_income"], r["revenue"])
        m["net_margin_pct"] = pct(r["net_income"], r["revenue"])
        m["roe_pct"] = pct(r["net_income"], r["total_equity"])
        m["roa_pct"] = pct(r["net_income"], r["total_assets"])
        m["debt_ratio_pct"] = pct(r["total_liabilities"], r["total_equity"])
        enriched.append(m)
        prev = r
    return enriched


def write_report_md(metrics):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    lines = []
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# 삼성전자 재무분석 자동 리포트")
    lines.append("")
    lines.append(f"_생성 시각: {generated_at}_")
    lines.append("")

    if not metrics:
        lines.append("분석할 데이터가 없습니다. 먼저 크롤링 및 파싱 스크립트를 실행하세요.")
    else:
        latest = metrics[-1]
        lines.append(f"## {latest['fiscal_year']}년 요약")
        lines.append("")
        lines.append(f"- 매출액: {krw_to_trillion(latest['revenue'])}조 원 "
                      f"(전년 대비 {latest['revenue_yoy_pct']}%)" if latest["revenue_yoy_pct"] is not None
                      else f"- 매출액: {krw_to_trillion(latest['revenue'])}조 원")
        lines.append(f"- 영업이익: {krw_to_trillion(latest['operating_income'])}조 원 "
                      f"(전년 대비 {latest['operating_income_yoy_pct']}%, 영업이익률 {latest['operating_margin_pct']}%)")
        lines.append(f"- 당기순이익: {krw_to_trillion(latest['net_income'])}조 원 "
                      f"(전년 대비 {latest['net_income_yoy_pct']}%, 순이익률 {latest['net_margin_pct']}%)")
        lines.append(f"- ROE: {latest['roe_pct']}%  /  ROA: {latest['roa_pct']}%  /  부채비율: {latest['debt_ratio_pct']}%")
        lines.append("")
        lines.append("## 연도별 상세 (단위: 조 원, %)")
        lines.append("")
        lines.append("| 연도 | 매출액 | 매출YoY | 영업이익 | 영업이익률 | 순이익 | 순이익률 | ROE | 부채비율 |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for m in metrics:
            lines.append(
                f"| {m['fiscal_year']} | {krw_to_trillion(m['revenue'])} | {m['revenue_yoy_pct']} | "
                f"{krw_to_trillion(m['operating_income'])} | {m['operating_margin_pct']} | "
                f"{krw_to_trillion(m['net_income'])} | {m['net_margin_pct']} | "
                f"{m['roe_pct']} | {m['debt_ratio_pct']} |"
            )
        lines.append("")
        lines.append("> 이 리포트는 DART 공시 XBRL 데이터를 자동 파싱하여 생성되었습니다. "
                      "택소노미 개정 등으로 일부 연도 값이 비어있거나 부정확할 수 있으니 "
                      "중요한 의사결정 전에는 원본 공시를 대조하시기 바랍니다.")

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"리포트 생성 완료: {REPORT_MD}")


def write_dashboard_json(metrics):
    os.makedirs(DOCS_DIR, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company": "삼성전자 (005930)",
        "years": metrics,
    }
    with open(DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"대시보드 데이터 생성 완료: {DASHBOARD_JSON}")


def main():
    rows = load_rows()
    metrics = compute_metrics(rows)
    write_report_md(metrics)
    write_dashboard_json(metrics)


if __name__ == "__main__":
    main()
