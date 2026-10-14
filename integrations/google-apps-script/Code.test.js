const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const headers = [
  "ticket_id", "ticket_number", "registration_id", "ticket_type",
  "booking_quantity", "ticket_quantity", "unit_price", "name", "email",
  "phone", "amount_due", "payment_method", "provider_order_id",
  "provider_payment_id", "upi_id", "transaction_id_utr", "payment_status",
  "verified_by", "verified_at", "ticket_status", "ticket_generated_at",
  "email_status", "email_sent_at", "scan_status", "checked_in_at",
  "checked_in_by", "created_at", "updated_at", "last_synced_at",
];
const legacyHeaders = [
  "ticket_id", "ticket_number", "registration_id", "ticket_type", "name",
  "email", "phone", "amount_due", "payment_method", "upi_id",
  "transaction_id_utr", "payment_status", "verified_by", "verified_at",
  "ticket_status", "ticket_generated_at", "email_status", "email_sent_at",
  "scan_status", "checked_in_at", "checked_in_by", "created_at",
  "updated_at", "last_synced_at",
];

function createHarness(initialSheetHeaders = {}) {
  const properties = {
    WEBHOOK_SECRET: "test-shared-secret",
    SPREADSHEET_ID: "test-spreadsheet-id",
  };
  const sheets = new Map();
  const lock = { attempts: 0, releases: 0, granted: true };

  class FakeRange {
    constructor(sheet, row, column, rowCount, columnCount) {
      Object.assign(this, { sheet, row, column, rowCount, columnCount });
    }

    getValues() {
      return Array.from({ length: this.rowCount }, (_, rowOffset) =>
        Array.from({ length: this.columnCount }, (_, columnOffset) =>
          this.sheet.values[this.row + rowOffset - 1]?.[this.column + columnOffset - 1] ?? ""
        )
      );
    }

    getDisplayValues() {
      return this.getValues().map((row) => row.map(String));
    }

    setValues(values) {
      values.forEach((row, rowOffset) => {
        const targetIndex = this.row + rowOffset - 1;
        this.sheet.values[targetIndex] ??= [];
        row.forEach((value, columnOffset) => {
          this.sheet.values[targetIndex][this.column + columnOffset - 1] = value;
        });
      });
      return this;
    }
  }

  class FakeSheet {
    constructor(name) {
      this.name = name;
      this.values = [];
    }

    getLastRow() {
      return this.values.reduce(
        (last, row, index) => row.some((value) => value !== "")
          ? index + 1
          : last,
        0
      );
    }

    getLastColumn() {
      return Math.max(0, ...this.values.map((row) => row.length));
    }

    getRange(row, column, rowCount, columnCount) {
      return new FakeRange(this, row, column, rowCount, columnCount);
    }
  }

  for (const [name, initialHeaders] of Object.entries(initialSheetHeaders)) {
    const sheet = new FakeSheet(name);
    sheet.values.push(initialHeaders.slice());
    sheets.set(name, sheet);
  }

  const context = {
    ContentService: {
      MimeType: { JSON: "application/json" },
      createTextOutput(text) {
        return {
          text,
          setMimeType() { return this; },
        };
      },
    },
    LockService: {
      getScriptLock() {
        return {
          tryLock() { lock.attempts += 1; return lock.granted; },
          releaseLock() { lock.releases += 1; },
        };
      },
    },
    PropertiesService: {
      getScriptProperties() {
        return { getProperty: (name) => properties[name] || null };
      },
    },
    SpreadsheetApp: {
      openById(id) {
        assert.equal(id, properties.SPREADSHEET_ID);
        return {
          getSheetByName(name) { return sheets.get(name) || null; },
          insertSheet(name) {
            const sheet = new FakeSheet(name);
            sheets.set(name, sheet);
            return sheet;
          },
        };
      },
    },
    Utilities: {
      DigestAlgorithm: { SHA_256: "sha256" },
      Charset: { UTF_8: "utf8" },
      computeDigest(_algorithm, value) {
        return [...crypto.createHash("sha256").update(value, "utf8").digest()]
          .map((byte) => byte > 127 ? byte - 256 : byte);
      },
    },
  };
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, "Code.gs"), "utf8");
  vm.runInContext(source, context);
  return { context, sheets, lock, properties };
}

function ticket(ticketId, registrationId, status = "VERIFIED") {
  const row = Object.fromEntries(headers.map((key) => [key, ""]));
  Object.assign(row, {
    ticket_id: ticketId,
    ticket_number: `SIMS-DN-${ticketId.slice(0, 8)}`,
    registration_id: registrationId,
    booking_quantity: 1,
    ticket_quantity: 1,
    amount_due: "149.00",
    payment_status: status,
    ticket_status: "ISSUED",
    name: "=HYPERLINK(\"https://bad.example\",\"click\")",
  });
  return { sheet_name: "Online_Tickets", row };
}

