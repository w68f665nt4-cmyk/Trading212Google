"""
Trading212 Portfolio Monitor - Clean Foundation v1.7.3 (Append vs Manual overwrite)
================================================================
- Hourly (scheduled) runs: always append new rows; never delete existing.
- Manual runs: overwrite only previous MANUAL rows for the same day; if none yet today, append as new.
- Implements a hidden marker column 'Mode' with values 'auto' or 'manual' to distinguish sources.
"""

# ... keep existing imports ...
import os
import sys
import json
import logging
import argparse
import base64
import pytz
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

import requests
from requests.exceptions import RequestException, Timeout
from dotenv import load_dotenv

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# existing code omitted for brevity up to GoogleSheets class

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
        logger.info(f"Upserting data to Google Sheet '{sheet_name}' (mode={mode})...")
        try:
            header = [
                "Date", "Timestamp", "Ticker",
                "Quantity", "Avg Price", "Current Price", "P&L",
                "Currency", "Total value in foreign currency", "Total value in HUF",
                "Mode"
            ]
            try:
                is_new_sheet = worksheet.acell('A1').value is None
            except gspread.exceptions.APIError as e:
                logger.warning(f"Could not read A1 (likely new sheet): {e}")
                is_new_sheet = True
            if is_new_sheet:
                worksheet.append_row(header, value_input_option='USER_ENTERED')
                logger.info(f"Worksheet '{sheet_name}' is new. Added header.")

            current_date = portfolio.timestamp[:10]

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
                rows_to_append.append([
                    current_date,
                    timestamp_str,
                    pos.ticker,
                    pos.quantity,
                    pos.average_price,
                    pos.current_price,
                    pos.pnl,
                    pos.currency,
                    pos.total_value,
                    pos.total_value_huf,
                    mode
                ])
            logger.info(f"Appending {len(rows_to_append)} new rows...")
            worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            logger.info(f"Successfully upserted data to '{sheet_name}' (mode={mode})")
            return True
        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to upsert to Google Sheet: {e}", exc_info=True)
            return False

class Application:
    def __init__(self):
        self.config = Config()
        self.trading212 = Trading212API(
            self.config.api_key,
            self.config.api_secret,
            timeout=self.config.api_timeout,
            retries=self.config.api_retries,
        )
        self.processor = PortfolioProcessor(self.config.timezone)
        self.store = DataStore(self.config.data_dir)
        self.google_sheet = GoogleSheets(
            self.config.google_sheet_id,
            self.config.google_creds_file
        )

    def fetch(self) -> Optional['Portfolio']:
        logger.info("Starting portfolio fetch...")
        raw_positions = self.trading212.get_portfolio()
        if not raw_positions:
            logger.error("Failed to fetch positions")
            return None
        instrument_metadata = self.trading212.get_instruments()
        portfolio = self.processor.process(raw_positions, instrument_metadata)
        return portfolio

    def fetch_and_upload_to_gsheet(self) -> bool:
        sheet_name = "RawData"
        logger.info(f"Target worksheet name set to: {sheet_name}")
        portfolio = self.fetch()
        if not portfolio:
            logger.error("Could not fetch portfolio, skipping GSheet upload")
            return False
        if not self.google_sheet.client or not self.google_sheet.sheet:
            logger.error("Google Sheets client not initialized. Cannot upload.")
            return False
        # Determine mode from GitHub Actions; default to 'manual' when run locally
        gh_event = os.getenv('GITHUB_EVENT_NAME', '')
        mode = 'auto' if gh_event == 'schedule' else 'manual'
        return self.google_sheet.upsert_daily_data(portfolio, sheet_name, mode)

# keep the rest of the file content (DataStore, CLI) unchanged
