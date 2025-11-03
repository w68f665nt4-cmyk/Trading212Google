"""
Trading212 Portfolio Monitor - Clean Foundation v1.7.2 (Reverted)
================================================================
- Removed 'Total P&L (HUF)' column from Google Sheets upload (RawData, keeps previous working behavior)
"""

# Original, working implementation restored with minor cleanup

import os
import sys
import json
import logging
import argparse
import base64
import pytz
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

import requests
from requests.exceptions import RequestException, Timeout
from dotenv import load_dotenv

import gspread
from oauth2client.service_account import ServiceAccountCredentials


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("Trading212Monitor")
    logger.setLevel(getattr(logging, log_level))
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(getattr(logging, log_level))
        ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(ch)
    return logger


logger = setup_logging()


class Config:
    REQUIRED_VARS = [
        "TRADING212_API_KEY",
        "TRADING212_API_SECRET",
        "GOOGLE_SHEET_ID",
        "GOOGLE_CREDENTIALS_FILE",
    ]
    def __init__(self, env_file: str = ".env"):
        if Path(env_file).exists():
            load_dotenv(env_file)
        missing = [v for v in self.REQUIRED_VARS if not os.getenv(v)]
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            sys.exit(1)
        self.api_key = os.getenv("TRADING212_API_KEY")
        self.api_secret = os.getenv("TRADING212_API_SECRET")
        self.google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.google_creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.timezone = pytz.timezone(os.getenv("TIMEZONE", "Europe/Budapest"))
        self.api_timeout = int(os.getenv("API_TIMEOUT", "15"))
        self.api_retries = int(os.getenv("API_RETRIES", "3"))


@dataclass
class Position:
    ticker: str
    display_name: str
    quantity: float
    average_price: float
    current_price: float
    pnl: float
    currency: str
    total_value_huf: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['total_value'] = self.quantity * self.current_price
        inv = self.quantity * self.average_price
        d['pnl_percent'] = 0.0 if inv == 0 else (self.pnl / inv) * 100
        return d


@dataclass
class Portfolio:
    positions: List[Position]
    timestamp: str
    timezone: str
    total_pnl: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "timezone": self.timezone,
            "total_pnl": self.total_pnl,
            "positions": [p.to_dict() for p in self.positions],
            "position_count": len(self.positions),
        }


class Trading212API:
    def __init__(self, api_key: str, api_secret: str, timeout: int = 15, retries: int = 3):
        self.base_url = "https://live.trading212.com/api/v0"
        self.timeout = timeout
        self.retries = retries
        cred = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Basic {cred}", "Accept": "application/json"})
    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.retries + 1):
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kwargs)
                r.raise_for_status()
                return r.json()
            except (Timeout, RequestException) as e:
                if attempt == self.retries:
                    logger.error(f"API error {method} {endpoint}: {e}")
                    return None
    def get_portfolio(self) -> Optional[List[Dict]]:
        return self._request("GET", "/equity/portfolio")
    def get_instruments(self) -> Optional[Dict]:
        data = self._request("GET", "/equity/metadata/instruments")
        return {i['ticker']: i for i in data} if data else None


class FXRateAPI:
    def __init__(self):
        self.base_url = "https://api.frankfurter.app"
        self.cache: Dict[str, float] = {}
    def get_rate(self, from_ccy: str, to_ccy: str) -> float:
        if from_ccy == to_ccy:
            return 1.0
        key = f"{from_ccy}/{to_ccy}"
        if key in self.cache:
            return self.cache[key]
        try:
            r = requests.get(f"{self.base_url}/latest", params={"from": from_ccy, "to": to_ccy}, timeout=10)
            r.raise_for_status()
            rate = float(r.json()["rates"][to_ccy])
            self.cache[key] = rate
            return rate
        except Exception:
            return 1.0


class PortfolioProcessor:
    def __init__(self, timezone: pytz.timezone):
        self.tz = timezone
        self.fx = FXRateAPI()
    def process(self, raw: List[Dict], meta: Optional[Dict]) -> Optional[Portfolio]:
        if not raw:
            return None
        usd_huf = self.fx.get_rate("USD", "HUF")
        eur_huf = self.fx.get_rate("EUR", "HUF")
        positions: List[Position] = []
        total_pnl_huf = 0.0
        for r in raw:
            try:
                t = r.get("ticker", "UNKNOWN")
                qty = float(r.get("quantity", 0))
                avg = float(r.get("averagePrice", 0))
                cur = float(r.get("currentPrice", 0))
                ppl = float(r.get("ppl", 0))
                if meta and t in meta:
                    ccy = meta[t].get("currencyCode", "EUR")
                    name = meta[t].get("name", t)
                else:
                    ccy = "USD" if "_US_" in t else "EUR"
                    name = t
                pos = Position(ticker=t, display_name=name, quantity=qty, average_price=avg, current_price=cur, pnl=ppl, currency=ccy)
                rate = usd_huf if ccy == "USD" else eur_huf if ccy == "EUR" else 1.0
                total_pnl_huf += ppl * rate
                pos.total_value_huf = pos.quantity * pos.current_price * rate
                positions.append(pos)
            except Exception:
                continue
        if not positions:
            return None
        now = datetime.now(self.tz)
        return Portfolio(positions=positions, timestamp=now.isoformat(), timezone=str(self.tz), total_pnl=total_pnl_huf)


