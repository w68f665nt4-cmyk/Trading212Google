"""
Trading212 Portfolio Monitor - Clean Foundation v1.7.2 (Remove Total P&L column)
Trading212 Portfolio Monitor - Clean Foundation v1.7.3 (Append vs Manual overwrite)
================================================================
A clean, production-ready implementation focused on reliability and maintainability.

Changelog v1.7.2:
- Removed 'Total P&L (HUF)' column from Google Sheets upload (RawData sheet).
- Updated header and row construction accordingly (Column C removed).
- Hourly (scheduled) runs: always append new rows; never delete existing.
- Manual runs: overwrite only previous MANUAL rows for the same day; if none yet today, append as new.
- Implements a hidden marker column 'Mode' with values 'auto' or 'manual' to distinguish sources.
"""

# ... keep existing imports ...
import os
import sys
import json
@@ -27,370 +26,39 @@
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# existing code omitted for brevity up to GoogleSheets class

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger("Trading212Monitor")
    logger.setLevel(getattr(logging, log_level))
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    if not logger.hasHandlers():
        logger.addHandler(console_handler)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
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
            logger.debug(f"Loaded environment from {env_file}")
        missing = [var for var in self.REQUIRED_VARS if not os.getenv(var)]
        if missing:
            logger.error(f"Missing required environment variables: {', '.join(missing)}")
            sys.exit(1)
        self.api_key = os.getenv("TRADING212_API_KEY")
        self.api_secret = os.getenv("TRADING212_API_SECRET")
        self.google_sheet_id = os.getenv("GOOGLE_SHEET_ID")
        self.google_creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.timezone_str = os.getenv("TIMEZONE", "Europe/Budapest")
        self.timezone = pytz.timezone(self.timezone_str)
        self.api_timeout = int(os.getenv("API_TIMEOUT", "15"))
        self.api_retries = int(os.getenv("API_RETRIES", "3"))
        self.data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "cache").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "logs").mkdir(parents=True, exist_ok=True)
        logger.info(f"Configuration loaded successfully (Timezone: {self.timezone})")


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
        d['total_value'] = self.total_value
        d['pnl_percent'] = self.pnl_percent
        return d

    @property
    def total_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def pnl_percent(self) -> float:
        invested = self.quantity * self.average_price
        if invested == 0:
            return 0.0
        return (self.pnl / invested) * 100


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

    def __str__(self) -> str:
        lines = [
            "=" * 70,
            f"PORTFOLIO SUMMARY - {self.timestamp}",
            "=" * 70,
        ]
        for pos in self.positions:
            lines.append(
                f"{pos.ticker:12} | Qty: {pos.quantity:8.2f} | "
                f"Avg: {pos.average_price:8.2f} {pos.currency} | "
                f"Current: {pos.current_price:8.2f} {pos.currency}"
            )
            lines.append(
                f"{'':12} | P&L: {pos.pnl:+8.2f} {pos.currency} | "
                f"Total Val: {pos.total_value_huf:,.2f} HUF"
            )
            lines.append("-" * 70)
        lines.append(f"TOTAL P&L: {self.total_pnl:+.2f} HUF")
        lines.append("=" * 70)
        return "\n".join(lines)


class Trading212API:
    def __init__(self, api_key: str, api_secret: str, timeout: int = 15, retries: int = 3):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://live.trading212.com/api/v0"
        self.timeout = timeout
        self.retries = retries
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        credentials = f"{self.api_key}:{self.api_secret}"
        encoded_creds = base64.b64encode(credentials.encode()).decode()
        session.headers.update({
            "Authorization": f"Basic {encoded_creds}",
            "Accept": "application/json"
        })
        return session

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.retries + 1):
            try:
                logger.debug(f"Request attempt {attempt}/{self.retries}: {method} {endpoint}")
                if method.upper() == "GET":
                    response = self.session.get(url, timeout=self.timeout, **kwargs)
                else:
                    response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                response.raise_for_status()
                return response.json()
            except Timeout:
                logger.warning(f"Timeout on attempt {attempt}/{self.retries}")
                if attempt == self.retries:
                    logger.error(f"Final timeout: {method} {endpoint}")
                    return None
            except RequestException as e:
                logger.error(f"Request error on attempt {attempt}/{self.retries}: {e}")
                if attempt == self.retries:
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                return None
            if attempt < self.retries:
                import time
                time.sleep(1)
        return None

    def get_portfolio(self) -> Optional[List[Dict]]:
        logger.info("Fetching portfolio from Trading212...")
        data = self._request("GET", "/equity/portfolio")
        if data:
            logger.info(f"Successfully fetched {len(data)} positions")
            return data
        else:
            logger.error("Failed to fetch portfolio")
            return None

    def get_instruments(self) -> Optional[Dict]:
        logger.info("Fetching instrument data...")
        data = self._request("GET", "/equity/metadata/instruments")
        if data:
            logger.info(f"Successfully fetched metadata for {len(data)} instruments")
            return {item['ticker']: item for item in data}
        else:
            logger.error("Failed to fetch instruments")
            return None


