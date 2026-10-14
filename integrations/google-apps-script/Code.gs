const SHEET_HEADERS = [
  "ticket_id",
  "ticket_number",
  "registration_id",
  "ticket_type",
  "booking_quantity",
  "ticket_quantity",
  "unit_price",
  "name",
  "email",
  "phone",
  "amount_due",
  "payment_method",
  "provider_order_id",
  "provider_payment_id",
  "upi_id",
  "transaction_id_utr",
  "payment_status",
  "verified_by",
  "verified_at",
  "ticket_status",
  "ticket_generated_at",
  "email_status",
  "email_sent_at",
  "scan_status",
  "checked_in_at",
  "checked_in_by",
  "created_at",
  "updated_at",
  "last_synced_at",
];

const LEGACY_SHEET_HEADERS = [
  "ticket_id",
  "ticket_number",
  "registration_id",
  "ticket_type",
  "name",
  "email",
  "phone",
  "amount_due",
  "payment_method",
  "upi_id",
  "transaction_id_utr",
  "payment_status",
  "verified_by",
  "verified_at",
  "ticket_status",
  "ticket_generated_at",
  "email_status",
  "email_sent_at",
  "scan_status",
  "checked_in_at",
  "checked_in_by",
  "created_at",
  "updated_at",
  "last_synced_at",
];

const ALLOWED_SHEETS = new Set(["Online_Tickets", "OnSpot_Tickets"]);
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function jsonResponse(body) {
  return ContentService.createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}

function constantTimeSecretMatch(provided, expected) {
  const algorithm = Utilities.DigestAlgorithm.SHA_256;
  const charset = Utilities.Charset.UTF_8;
  const left = Utilities.computeDigest(algorithm, provided, charset);
  const right = Utilities.computeDigest(algorithm, expected, charset);
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) {
    difference |= (left[index] & 0xff) ^ (right[index] & 0xff);
  }
  return difference === 0;
}

function validateTicket(item) {
  if (!item || typeof item !== "object" ||
      !ALLOWED_SHEETS.has(item.sheet_name) ||
      !item.row || typeof item.row !== "object" ||
      Array.isArray(item.row)) {
    throw new Error("INVALID_REQUEST");
  }

  const row = item.row;
  const keys = Object.keys(row).sort();
  const expectedKeys = SHEET_HEADERS.slice().sort();
  if (keys.length !== expectedKeys.length ||
      keys.some((key, index) => key !== expectedKeys[index])) {
    throw new Error("INVALID_REQUEST");
  }
  if (typeof row.ticket_id !== "string" ||
      !UUID_PATTERN.test(row.ticket_id) ||
      typeof row.registration_id !== "string" ||
      !UUID_PATTERN.test(row.registration_id) ||
      typeof row.ticket_number !== "string" ||
      !row.ticket_number.trim() ||
      !["VERIFIED", "CAPTURED"].includes(row.payment_status) ||
      !["ISSUED", "USED", "CANCELLED"].includes(row.ticket_status)) {
    throw new Error("INVALID_REQUEST");
  }
  for (const header of SHEET_HEADERS) {
    const value = row[header];
    if (header === "booking_quantity" || header === "ticket_quantity") {
      if (!Number.isInteger(value) || value < 1) {
        throw new Error("INVALID_REQUEST");
      }
      continue;
    }
    if (typeof value !== "string") {
      throw new Error("INVALID_REQUEST");
    }
  }
  return item;
}

function sheetForTicket(spreadsheet, name) {
  let sheet = spreadsheet.getSheetByName(name);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(name);
  }

  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, SHEET_HEADERS.length).setValues([SHEET_HEADERS]);
    return { sheet, headers: SHEET_HEADERS };
  }

  const columnCount = sheet.getLastColumn();
  if (![SHEET_HEADERS.length, LEGACY_SHEET_HEADERS.length].includes(columnCount)) {
    throw new Error("SCHEMA_MISMATCH");
  }
  const headers = sheet.getRange(1, 1, 1, columnCount).getValues()[0];
  const validHeaders = [SHEET_HEADERS, LEGACY_SHEET_HEADERS].some(
    (expected) =>
      headers.length === expected.length &&
      headers.every((header, index) => header === expected[index])
  );
  if (!validHeaders) {
    throw new Error("SCHEMA_MISMATCH");
  }
  return { sheet, headers };
}

