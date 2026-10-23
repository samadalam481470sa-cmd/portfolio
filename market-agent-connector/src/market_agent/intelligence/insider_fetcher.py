"""Insider trading data from OpenInsider.com (SEC Form 4 filings).

OpenInsider aggregates insider buy/sell transactions filed with the SEC.
Source: http://openinsider.com — data from sec.gov Form 3, 4, 5.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

import httpx

from market_agent.ai.models import InsiderTrade, InsiderTradeSummary

OPENINSIDER_URL = "http://openinsider.com/screener"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MarketAgent/1.0)"}


class _TableParser(HTMLParser):
    """Parse OpenInsider tinytable rows."""

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []
        self.table_class = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "table" and attrs_dict.get("class") == "tinytable":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag == "td":
            self.in_cell = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.in_table:
            self.in_table = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            # Optional leading flag cells are often empty and get dropped, so
            # accept any row long enough to hold a full transaction record.
            if len(self.current_row) >= 10:
                self.rows.append(self.current_row)
        elif tag == "td" and self.in_cell:
            self.in_cell = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            text = data.strip()
            if text:
                self.current_row.append(text)


class InsiderFetcher:
    """Fetch insider trade history from OpenInsider.com."""

    def __init__(self, finnhub_api_key: str = "") -> None:
        self.finnhub_api_key = finnhub_api_key
        self._client = httpx.AsyncClient(timeout=25.0, headers=HEADERS, follow_redirects=True)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_trades(
        self,
        symbol: str,
        limit: int = 20,
        days: int = 365,
        purchases_only: bool = False,
        sales_only: bool = False,
    ) -> list[InsiderTrade]:
        symbol = symbol.upper().strip()
        trades = await self._fetch_openinsider(symbol, limit, days, purchases_only, sales_only)
        if not trades and self.finnhub_api_key:
            trades = await self._fetch_finnhub(symbol, limit)
        return trades

    async def get_summary(self, symbol: str, days: int = 90) -> InsiderTradeSummary:
        trades = await self.get_trades(symbol, limit=100, days=days)
        return _summarize(symbol, trades, days)

    async def get_market_wide_buys(
        self,
        days: int = 7,
        min_value_usd: int = 100_000,
        limit: int = 40,
    ) -> list[InsiderTrade]:
        """Find recent insider PURCHASES across the entire market.

        Insider buying is a stronger signal than selling (execs sell for many
        reasons, but they buy for one). This surfaces fresh conviction buys.
        """
        params: dict[str, Any] = {
            "s": "",
            "o": "",
            "pl": "",
            "ph": "",
            "ll": "",
            "lh": "",
            "fd": days,
            "fdr": "",
            "td": 0,
            "tdr": "",
            "xp": 1,  # purchases only
            "vl": max(1, min_value_usd // 1000),  # min value in $K
            "vh": "",
            "sic1": -1,
            "sicl": 100,
            "sich": 9999,
            "grp": 0,
            "sortcol": 0,
            "cnt": min(limit * 3, 300),
            "page": 1,
        }
        try:
            resp = await self._client.get(OPENINSIDER_URL, params=params)
            resp.raise_for_status()
        except Exception:
            return []

        parser = _TableParser()
        parser.feed(resp.text)
        trades: list[InsiderTrade] = []
        for row in parser.rows:
            trade = _parse_row_any(row)
            if trade and trade.is_purchase and (trade.value or 0) >= min_value_usd:
                trades.append(trade)
            if len(trades) >= limit:
                break
        return trades

    async def get_cluster_buys(
        self, days: int = 14, min_insiders: int = 2, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find stocks where MULTIPLE insiders bought recently (strongest signal)."""
        trades = await self.get_market_wide_buys(days=days, min_value_usd=25_000, limit=200)

        by_symbol: dict[str, list[InsiderTrade]] = {}
        for t in trades:
            by_symbol.setdefault(t.symbol, []).append(t)

        clusters = []
        for symbol, syms_trades in by_symbol.items():
            unique_insiders = {t.insider_name for t in syms_trades}
            if len(unique_insiders) < min_insiders:
                continue
            total_value = sum(t.value or 0 for t in syms_trades)
            clusters.append({
                "symbol": symbol,
                "insider_count": len(unique_insiders),
                "trade_count": len(syms_trades),
                "total_value_usd": round(total_value, 2),
                "insiders": sorted(unique_insiders)[:5],
                "latest_date": max(t.trade_date for t in syms_trades),
                "trades": [t.model_dump() for t in syms_trades[:5]],
            })

        clusters.sort(key=lambda c: (c["insider_count"], c["total_value_usd"]), reverse=True)
        return clusters[:limit]

    async def _fetch_openinsider(
        self,
        symbol: str,
        limit: int,
        days: int,
        purchases_only: bool,
        sales_only: bool,
    ) -> list[InsiderTrade]:
        params: dict[str, Any] = {
            "s": symbol,
            "o": "",
            "pl": "",
            "ph": "",
            "ll": "",
            "lh": "",
            "fd": days,
            "fdr": "",
            "td": 0,
            "tdr": "",
            "val": 0,
            "vl": 0,
            "vh": "",
            "ocl": "",
            "och": "",
            "sic1": -1,
            "sicl": 100,
            "sich": 9999,
            "grp": 0,
            "sortcol": 0,
            "cnt": min(limit, 100),
            "page": 1,
        }
        if purchases_only:
            params["xp"] = 1
        if sales_only:
            params["xs"] = 1

        try:
            resp = await self._client.get(OPENINSIDER_URL, params=params)
            resp.raise_for_status()
        except Exception:
            return []

        parser = _TableParser()
        parser.feed(resp.text)
        trades: list[InsiderTrade] = []

        for row in parser.rows:
            trade = _parse_row(row, symbol)
            if trade:
                trades.append(trade)
            if len(trades) >= limit:
                break

        return trades

    async def _fetch_finnhub(self, symbol: str, limit: int) -> list[InsiderTrade]:
        try:
            resp = await self._client.get(
                "https://finnhub.io/api/v1/stock/insider-transactions",
                params={"symbol": symbol, "token": self.finnhub_api_key},
            )
            if resp.status_code != 200:
                return []
            data = resp.json().get("data", [])
            trades = []
            for item in data[:limit]:
                change = item.get("change", 0)
                trades.append(
                    InsiderTrade(
                        symbol=symbol,
                        insider_name=item.get("name", ""),
                        title="",
                        trade_type="P - Purchase" if change > 0 else "S - Sale",
                        trade_date=item.get("transactionDate", "")[:10],
                        filing_date=item.get("filingDate", "")[:10],
                        price=item.get("transactionPrice"),
                        quantity=abs(int(change)) if change else 0,
                        value=abs(change * (item.get("transactionPrice") or 0)) if change else None,
                        source="finnhub",
                    )
                )
            return trades
        except Exception:
            return []