class FXRateAPI:
    def __init__(self, timeout: int = 10):
        self.base_url = "https://api.frankfurter.app"
        self.timeout = timeout
        self.cache: Dict[Tuple[str, str], float] = {}

    def get_rate(self, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return 1.0
        cache_key = (from_currency, to_currency)
        if cache_key in self.cache:
            logger.debug(f"Using cached rate: {from_currency}/{to_currency}")
            return self.cache[cache_key]
        logger.info(f"Fetching FX rate: {from_currency}/{to_currency}")
        try:
            response = requests.get(
                f"{self.base_url}/latest",
                params={"from": from_currency, "to": to_currency},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            if "rates" in data and to_currency in data["rates"]:
                rate = float(data["rates"][to_currency])
                self.cache[cache_key] = rate
                logger.debug(f"FX Rate: {from_currency}/{to_currency} = {rate:.4f}")
                return rate
            else:
                logger.error(f"FX API returned unexpected data: {data}")
                return 1.0
        except RequestException as e:
            logger.error(f"Failed to fetch FX rate: {e}")
            return 1.0
        except (ValueError, KeyError) as e:
            logger.error(f"Failed to parse FX rate response: {e}")
            return 1.0


class PortfolioProcessor:
    def __init__(self, timezone: pytz.timezone):
        self.timezone = timezone
        self.fx_api = FXRateAPI()

    def process(self, raw_positions: List[Dict], instrument_metadata: Optional[Dict] = None) -> Optional[Portfolio]:
        if not raw_positions:
            logger.warning("No positions to process")
            return None
        logger.info(f"Processing {len(raw_positions)} positions...")
        try:
            usd_huf = self.fx_api.get_rate("USD", "HUF")
            eur_huf = self.fx_api.get_rate("EUR", "HUF")
            positions: List[Position] = []
            total_pnl_huf = 0.0
            for raw_pos in raw_positions:
                try:
                    ticker = raw_pos.get("ticker", "UNKNOWN")
                    quantity = float(raw_pos.get("quantity", 0))
                    avg_price = float(raw_pos.get("averagePrice", 0))
                    current_price = float(raw_pos.get("currentPrice", 0))
                    pnl = float(raw_pos.get("ppl", 0))
                    if instrument_metadata and ticker in instrument_metadata:
                        currency = instrument_metadata[ticker].get("currencyCode", "EUR")
                        display_name = instrument_metadata[ticker].get("name", ticker)
                    else:
                        currency = "USD" if "_US_" in ticker else "EUR"
                        display_name = ticker
                    pos = Position(
                        ticker=ticker,
                        display_name=display_name,
                        quantity=quantity,
                        average_price=avg_price,
                        current_price=current_price,
                        pnl=pnl,
                        currency=currency,
                    )
                    fx_rate = 1.0
                    if currency == "USD":
                        fx_rate = usd_huf
                    elif currency == "EUR":
                        fx_rate = eur_huf
                    total_pnl_huf += pnl * fx_rate
                    pos.total_value_huf = pos.total_value * fx_rate
                    positions.append(pos)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping position {raw_pos.get('ticker', 'UNKNOWN')}: {e}")
                    continue
            if not positions:
                logger.error("No valid positions after processing")
                return None
            now = datetime.now(self.timezone)
            portfolio = Portfolio(
                positions=positions,
                timestamp=now.isoformat(),
                timezone=str(self.timezone),
                total_pnl=total_pnl_huf,
            )
            logger.info(f"Successfully processed {len(positions)} positions")
            return portfolio
        except Exception as e:
            logger.error(f"Error processing portfolio: {e}", exc_info=True)
            return None

# ===== Replace GoogleSheets.upsert_daily_data and Application.fetch_and_upload_to_gsheet =====

class GoogleSheets:
SCOPES = [
"https://www.googleapis.com/auth/spreadsheets",
"https://www.googleapis.com/auth/drive.file"
]

def __init__(self, sheet_id: str, creds_file: str):
self.sheet_id = sheet_id
self.creds_file = creds_file
self.client = self._authenticate()
self.sheet = self._open_sheet()
    # ... _authenticate, _open_sheet, _get_worksheet unchanged ...

    def _authenticate(self) -> Optional[gspread.Client]:
        try:
            if not Path(self.creds_file).exists():
                logger.error(f"Google credentials file not found: {self.creds_file}")
                return None
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.creds_file, self.SCOPES
            )
            client = gspread.authorize(creds)
            logger.info("Google Sheets authentication successful")
            return client
        except Exception as e:
            logger.error(f"Google Sheets authentication failed: {e}", exc_info=True)
            return None

    def _open_sheet(self) -> Optional[gspread.Spreadsheet]:
        if not self.client:
            return None
        try:
            sheet = self.client.open_by_key(self.sheet_id)
            logger.info(f"Successfully opened Google Sheet: {sheet.title}")
            return sheet
        except gspread.exceptions.APIError as e:
            logger.error(f"Failed to open Google Sheet (ID: {self.sheet_id}). Check ID and sharing permissions. Error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error opening Google Sheet: {e}", exc_info=True)
            return None

    def _get_worksheet(self, title: str) -> Optional[gspread.Worksheet]:
        if not self.sheet:
            return None
        try:
            return self.sheet.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Worksheet '{title}' not found, creating it...")
            return self.sheet.add_worksheet(title=title, rows=100, cols=20)
        except Exception as e:
            logger.error(f"Error accessing worksheet '{title}': {e}", exc_info=True)
            return None

    def upsert_daily_data(self, portfolio: Portfolio, sheet_name: str) -> bool:
    def upsert_daily_data(self, portfolio: 'Portfolio', sheet_name: str, mode: str) -> bool:
        """Append or upsert based on mode.
        mode: 'auto' for scheduled, 'manual' for workflow_dispatch/local.
        - auto: append rows only
        - manual: delete today's rows where Mode == 'manual', then append
        """
worksheet = self._get_worksheet(sheet_name)
if not worksheet:
logger.error(f"Could not get or create worksheet '{sheet_name}'")
return False
        logger.info(f"Upserting data to Google Sheet '{sheet_name}'...")
        logger.info(f"Upserting data to Google Sheet '{sheet_name}' (mode={mode})...")
try:
            # Header WITHOUT Total P&L column
header = [
"Date", "Timestamp", "Ticker",
"Quantity", "Avg Price", "Current Price", "P&L",
                "Currency", "Total value in foreign currency", "Total value in HUF"
                "Currency", "Total value in foreign currency", "Total value in HUF",
                "Mode"
]
try:
is_new_sheet = worksheet.acell('A1').value is None
@@ -400,19 +68,41 @@ def upsert_daily_data(self, portfolio: Portfolio, sheet_name: str) -> bool:
if is_new_sheet:
worksheet.append_row(header, value_input_option='USER_ENTERED')
logger.info(f"Worksheet '{sheet_name}' is new. Added header.")

current_date = portfolio.timestamp[:10]
            logger.info(f"Checking for existing data for date: {current_date}")
            cells_to_delete = []
            try:
                cells_to_delete = worksheet.findall(current_date, in_column=1)
            except gspread.exceptions.CellNotFound:
                logger.info("No existing data found for today.")
            if cells_to_delete:
                logger.info(f"Found {len(cells_to_delete)} existing rows for {current_date}. Deleting...")
                start_row = cells_to_delete[0].row
                end_row = cells_to_delete[-1].row
                worksheet.delete_rows(start_row, end_row)
                logger.info(f"Deleted rows {start_row} to {end_row}.")

            if mode == 'manual':
                # Find rows for today where Mode == 'manual' (column 11)
                try:
                    all_today = worksheet.findall(current_date, in_column=1)
                except gspread.exceptions.CellNotFound:
                    all_today = []
                if all_today:
                    # Filter rows where column 11 equals 'manual'
                    rows_to_delete = []
                    for cell in all_today:
                        try:
                            mode_value = worksheet.cell(cell.row, 11).value
                            if (mode_value or '').lower() == 'manual':
                                rows_to_delete.append(cell.row)
                        except Exception:
                            continue
                    if rows_to_delete:
                        # Delete contiguous blocks efficiently
                        rows_to_delete.sort()
                        start = rows_to_delete[0]
                        end = rows_to_delete[0]
                        for r in rows_to_delete[1:]:
                            if r == end + 1:
                                end = r
                            else:
                                worksheet.delete_rows(start, end)
                                start = r
                                end = r
                        worksheet.delete_rows(start, end)
                        logger.info(f"Deleted previous manual rows for {current_date}.")

            # Build rows
rows_to_append = []
timestamp_str = portfolio.timestamp
for pos in portfolio.positions:
@@ -426,11 +116,12 @@ def upsert_daily_data(self, portfolio: Portfolio, sheet_name: str) -> bool:
pos.pnl,
pos.currency,
pos.total_value,
                    pos.total_value_huf
                    pos.total_value_huf,
                    mode
])
logger.info(f"Appending {len(rows_to_append)} new rows...")
worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            logger.info(f"Successfully upserted data to '{sheet_name}'")
            logger.info(f"Successfully upserted data to '{sheet_name}' (mode={mode})")