function safeCellValue(value) {
  if (typeof value === "string" && /^[=+\-@]/.test(value)) {
    return "'" + value;
  }
  return value;
}

function upsertTicket(spreadsheet, item) {
  const { sheet, headers } = sheetForTicket(spreadsheet, item.sheet_name);
  const lastRow = sheet.getLastRow();
  const rowNumbersById = new Map();
  if (lastRow > 1) {
    const ticketIdColumn = headers.indexOf("ticket_id") + 1;
    const ticketIds = sheet.getRange(2, ticketIdColumn, lastRow - 1, 1).getDisplayValues();
    ticketIds.forEach((values, index) => {
      const ticketId = values[0];
      if (!ticketId) return;
      if (rowNumbersById.has(ticketId)) {
        throw new Error("DUPLICATE_TICKET_ID");
      }
      rowNumbersById.set(ticketId, index + 2);
    });
  }

  const values = headers.map((header) => safeCellValue(item.row[header]));
  const existingRow = rowNumbersById.get(item.row.ticket_id);
  if (existingRow) {
    sheet.getRange(existingRow, 1, 1, headers.length).setValues([values]);
    return "UPDATED";
  }
  sheet.getRange(lastRow + 1, 1, 1, headers.length).setValues([values]);
  return "INSERTED";
}

function doPost(event) {
  const properties = PropertiesService.getScriptProperties();
  const expectedSecret = properties.getProperty("WEBHOOK_SECRET") || "";
  const spreadsheetId = properties.getProperty("SPREADSHEET_ID") || "";
  let request;
  try {
    request = JSON.parse(event && event.postData && event.postData.contents);
  } catch (_error) {
    return jsonResponse({
      success: false,
      processed_ticket_ids: [],
      error_code: "INVALID_JSON",
      retryable: false,
    });
  }

  if (!request || typeof request !== "object" ||
      !expectedSecret || !spreadsheetId ||
      typeof request.secret !== "string" ||
      !constantTimeSecretMatch(request.secret, expectedSecret)) {
    return jsonResponse({
      success: false,
      processed_ticket_ids: [],
      error_code: expectedSecret && spreadsheetId
        ? "AUTH_FAILED"
        : "CONFIGURATION_ERROR",
      retryable: false,
    });
  }

  if (!Array.isArray(request.tickets) ||
      request.tickets.length === 0 ||
      request.tickets.length > 50) {
    return jsonResponse({
      success: false,
      processed_ticket_ids: [],
      error_code: "INVALID_REQUEST",
      retryable: false,
    });
  }

  let tickets;
  try {
    tickets = request.tickets.map(validateTicket);
    const identifiers = tickets.map((item) => item.row.ticket_id);
    if (new Set(identifiers).size !== identifiers.length) {
      throw new Error("INVALID_REQUEST");
    }
  } catch (_error) {
    return jsonResponse({
      success: false,
      processed_ticket_ids: [],
      error_code: "INVALID_REQUEST",
      retryable: false,
    });
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(25000)) {
    return jsonResponse({
      success: false,
      processed_ticket_ids: [],
      error_code: "LOCK_TIMEOUT",
      retryable: true,
    });
  }

  const processedTicketIds = [];
  try {
    const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
    for (const item of tickets) {
      upsertTicket(spreadsheet, item);
      processedTicketIds.push(item.row.ticket_id);
    }
    return jsonResponse({
      success: true,
      processed_ticket_ids: processedTicketIds,
      error_code: "",
      retryable: false,
    });
  } catch (error) {
    const errorCode = ["SCHEMA_MISMATCH", "DUPLICATE_TICKET_ID"].includes(error.message)
      ? error.message
      : "SHEET_WRITE_FAILED";
    return jsonResponse({
      success: false,
      processed_ticket_ids: processedTicketIds,
      error_code: errorCode,
      retryable: errorCode === "SHEET_WRITE_FAILED",
    });
  } finally {
    lock.releaseLock();
  }
}
