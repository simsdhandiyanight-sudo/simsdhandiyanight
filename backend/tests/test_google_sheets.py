from unittest.mock import patch

from django.test import SimpleTestCase

from apps.payments.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsDataMigrationError,
)
from apps.payments.sheets import SHEET_HEADERS


class GoogleSheetsClientTests(SimpleTestCase):
    def setUp(self):
        self.client = GoogleSheetsClient(object(), spreadsheet_id="spreadsheet-test")

    def test_empty_worksheet_gets_the_required_headers(self):
        with (
            patch.object(self.client, "_ensure_worksheet", return_value={}),
            patch.object(self.client, "_get_values", return_value=[]),
            patch.object(
                self.client,
                "_sheet_properties",
                return_value={"Online_Tickets": 1},
            ),
            patch.object(self.client, "_write_values") as write_values,
        ):
            headers = self.client._ensure_headers("Online_Tickets")

        self.assertEqual(headers, [list(SHEET_HEADERS)])
        write_values.assert_called_once_with(
            "Online_Tickets",
            "A1",
            [list(SHEET_HEADERS)],
        )

    def test_existing_ticket_row_is_updated_not_appended(self):
        row = {header: "" for header in SHEET_HEADERS}
        row.update(ticket_id="stable-ticket-id", ticket_number="SIMS-DN-20260001")
        existing = [row[header] for header in SHEET_HEADERS]
        with (
            patch.object(
                self.client,
                "_ensure_headers",
                return_value=[list(SHEET_HEADERS), existing],
            ),
            patch.object(self.client, "_write_values") as write_values,
            patch.object(self.client, "_append_values") as append_values,
        ):
            result = self.client.upsert_ticket_row("Online_Tickets", row)

        self.assertEqual(result, "UPDATED")
        write_values.assert_called_once_with(
            "Online_Tickets",
            "A2:X2",
            [[row[header] for header in SHEET_HEADERS]],
        )
        append_values.assert_not_called()

    def test_existing_legacy_records_are_archived_and_mapped_before_migration(self):
        old_rows = [
            [
                "registration_id",
                "ticket_id",
                "ticket_number",
                "email",
                "verification_status",
                "email_status",
                "created_at",
            ],
            [
                "registration-1",
                "stable-ticket-id",
                "SIMS-DN-20260001",
                "person@example.test",
                "VERIFIED",
                "SENT",
                "2026-10-12T10:00:00+00:00",
            ],
        ]
        with (
            patch.object(self.client, "_ensure_worksheet", return_value={}),
            patch.object(self.client, "_get_values", side_effect=[old_rows, []]),
            patch.object(self.client, "_write_values") as write_values,
            patch.object(self.client, "_clear_values") as clear_values,
        ):
            migrated = self.client._ensure_headers("Online_Tickets")

        self.assertEqual(migrated[0], list(SHEET_HEADERS))
        self.assertEqual(migrated[1][SHEET_HEADERS.index("ticket_id")], "stable-ticket-id")
        self.assertEqual(migrated[1][SHEET_HEADERS.index("payment_status")], "VERIFIED")
        self.assertEqual(migrated[1][SHEET_HEADERS.index("email_status")], "SENT")
        self.assertEqual(migrated[1][SHEET_HEADERS.index("name")], "")
        clear_values.assert_called_once_with("Online_Tickets")
        self.assertEqual(write_values.call_count, 2)
        self.assertEqual(write_values.call_args_list[0].args[2], old_rows)
        self.assertEqual(write_values.call_args_list[1].args[2][0], list(SHEET_HEADERS))

    def test_archive_collision_with_different_data_stops_migration(self):
        rows = [["ticket_id"], ["ticket-1"]]
        with (
            patch.object(self.client, "_ensure_worksheet"),
            patch.object(self.client, "_get_values", return_value=[["different-data"]]),
        ):
            with self.assertRaisesRegex(
                GoogleSheetsDataMigrationError,
                "contains different data",
            ):
                self.client._archive_legacy_rows("Online_Tickets", rows)

    def test_legacy_duplicate_ticket_ids_are_not_silently_dropped(self):
        rows = [
            ["ticket_id", "ticket_number"],
            ["ticket-1", "SIMS-DN-20260001"],
            ["ticket-1", "SIMS-DN-20260002"],
        ]
        with self.assertRaisesRegex(
            GoogleSheetsDataMigrationError,
            "duplicate ticket_id",
        ):
            self.client._legacy_values("Online_Tickets", rows)