class GoogleSheets:
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"]
    def __init__(self, sheet_id: str, creds_file: str):
        self.sheet_id = sheet_id
        self.creds_file = creds_file
        self.client = self._auth()
        self.sheet = self._open()
    def _auth(self) -> Optional[gspread.Client]:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_file, self.SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"GSheet auth failed: {e}")
            return None
    def _open(self) -> Optional[gspread.Spreadsheet]:
        if not self.client:
            return None
        try:
            return self.client.open_by_key(self.sheet_id)
        except Exception as e:
            logger.error(f"Open sheet failed: {e}")
            return None
    def _ws(self, title: str) -> Optional[gspread.Worksheet]:
        if not self.sheet:
            return None
        try:
            return self.sheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            return self.sheet.add_worksheet(title=title, rows=100, cols=20)
        except Exception as e:
            logger.error(f"Worksheet access failed: {e}")
            return None
    def upsert_daily(self, portfolio: Portfolio, title: str) -> bool:
        ws = self._ws(title)
        if not ws:
            return False
        header = [
            "Date", "Timestamp", "Ticker",
            "Quantity", "Avg Price", "Current Price", "P&L",
            "Currency", "Total value in foreign currency", "Total value in HUF"
        ]
        try:
            if ws.acell('A1').value is None:
                ws.append_row(header, value_input_option='USER_ENTERED')
        except Exception:
            ws.append_row(header, value_input_option='USER_ENTERED')
        # Previous working behavior: delete today's block then append fresh snapshot
        today = portfolio.timestamp[:10]
        try:
            cells = ws.findall(today, in_column=1)
        except gspread.exceptions.CellNotFound:
            cells = []
        if cells:
            start = cells[0].row
            end = cells[-1].row
            ws.delete_rows(start, end)
        rows = []
        ts = portfolio.timestamp
        for p in portfolio.positions:
            rows.append([
                today, ts, p.ticker,
                p.quantity, p.average_price, p.current_price, p.pnl,
                p.currency, p.quantity * p.current_price, p.total_value_huf
            ])
        ws.append_rows(rows, value_input_option='USER_ENTERED')
        return True


class Application:
    def __init__(self):
        self.cfg = Config()
        self.t212 = Trading212API(self.cfg.api_key, self.cfg.api_secret, timeout=self.cfg.api_timeout, retries=self.cfg.api_retries)
        self.proc = PortfolioProcessor(self.cfg.timezone)
        self.gs = GoogleSheets(self.cfg.google_sheet_id, self.cfg.google_creds_file)
    def fetch(self) -> Optional[Portfolio]:
        raw = self.t212.get_portfolio()
        if not raw:
            return None
        meta = self.t212.get_instruments()
        return self.proc.process(raw, meta)
    def fetch_and_upload_to_gsheet(self) -> bool:
        pf = self.fetch()
        if not pf:
            return False
        return self.gs.upsert_daily(pf, "RawData")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="fetch", choices=["fetch", "save", "latest", "gsheet"])  
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        setup_logging("DEBUG")
    app = Application()
    if args.command == "gsheet":
        ok = app.fetch_and_upload_to_gsheet()
        sys.exit(0 if ok else 1)
    elif args.command == "fetch":
        pf = app.fetch()
        if pf:
            print(str(pf))
            sys.exit(0)
        sys.exit(1)
    elif args.command == "save":
        pf = app.fetch()
        if pf:
            Path("data").mkdir(exist_ok=True)
            with open("data/portfolio.json", "w", encoding="utf-8") as f:
                json.dump(pf.to_dict(), f, indent=2, ensure_ascii=False)
            sys.exit(0)
        sys.exit(1)
    elif args.command == "latest":
        if Path("data/portfolio.json").exists():
            print(Path("data/portfolio.json").read_text())
            sys.exit(0)
        sys.exit(1)


if __name__ == "__main__":
    main()