return True
except gspread.exceptions.APIError as e:
logger.error(f"Google Sheets API error: {e}")
@@ -439,7 +130,6 @@ def upsert_daily_data(self, portfolio: Portfolio, sheet_name: str) -> bool:
logger.error(f"Failed to upsert to Google Sheet: {e}", exc_info=True)
return False


class Application:
def __init__(self):
self.config = Config()
@@ -456,7 +146,7 @@ def __init__(self):
self.config.google_creds_file
)

    def fetch(self) -> Optional[Portfolio]:
    def fetch(self) -> Optional['Portfolio']:
logger.info("Starting portfolio fetch...")
raw_positions = self.trading212.get_portfolio()
if not raw_positions:
@@ -466,130 +156,19 @@ def fetch(self) -> Optional[Portfolio]:
portfolio = self.processor.process(raw_positions, instrument_metadata)
return portfolio

    def fetch_and_display(self) -> bool:
        portfolio = self.fetch()
        if portfolio:
            print("\n" + str(portfolio))
            return True
        else:
            logger.error("Could not fetch portfolio")
            return False

    def fetch_and_save(self) -> bool:
        portfolio = self.fetch()
        if portfolio:
            return self.store.save_portfolio(portfolio)
        else:
            logger.error("Could not fetch portfolio")
            return False

    def show_latest(self) -> bool:
        data = self.store.load_latest_portfolio()
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        else:
            logger.warning("No saved portfolio available")
            return False