def _parse_row(cells: list[str], expected_symbol: str) -> InsiderTrade | None:
    """Parse OpenInsider table row by locating the ticker column."""
    cells = [c.strip() for c in cells if c.strip()]
    if len(cells) < 10:
        return None

    ticker_idx = None
    for i, c in enumerate(cells):
        if c.upper() == expected_symbol.upper():
            ticker_idx = i
            break
    if ticker_idx is None or ticker_idx < 2:
        return None

    try:
        filing_date = cells[ticker_idx - 2]
        trade_date = cells[ticker_idx - 1]
        ticker = cells[ticker_idx]
        insider = cells[ticker_idx + 1]
        title = cells[ticker_idx + 2]
        trade_type = cells[ticker_idx + 3]
        price = _parse_money(cells[ticker_idx + 4])
        qty = _parse_qty(cells[ticker_idx + 5])
        owned = _parse_qty(cells[ticker_idx + 6]) if len(cells) > ticker_idx + 6 else None
        delta_own = cells[ticker_idx + 7] if len(cells) > ticker_idx + 7 else ""
        value = _parse_money(cells[ticker_idx + 8]) if len(cells) > ticker_idx + 8 else None
    except (IndexError, ValueError):
        return None

    if not re.match(r"\d{4}-\d{2}-\d{2}", trade_date):
        return None

    return InsiderTrade(
        symbol=ticker.upper(),
        insider_name=insider,
        title=title,
        trade_type=trade_type,
        trade_date=trade_date,
        filing_date=filing_date,
        price=price,
        quantity=qty,
        shares_owned=owned,
        ownership_change_pct=_parse_pct(delta_own),
        value=value,
        source="openinsider",
    )


def _parse_row_any(cells: list[str]) -> InsiderTrade | None:
    """Parse a row without knowing the ticker — locates the date columns instead."""
    cells = [c.strip() for c in cells if c.strip()]
    if len(cells) < 10:
        return None

    # Find the trade-date column (plain YYYY-MM-DD, following the filing datetime)
    date_idx = None
    for i, c in enumerate(cells):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c) and i >= 1:
            date_idx = i
            break
    if date_idx is None:
        return None

    ticker_idx = date_idx + 1
    if ticker_idx >= len(cells):
        return None
    ticker = cells[ticker_idx]
    if not re.fullmatch(r"[A-Z.\-]{1,8}", ticker.upper()):
        return None

    return _parse_row(cells, ticker)


def _parse_money(text: str) -> float | None:
    text = text.replace("$", "").replace(",", "").replace("+", "").strip()
    if not text or text == "-":
        return None
    try:
        return abs(float(text))
    except ValueError:
        return None


def _parse_qty(text: str) -> int:
    text = text.replace(",", "").replace("+", "").strip()
    try:
        return abs(int(text))
    except ValueError:
        return 0


def _parse_pct(text: str) -> float | None:
    text = text.replace("%", "").strip()
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _summarize(symbol: str, trades: list[InsiderTrade], days: int) -> InsiderTradeSummary:
    purchases = [t for t in trades if t.is_purchase]
    sales = [t for t in trades if t.is_sale]
    buy_value = sum(t.value or 0 for t in purchases)
    sell_value = sum(t.value or 0 for t in sales)

    # Net sentiment: more insider buying = bullish signal
    if buy_value > sell_value * 1.5:
        sentiment = "bullish"
    elif sell_value > buy_value * 1.5:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    notable = sorted(trades, key=lambda t: t.value or 0, reverse=True)[:5]

    return InsiderTradeSummary(
        symbol=symbol,
        period_days=days,
        total_trades=len(trades),
        purchases=len(purchases),
        sales=len(sales),
        buy_value_usd=round(buy_value, 2),
        sell_value_usd=round(sell_value, 2),
        net_sentiment=sentiment,
        notable_trades=notable,
    )
