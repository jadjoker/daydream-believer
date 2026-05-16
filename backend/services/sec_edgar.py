import httpx
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta

BASE = "https://data.sec.gov"
HEADERS = {"User-Agent": "DaydreamBeliever jadbraveheart@gmail.com"}


async def _get(path: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
            r = await client.get(f"{BASE}{path}")
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        print(f"[SEC] error {path}: {e}")
    return None


async def get_cik_for_ticker(ticker: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            r = await client.get("https://www.sec.gov/files/company_tickers.json")
            if r.status_code == 200:
                data = r.json()
                for _, co in data.items():
                    if co.get("ticker", "").upper() == ticker.upper():
                        return str(co["cik_str"]).zfill(10)
    except Exception as e:
        print(f"[SEC] CIK lookup error: {e}")
    return None


async def get_insider_transactions(ticker: str) -> List[Dict]:
    cik = await get_cik_for_ticker(ticker)
    if not cik:
        return []

    data = await _get(f"/submissions/CIK{cik}.json")
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    acc_nums = filings.get("accessionNumber", [])

    trades = []
    for i, form in enumerate(forms):
        if form in ("4", "4/A") and i < len(dates):
            trades.append({
                "ticker": ticker.upper(),
                "company": data.get("name", ticker),
                "form": form,
                "filing_date": dates[i] if i < len(dates) else "",
                "accession": acc_nums[i] if i < len(acc_nums) else "",
                "insider_name": "See SEC filing",
                "insider_title": "",
                "trade_type": "Unknown",
                "shares": 0,
                "price": 0.0,
                "value": 0.0,
                "trade_date": dates[i] if i < len(dates) else "",
                "filed_date": dates[i] if i < len(dates) else "",
            })
        if len(trades) >= 20:
            break

    return trades


async def get_recent_filings(ticker: str, form_type: str = "8-K") -> List[Dict]:
    cik = await get_cik_for_ticker(ticker)
    if not cik:
        return []

    data = await _get(f"/submissions/CIK{cik}.json")
    if not data:
        return []

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    descriptions = filings.get("primaryDocument", [])
    acc_nums = filings.get("accessionNumber", [])

    results = []
    for i, form in enumerate(forms):
        if form == form_type or (form_type == "all"):
            results.append({
                "form": form,
                "date": dates[i] if i < len(dates) else "",
                "description": descriptions[i] if i < len(descriptions) else "",
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nums[i].replace('-', '')}/{descriptions[i]}" if i < len(acc_nums) else "",
            })
        if len(results) >= 10:
            break

    return results


async def get_openinsider_trades(ticker: str) -> List[Dict]:
    """Scrape OpenInsider for insider trades"""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"http://openinsider.com/screener",
                params={"s": ticker, "o": "", "pl": "", "ph": "", "ll": "", "lh": "", "fd": "30", "td": "", "tdr": "", "fdlyl": "", "fdlyh": "", "daysago": "30", "xp": "1", "vl": "10", "vh": "", "ocl": "", "och": "", "sic1": "-1", "sicl": "100", "sich": "9999", "grp": "0", "nfl": "", "nfh": "", "nil": "", "nih": "", "nol": "", "noh": "", "v2l": "", "v2h": "", "oc2l": "", "oc2h": "", "sortcol": "0", "cnt": "20", "action": "1"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code != 200:
                return []
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "lxml")
            table = soup.find("table", {"class": "tinytable"})
            if not table:
                return []
            rows = table.find_all("tr")[1:]
            trades = []
            for row in rows[:20]:
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 11:
                    trades.append({
                        "ticker": ticker.upper(),
                        "company": cols[3] if len(cols) > 3 else "",
                        "insider_name": cols[4] if len(cols) > 4 else "",
                        "insider_title": cols[5] if len(cols) > 5 else "",
                        "trade_type": cols[6] if len(cols) > 6 else "",
                        "price": _parse_num(cols[7]) if len(cols) > 7 else 0,
                        "shares": int(_parse_num(cols[8])) if len(cols) > 8 else 0,
                        "value": _parse_num(cols[9]) if len(cols) > 9 else 0,
                        "filed_date": cols[1] if len(cols) > 1 else "",
                        "trade_date": cols[2] if len(cols) > 2 else "",
                    })
            return trades
    except Exception as e:
        print(f"[OpenInsider] error for {ticker}: {e}")
        return []


def _parse_num(s: str) -> float:
    try:
        return float(s.replace(",", "").replace("$", "").replace("+", "").replace("%", "") or "0")
    except Exception:
        return 0.0
