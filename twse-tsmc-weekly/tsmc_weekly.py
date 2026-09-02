#!/usr/bin/env python3
"""
抓取台灣證券交易所（TWSE）台積電（2330）本週每日股價。

資料來源：
https://www.twse.com.tw/exchangeReport/STOCK_DAY

特色：
1. 僅使用 Python 標準函式庫，不需要額外安裝套件。
2. 自動以台北時間判斷「本週」。
3. 若本週跨月份，會自動抓取前後兩個月份，避免漏掉週一資料。
4. 預設抓台積電 2330，也可用 --stock 查詢其他上市股票。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
DEFAULT_STOCK_NO = "2330"
TAIPEI_TZ = timezone(timedelta(hours=8))


def get_taipei_today() -> date:
    """取得台北時區今天日期。"""
    return datetime.now(TAIPEI_TZ).date()


def get_week_range(target_date: date) -> tuple[date, date]:
    """
    取得 target_date 所在週的查詢範圍。

    週一視為一週開始，結束日期最多到 target_date，
    因此不會把尚未發生的未來交易日列入範圍。
    """
    week_start = target_date - timedelta(days=target_date.weekday())
    return week_start, target_date


def get_month_anchors(start_date: date, end_date: date) -> list[date]:
    """
    取得查詢範圍涵蓋到的月份。

    TWSE STOCK_DAY API 一次回傳一整個月份，因此若本週跨月，
    必須分別抓兩個月份才不會漏掉資料。
    """
    anchors: list[date] = []
    current = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)

    while current <= last:
        anchors.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return anchors


def fetch_monthly_stock(stock_no: str, month_anchor: date) -> dict[str, Any]:
    """
    呼叫 TWSE STOCK_DAY API，取得指定股票某月份每日成交資訊。

    Args:
        stock_no: 股票代號，例如台積電為 2330。
        month_anchor: 指定月份中的任一天；程式固定傳該月 1 日。

    Returns:
        TWSE 回傳的 JSON 物件。

    Raises:
        RuntimeError: 網路錯誤、HTTP 錯誤、JSON 格式錯誤或 TWSE 回傳非 OK。
    """
    query = urlencode(
        {
            "response": "json",
            "date": month_anchor.strftime("%Y%m%d"),
            "stockNo": stock_no,
        }
    )
    url = f"{TWSE_STOCK_DAY_URL}?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; twse-weekly-stock/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"TWSE HTTP 錯誤：{exc.code} {exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"無法連線 TWSE：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("TWSE 回傳內容不是有效 JSON。") from exc

    if payload.get("stat") != "OK":
        message = payload.get("stat") or payload.get("message") or "未知錯誤"
        raise RuntimeError(f"TWSE 查詢失敗：{message}")

    return payload


def parse_roc_date(value: str) -> date:
    """
    將民國日期（例如 115/09/02）轉成西元 date。

    TWSE STOCK_DAY 的日期欄位使用民國年格式。
    """
    clean_value = value.strip().replace("*", "")
    roc_year, month, day = (int(part) for part in clean_value.split("/"))
    return date(roc_year + 1911, month, day)


def collect_weekly_rows(
    stock_no: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    """
    抓取並整理指定日期區間內的每日股價資料。

    回傳欄位：
    date、volume、turnover、open、high、low、close、change、transactions。
    """
    result: list[dict[str, str]] = []
    seen_dates: set[date] = set()

    for month_anchor in get_month_anchors(start_date, end_date):
        payload = fetch_monthly_stock(stock_no, month_anchor)

        for row in payload.get("data", []):
            if len(row) < 9:
                continue

            trading_date = parse_roc_date(row[0])
            if not (start_date <= trading_date <= end_date):
                continue
            if trading_date in seen_dates:
                continue

            seen_dates.add(trading_date)
            result.append(
                {
                    "date": trading_date.isoformat(),
                    "volume": row[1],
                    "turnover": row[2],
                    "open": row[3],
                    "high": row[4],
                    "low": row[5],
                    "close": row[6],
                    "change": row[7],
                    "transactions": row[8],
                }
            )

    result.sort(key=lambda item: item["date"])
    return result


def print_table(
    stock_no: str,
    start_date: date,
    end_date: date,
    rows: list[dict[str, str]],
) -> None:
    """將本週股價以簡潔表格輸出到終端機。"""
    print(f"\n股票代號：{stock_no}")
    print(f"查詢區間：{start_date.isoformat()} ~ {end_date.isoformat()}")

    if not rows:
        print("本週目前沒有交易資料。")
        return

    headers = ("日期", "開盤", "最高", "最低", "收盤", "漲跌", "成交股數")
    values = [
        (
            row["date"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["change"],
            row["volume"],
        )
        for row in rows
    ]

    widths = [
        max(len(headers[index]), *(len(item[index]) for item in values))
        for index in range(len(headers))
    ]

    def format_row(items: tuple[str, ...]) -> str:
        return " | ".join(
            value.ljust(widths[index])
            for index, value in enumerate(items)
        )

    print(format_row(headers))
    print("-+-".join("-" * width for width in widths))
    for item in values:
        print(format_row(item))


def parse_args() -> argparse.Namespace:
    """解析命令列參數。"""
    parser = argparse.ArgumentParser(
        description="抓取 TWSE 台積電（預設 2330）本週每日股價。"
    )
    parser.add_argument(
        "--stock",
        default=DEFAULT_STOCK_NO,
        help="股票代號，預設 2330。",
    )
    parser.add_argument(
        "--date",
        help="指定基準日期 YYYY-MM-DD；未指定時使用台北今天日期。",
    )
    return parser.parse_args()


def parse_target_date(value: str | None) -> date:
    """解析 --date；未指定時回傳台北今天日期。"""
    if not value:
        return get_taipei_today()

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("--date 格式必須是 YYYY-MM-DD。") from exc


def main() -> int:
    """程式進入點。"""
    args = parse_args()

    try:
        target_date = parse_target_date(args.date)
        week_start, week_end = get_week_range(target_date)
        stock_no = args.stock.strip()

        if not stock_no.isdigit():
            raise ValueError("股票代號必須全部為數字。")

        rows = collect_weekly_rows(stock_no, week_start, week_end)
        print_table(stock_no, week_start, week_end, rows)
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