function post(context, payload) {
  const result = context.doPost({
    postData: { contents: JSON.stringify(payload) },
  });
  return JSON.parse(result.text);
}

test("rejects missing or invalid shared secret and malformed JSON", () => {
  const { context } = createHarness();
  const validTicket = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  assert.equal(
    post(context, { secret: "wrong", tickets: [validTicket] }).error_code,
    "AUTH_FAILED"
  );
  assert.equal(
    post(context, { tickets: [validTicket] }).error_code,
    "AUTH_FAILED"
  );
  assert.equal(
    JSON.parse(context.doPost({ postData: { contents: "{" } }).text).error_code,
    "INVALID_JSON"
  );
});

test("rejects malformed, unverified, and invalid UUID ticket payloads", () => {
  const { context } = createHarness();
  const validTicket = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  for (const invalid of [
    { ...validTicket, row: { ...validTicket.row, ticket_id: "not-a-uuid" } },
    { ...validTicket, row: { ...validTicket.row, payment_status: "PENDING" } },
    { ...validTicket, row: { ...validTicket.row, ticket_quantity: "1" } },
    { ...validTicket, row: Object.fromEntries(Object.entries(validTicket.row).filter(([key]) => key !== "phone")) },
  ]) {
    assert.equal(
      post(context, { secret: "test-shared-secret", tickets: [invalid] }).error_code,
      "INVALID_REQUEST"
    );
  }
});

test("inserts then updates an existing ticket row without duplication", () => {
  const { context, sheets, lock } = createHarness();
  const record = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  const payload = { secret: "test-shared-secret", tickets: [record] };
  assert.equal(post(context, payload).success, true);
  record.row.name = "Updated attendee";
  assert.equal(post(context, payload).success, true);

  const sheet = sheets.get("Online_Tickets");
  assert.equal(sheet.getLastRow(), 2);
  assert.equal(sheet.values[1][0], record.row.ticket_id);
  assert.equal(sheet.values[1][headers.indexOf("name")], "Updated attendee");
  assert.equal(lock.attempts, 2);
  assert.equal(lock.releases, 2);
});

test("keeps separate UUID rows for multiple tickets in one booking", () => {
  const { context, sheets } = createHarness();
  const registrationId = "00000000-0000-4000-8000-000000000003";
  const records = [
    ticket("00000000-0000-4000-8000-000000000001", registrationId),
    ticket("00000000-0000-4000-8000-000000000002", registrationId),
  ];
  const result = post(context, {
    secret: "test-shared-secret",
    tickets: records,
  });

  assert.equal(result.success, true);
  assert.deepEqual(result.processed_ticket_ids, records.map(({ row }) => row.ticket_id));
  assert.equal(sheets.get("Online_Tickets").getLastRow(), 3);
});

test("escapes formula-leading customer values before writing", () => {
  const { context, sheets } = createHarness();
  const record = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  post(context, { secret: "test-shared-secret", tickets: [record] });
  assert.equal(
    sheets.get("Online_Tickets").values[1][headers.indexOf("name")],
    "'" + record.row.name
  );
});

test("reports a busy script lock as a retryable error", () => {
  const { context, lock } = createHarness();
  lock.granted = false;
  const record = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  const result = post(context, {
    secret: "test-shared-secret",
    tickets: [record],
  });
  assert.equal(result.success, false);
  assert.equal(result.error_code, "LOCK_TIMEOUT");
  assert.equal(result.retryable, true);
  assert.equal(lock.releases, 0);
});

test("refuses to modify an existing worksheet with different headers", () => {
  const { context, sheets } = createHarness();
  const record = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  post(context, { secret: "test-shared-secret", tickets: [record] });
  const sheet = sheets.get("Online_Tickets");
  sheet.values[0][0] = "legacy_ticket_id";
  const before = JSON.stringify(sheet.values);

  const result = post(context, {
    secret: "test-shared-secret",
    tickets: [record],
  });
  assert.equal(result.success, false);
  assert.equal(result.error_code, "SCHEMA_MISMATCH");
  assert.equal(JSON.stringify(sheet.values), before);
});

test("upserts against the known legacy sheet schema without changing its columns", () => {
  const { context, sheets } = createHarness({
    Online_Tickets: legacyHeaders,
  });
  const record = ticket(
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002"
  );
  const payload = { secret: "test-shared-secret", tickets: [record] };

  assert.equal(post(context, payload).success, true);
  record.row.name = "Updated attendee";
  assert.equal(post(context, payload).success, true);

  const sheet = sheets.get("Online_Tickets");
  assert.deepEqual(sheet.values[0], legacyHeaders);
  assert.equal(sheet.getLastColumn(), legacyHeaders.length);
  assert.equal(sheet.getLastRow(), 2);
  assert.equal(sheet.values[1][legacyHeaders.indexOf("ticket_id")], record.row.ticket_id);
  assert.equal(sheet.values[1][legacyHeaders.indexOf("name")], "Updated attendee");
});
