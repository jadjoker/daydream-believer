import os
import httpx
import asyncio
from typing import Optional, Dict

FRED_KEY = os.getenv("FRED_API_KEY", "")
BASE = "https://api.stlouisfed.org/fred"

# Series IDs
_CPI       = "CPIAUCSL"           # Consumer Price Index (monthly)
_FED_RATE  = "FEDFUNDS"           # Federal Funds Effective Rate (monthly)
_UNEMP     = "UNRATE"             # Unemployment Rate (monthly)
_GDP       = "A191RL1Q225SBEA"    # Real GDP growth, annualized % (quarterly)


async def _get_observations(series_id: str, limit: int = 2) -> list:
    if not FRED_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": FRED_KEY,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
            )
            r.raise_for_status()
            return r.json().get("observations", [])
    except Exception as e:
        print(f"[FRED] error {series_id}: {e}")
        return []


def _val(obs: list, index: int = 0) -> Optional[float]:
    try:
        v = (obs[index] or {}).get("value", ".")
        return float(v) if v not in (".", None, "") else None
    except (IndexError, ValueError, TypeError):
        return None


def _date(obs: list, index: int = 0) -> str:
    try:
        return (obs[index] or {}).get("date", "")
    except IndexError:
        return ""


async def get_macro_snapshot() -> Dict:
    """
    Fetch key US macro indicators from FRED.
    All series are monthly/quarterly so results are cached for 6h in the caller.
    Returns empty-safe dict — all values may be None if FRED_API_KEY is unset.
    """
    cpi_obs, fed_obs, unemp_obs, gdp_obs = await asyncio.gather(
        _get_observations(_CPI,      limit=13),   # 13 months → compute YoY
        _get_observations(_FED_RATE, limit=1),
        _get_observations(_UNEMP,    limit=1),
        _get_observations(_GDP,      limit=1),
        return_exceptions=True,
    )

    # CPI year-over-year %
    cpi_yoy = None
    if isinstance(cpi_obs, list) and len(cpi_obs) >= 13:
        current   = _val(cpi_obs, 0)
        year_ago  = _val(cpi_obs, 12)
        if current and year_ago and year_ago != 0:
            cpi_yoy = round((current - year_ago) / year_ago * 100, 2)

    fed_rate    = _val(fed_obs,   0) if isinstance(fed_obs,   list) else None
    unemployment= _val(unemp_obs, 0) if isinstance(unemp_obs, list) else None
    gdp_growth  = _val(gdp_obs,   0) if isinstance(gdp_obs,   list) else None
    gdp_date    = _date(gdp_obs,  0) if isinstance(gdp_obs,   list) else ""
    fed_date    = _date(fed_obs,  0) if isinstance(fed_obs,   list) else ""

    # Plain-English policy stance for the AI prompt
    policy_stance = ""
    if fed_rate is not None and cpi_yoy is not None:
        real_rate = fed_rate - cpi_yoy
        if real_rate > 1.5:
            policy_stance = "Highly restrictive (real rate {:.1f}%) — headwind for rate-sensitive sectors & long-duration growth".format(real_rate)
        elif real_rate > 0:
            policy_stance = "Mildly restrictive (real rate {:.1f}%) — neutral to slight headwind for growth multiples".format(real_rate)
        elif real_rate > -1:
            policy_stance = "Roughly neutral (real rate {:.1f}%)".format(real_rate)
        else:
            policy_stance = "Accommodative (real rate {:.1f}%) — supportive for growth and risk assets".format(real_rate)

    inflation_trend = ""
    if cpi_yoy is not None:
        if cpi_yoy > 4:
            inflation_trend = "elevated inflation — Fed hawkish risk; avoid long-duration, favor real assets & pricing-power businesses"
        elif cpi_yoy > 2.5:
            inflation_trend = "above-target inflation — Fed likely on hold; watch rate-sensitive sectors"
        elif cpi_yoy > 1.5:
            inflation_trend = "near-target inflation — balanced environment"
        else:
            inflation_trend = "below-target inflation — potential for rate cuts; positive for bonds and growth multiples"

    return {
        "cpi_yoy":        cpi_yoy,
        "fed_rate":       fed_rate,
        "unemployment":   unemployment,
        "gdp_growth":     gdp_growth,
        "gdp_date":       gdp_date,
        "fed_date":       fed_date,
        "policy_stance":  policy_stance,
        "inflation_trend":inflation_trend,
    }
