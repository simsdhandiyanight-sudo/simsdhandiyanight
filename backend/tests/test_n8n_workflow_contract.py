import json
from pathlib import Path

from django.test import SimpleTestCase

from apps.payments.sheets import SHEET_HEADERS


WORKFLOW_DIR = (
    Path(__file__).resolve().parents[2]
    / "mail delivery dhandiya night sims"
)
SHEET_SYNC_WORKFLOW = WORKFLOW_DIR / "n8n" / "workflows" / "ticket-google-sheets-sync.json"
SHEET_EMAIL_WORKFLOW = (
    WORKFLOW_DIR
    / "n8n"
    / "workflows"
    / "ticket-email-delivery-from-google-sheets.json"
)


class N8nWorkflowContractTests(SimpleTestCase):
    def load_workflow(self, path):
        with path.open(encoding="utf-8") as workflow_file:
            return json.load(workflow_file)

    def test_legacy_email_workflow_export_is_inactive(self):
        workflow = self.load_workflow(SHEET_EMAIL_WORKFLOW)
        self.assertFalse(workflow["active"])

    def test_sheets_workflow_uses_django_jobs_and_ticket_id_upserts(self):
        workflow = self.load_workflow(SHEET_SYNC_WORKFLOW)
        nodes = {node["name"]: node for node in workflow["nodes"]}
        self.assertIn("Fetch Pending Sheet Jobs", nodes)
        self.assertIn("Fetch Ticket Sheet Data", nodes)
        self.assertIn("Mark Sheet Job Synced", nodes)
        self.assertIn("Report Sheet Upsert Failure", nodes)

        pending_url = nodes["Fetch Pending Sheet Jobs"]["parameters"]["url"]
        self.assertIn("/api/internal/sheet-jobs/pending", pending_url)
        data_url = nodes["Fetch Ticket Sheet Data"]["parameters"]["url"]
        self.assertIn("/api/internal/sheet-jobs/", data_url)
        self.assertIn("/data?attempt=", data_url)

        upsert = nodes["Upsert Ticket Row"]["parameters"]
        self.assertEqual(upsert["operation"], "appendOrUpdate")
        self.assertEqual(upsert["columns"]["matchingColumns"], ["ticket_id"])
        self.assertIn("$json.sheet_name", upsert["sheetName"]["value"])
        self.assertEqual(
            upsert["documentId"]["value"],
            "={{$env.GOOGLE_SHEETS_SPREADSHEET_ID}}",
        )
        self.assertEqual(
            set(upsert["columns"]["value"]),
            set(SHEET_HEADERS),
        )
        self.assertEqual(upsert["columns"]["value"], list(SHEET_HEADERS))
        self.assertEqual(
            nodes["Ensure Sheet Headers"]["parameters"]["headers"],
            list(SHEET_HEADERS),
        )
        serialized = json.dumps(workflow).lower()
        self.assertNotIn("qr_token", serialized)
        self.assertNotIn("django_internal_api_key", serialized)