def fetch_and_upload_to_gsheet(self) -> bool:
sheet_name = "RawData"
logger.info(f"Target worksheet name set to: {sheet_name}")
portfolio = self.fetch()
        if portfolio:
            if not self.google_sheet.client or not self.google_sheet.sheet:
                logger.error("Google Sheets client not initialized. Cannot upload.")
                return False
            return self.google_sheet.upsert_daily_data(portfolio, sheet_name)
        else:
        if not portfolio:
logger.error("Could not fetch portfolio, skipping GSheet upload")
return False


class DataStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.portfolio_dir = data_dir / "portfolios"
        self.portfolio_dir.mkdir(parents=True, exist_ok=True)

    def save_portfolio(self, portfolio: Portfolio) -> bool:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.portfolio_dir / f"portfolio_{timestamp}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(portfolio.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Portfolio saved to {filename}")
            return True
        except IOError as e:
            logger.error(f"Failed to save portfolio: {e}")
        if not self.google_sheet.client or not self.google_sheet.sheet:
            logger.error("Google Sheets client not initialized. Cannot upload.")
return False
        # Determine mode from GitHub Actions; default to 'manual' when run locally
        gh_event = os.getenv('GITHUB_EVENT_NAME', '')
        mode = 'auto' if gh_event == 'schedule' else 'manual'
        return self.google_sheet.upsert_daily_data(portfolio, sheet_name, mode)

    def load_latest_portfolio(self) -> Optional[Portfolio]:
        try:
            files = sorted(self.portfolio_dir.glob("portfolio_*.json"), reverse=True)
            if not files:
                logger.warning("No saved portfolios found")
                return None
            latest_file = files[0]
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"Loaded portfolio from {latest_file}")
            return data
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load portfolio: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(
        description="Trading212 Portfolio Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trading212_clean.py fetch        Fetch and display portfolio
  python trading212_clean.py save         Fetch and save to JSON
  python trading212_clean.py gsheet       Fetch and upload to Google Sheets
  python trading212_clean.py latest       Show latest saved portfolio
  python trading212_clean.py --verbose    Increase logging verbosity
        """
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="fetch",
        choices=["fetch", "save", "latest", "gsheet"],
        help="Command to execute (default: fetch)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(logging.DEBUG)
    logger.info(f"Trading212 Portfolio Monitor v1.7.2 - Command: {args.command}")
    try:
        app = Application()
        if args.command == "fetch":
            success = app.fetch_and_display()
        elif args.command == "save":
            success = app.fetch_and_save()
        elif args.command == "latest":
            success = app.show_latest()
        elif args.command == "gsheet":
            success = app.fetch_and_upload_to_gsheet()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
# keep the rest of the file content (DataStore, CLI) unchanged
