import hashlib
import json
import logging
from urllib.parse import quote

import google.auth.exceptions
import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

from django.conf import settings

from .sheets import SHEET_HEADERS

logger = logging.getLogger(__name__)

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"


class GoogleSheetsError(RuntimeError):
    pass


class GoogleSheetsConfigurationError(GoogleSheetsError):
    pass


class GoogleSheetsDataMigrationError(GoogleSheetsError):
    pass


def create_google_sheets_client():
    raw_credentials = settings.GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON
    spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
    if not raw_credentials or not spreadsheet_id:
        raise GoogleSheetsConfigurationError(
            "Set GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON and "
            "GOOGLE_SHEETS_SPREADSHEET_ID to enable ticket synchronization."
        )
    try:
        service_account = json.loads(raw_credentials)
        credentials = Credentials.from_service_account_info(
            service_account,
            scopes=(SHEETS_SCOPE,),
        )
    except (json.JSONDecodeError, TypeError, ValueError, google.auth.exceptions.GoogleAuthError) as error:
        raise GoogleSheetsConfigurationError(
            "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON is not a valid service-account credential."
        ) from error
    return GoogleSheetsClient(
        AuthorizedSession(credentials),
        spreadsheet_id=spreadsheet_id,
    )


class GoogleSheetsClient:
    def __init__(self, session, *, spreadsheet_id):
        self.session = session
        self.spreadsheet_id = spreadsheet_id

    def _request(self, method, path, **kwargs):
        path_separator = "" if path.startswith(":") else "/"
        response = self.session.request(
            method,
            f"{SHEETS_API}/{quote(self.spreadsheet_id, safe='')}"
            f"{path_separator}{path.lstrip('/')}",
            timeout=20,
            **kwargs,
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    @staticmethod
    def _quoted_range(sheet_name, cell_range):
        return quote(f"'{sheet_name}'!{cell_range}", safe="'!:$")

    def _sheet_properties(self):
        spreadsheet = self._request(
            "GET",
            "",
            params={"fields": "sheets.properties(sheetId,title)"},
        )
        return {
            sheet["properties"]["title"]: sheet["properties"]["sheetId"]
            for sheet in spreadsheet.get("sheets", [])
        }

    def _add_worksheet(self, title):
        self._request(
            "POST",
            ":batchUpdate",
            json={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        )

    def _ensure_worksheet(self, title):
        sheets = self._sheet_properties()
        if title in sheets:
            return sheets
        try:
            self._add_worksheet(title)
        except requests.HTTPError:
            # Another worker may have created the same tab between the read and write.
            sheets = self._sheet_properties()
            if title not in sheets:
                raise
        return self._sheet_properties()

    def _get_values(self, title, cell_range="A:ZZ"):
        result = self._request(
            "GET",
            f"/values/{self._quoted_range(title, cell_range)}",
        )
        return result.get("values", [])

    def _write_values(self, title, cell_range, values):
        self._request(
            "PUT",
            f"/values/{self._quoted_range(title, cell_range)}",
            params={"valueInputOption": "RAW"},
            json={"majorDimension": "ROWS", "values": values},
        )

    def _append_values(self, title, values):
        self._request(
            "POST",
            f"/values/{self._quoted_range(title, 'A:X')}:append",
            params={
                "valueInputOption": "RAW",
                "insertDataOption": "INSERT_ROWS",
            },
            json={"majorDimension": "ROWS", "values": [values]},
        )

    def _clear_values(self, title):
        self._request(
            "POST",
            f"/values/{self._quoted_range(title, 'A:ZZ')}:clear",
            json={},
        )

    def _legacy_sheet_title(self, title, rows):
        content_hash = hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:8]
        return f"Legacy_{title}_{content_hash}"[:100]

    def _archive_legacy_rows(self, title, rows):
        archive_title = self._legacy_sheet_title(title, rows)
        self._ensure_worksheet(archive_title)
        archived_rows = self._get_values(archive_title)
        if not archived_rows:
            self._write_values(archive_title, "A1", rows)
        elif archived_rows != rows:
            raise GoogleSheetsDataMigrationError(
                f"Archive worksheet {archive_title} contains different data; "
                "the source worksheet was not modified."
            )
        logger.warning(
            "Archived legacy Google Sheets rows from %s to %s before schema migration.",
            title,
            archive_title,
        )

    def _legacy_values(self, title, rows):
        headers = [str(value) for value in rows[0]]
        if len(headers) != len(set(headers)):
            raise GoogleSheetsDataMigrationError(
                f"{title} contains duplicate column headers. "
                "The original data has been archived; reconcile the schema before syncing."
            )
        legacy_rows = rows[1:]
        normalized_rows = []
        ticket_ids = set()
        source_indexes = {header: index for index, header in enumerate(headers)}
        for old_row in legacy_rows:
            old_values = {
                header: old_row[index] if index < len(old_row) else ""
                for header, index in source_indexes.items()
            }
            if not old_values.get("ticket_id"):
                raise GoogleSheetsDataMigrationError(
                    f"{title} contains a legacy row without ticket_id. "
                    "The original data has been archived; reconcile that row before syncing."
                )
            if old_values["ticket_id"] in ticket_ids:
                raise GoogleSheetsDataMigrationError(
                    f"{title} contains duplicate ticket_id values. "
                    "The original data has been archived; reconcile those rows before syncing."
                )
            ticket_ids.add(old_values["ticket_id"])
            migrated = {
                header: old_values.get(header, "")
                for header in SHEET_HEADERS
            }
            if not migrated["payment_status"]:
                migrated["payment_status"] = old_values.get("verification_status", "")
            migrated["last_synced_at"] = ""
            normalized_rows.append(migrated)

        return [
            [row[header] for header in SHEET_HEADERS]
            for row in normalized_rows
        ]

    def _ensure_headers(self, title):
        self._ensure_worksheet(title)
        rows = self._get_values(title)
        if rows and rows[0] == list(SHEET_HEADERS):
            return rows

        if not rows:
            # Recover an interrupted migration from its archived source before treating this as new.
            archive_prefix = f"Legacy_{title}_"
            archive_titles = [
                name
                for name in self._sheet_properties()
                if name.startswith(archive_prefix)
            ]
            if archive_titles:
                rows = self._get_values(sorted(archive_titles)[-1])
            else:
                self._write_values(title, "A1", [list(SHEET_HEADERS)])
                return [list(SHEET_HEADERS)]

        if rows:
            headers = [str(value) for value in rows[0]]
            self._archive_legacy_rows(title, rows)
            migrated_rows = self._legacy_values(title, rows)
            self._clear_values(title)
            self._write_values(
                title,
                "A1",
                [list(SHEET_HEADERS), *migrated_rows],
            )
            return [list(SHEET_HEADERS), *migrated_rows]

        self._write_values(title, "A1", [list(SHEET_HEADERS)])
        return [list(SHEET_HEADERS)]

    def upsert_ticket_row(self, title, row):
        rows = self._ensure_headers(title)
        row_values = [row[header] for header in SHEET_HEADERS]
        ticket_column = SHEET_HEADERS.index("ticket_id")
        matches = [
            index
            for index, existing in enumerate(rows[1:], start=2)
            if len(existing) > ticket_column
            and existing[ticket_column] == row["ticket_id"]
        ]
        if len(matches) > 1:
            raise GoogleSheetsDataMigrationError(
                f"{title} contains duplicate rows for ticket_id {row['ticket_id']}; "
                "no new row was written."
            )
        if matches:
            target_row = matches[0]
            self._write_values(
                title,
                f"A{target_row}:X{target_row}",
                [row_values],
            )
            return "UPDATED"
        self._append_values(title, row_values)
        return "INSERTED"
