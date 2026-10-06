#!/usr/bin/env node

/**
 * Convert DXB Interact incremental JSONL shards into date-partitioned CSVs.
 *
 * Usage:
 *   node scripts/dxbi_export_incremental_partitions.js <input-root> <output-root>
 *
 * The output is deliberately a derived layer: raw scrape files are never modified.
 */

const fs = require("node:fs");
const path = require("node:path");
const zlib = require("node:zlib");
const crypto = require("node:crypto");

const inputRoot = process.argv[2];
const outputRoot = process.argv[3];
if (!inputRoot || !outputRoot) {
  console.error("Usage: node dxbi_export_incremental_partitions.js <input-root> <output-root>");
  process.exit(2);
}

const SALES_HEADERS = [
  "record_key", "transaction_date", "property_name", "area_name", "status", "property_type",
  "unit_number", "sale_amount_aed", "sale_price_per_sqft_aed", "transaction_size_sqft", "bua_sqft",
  "bedrooms", "bedroom_label", "balcony_sqft", "sold_by", "times_sold_text", "detail_url",
  "source_shard_date", "source_file", "scraped_at", "raw_location_text", "raw_amount_text",
  "raw_specs_text", "raw_date_text",
];
const RENTAL_HEADERS = [
  "record_key", "contract_start_date", "contract_end_date", "duration_months", "property_name",
  "area_name", "contract_status", "property_type", "unit_number", "rent_amount_aed",
  "rental_yield_pct", "purchase_price_text", "purchase_price_aed", "size_sqft", "bedrooms",
  "bedroom_label", "source_shard_date", "source_file", "scraped_at", "raw_location_text",
  "raw_amount_text", "raw_specs_text", "raw_date_text",
];

function clean(value) {
  return String(value ?? "").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim();
}

function textColumn(row, id) {
  return clean((row.columns || []).find((column) => column.id === id)?.text);
}

function htmlColumn(row, id) {
  return String((row.columns || []).find((column) => column.id === id)?.html || "");
}

function csvEscape(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function intFromText(value) {
  const match = clean(value).match(/-?\d[\d,]*/);
  return match ? Number(match[0].replace(/,/g, "")) : "";
}

function numberFromText(value) {
  const match = clean(value).match(/-?\d+(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?/);
  return match ? Number(match[0].replace(/,/g, "")) : "";
}

function parseMoneyCompact(value) {
  const match = clean(value).match(/AED\s*([\d,.]+)\s*([KM])?/i);
  if (!match) return "";
  const amount = Number(match[1].replace(/,/g, ""));
  if (!Number.isFinite(amount)) return "";
  return Math.round(amount * ({ K: 1_000, M: 1_000_000 }[(match[2] || "").toUpperCase()] || 1));
}

function htmlTitle(html, selectorHint) {
  const re = selectorHint
    ? new RegExp(`<[^>]*${selectorHint}[^>]*title="([^"]*)"`, "i")
    : /title="([^"]*)"/i;
  const match = String(html || "").match(re);
  return match ? clean(match[1]) : "";
}

function paragraphTitle(html) {
  const match = String(html || "").match(/<p\b[^>]*title="([^"]*)"/i);
  return match ? clean(match[1]) : "";
}

function splitPropertyArea(value) {
  const parts = clean(value).split(",").map(clean).filter(Boolean);
  return parts.length < 2
    ? { property_name: clean(value), area_name: "" }
    : { property_name: parts.slice(0, -1).join(", "), area_name: parts.at(-1) };
}

function parseStatusAndTypeFromTitle(html) {
  const title = paragraphTitle(html);
  const match = title.match(/^(Offplan|Ready|New|Renewed)?\s*(.*)$/i);
  return match ? { status: clean(match[1]), property_type: clean(match[2] || title) } : { status: "", property_type: "" };
}

function parseUnit(row) {
  if (row.unit_number) return clean(row.unit_number);
  const matches = [...textColumn(row, "PATH_NAME").matchAll(/\bNo\.\s*([^,]+)/gi)]
    .map((match) => clean(match[1]))
    .filter((value) => value && !/^u-hidden$/i.test(value));
  return matches.at(-1) || "";
}

function parseBedrooms(specsText) {
  const text = clean(specsText);
  if (/\bStudio\b/i.test(text)) return 0;
  const match = text.match(/(\d+)\s*Beds?/i);
  return match ? Number(match[1]) : "";
}

function parseBedroomLabel(specsText) {
  if (/\bStudio\b/i.test(clean(specsText))) return "Studio";
  return clean(specsText).match(/\d+\s*Beds?/i)?.[0] || "";
}

function parseSqft(specsText) {
  const match = clean(specsText).match(/([\d,]+)\s*sqft/i);
  return match ? Number(match[1].replace(/,/g, "")) : "";
}

function parseBuaSqft(specsText) {
  const match = clean(specsText).match(/[•·]\s*([\d,]+|-)\s*sqft\s*BUA/i);
  return !match || match[1] === "-" ? "" : Number(match[1].replace(/,/g, ""));
}

function parseBalconySqft(specsText) {
  const match = clean(specsText).match(/Balcony\s*([\d,]+)\s*sqft/i);
  return match ? Number(match[1].replace(/,/g, "")) : "";
}

function isoDate(day, mon, year) {
  const months = { Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06", Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12" };
  const month = months[`${mon[0].toUpperCase()}${mon.slice(1, 3).toLowerCase()}`];
  return month ? `${year}-${month}-${String(day).padStart(2, "0")}` : "";
}

function parseSaleDate(value) {
  const match = clean(value).match(/(\d{1,2}),\s*([A-Za-z]{3})\s*(\d{4})/);
  return match ? isoDate(match[1], match[2], match[3]) : "";
}

function parseContractDates(value) {
  const text = clean(value);
  const match = text.match(/(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s*-\s*(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})/i);
  const months = text.match(/(\d+)\s*Months?/i);
  return {
    contract_start_date: match ? isoDate(match[1], match[2], match[3]) : "",
    contract_end_date: match ? isoDate(match[4], match[5], match[6]) : "",
    duration_months: months ? Number(months[1]) : "",
  };
}

function parseSeller(value) {
  const text = clean(value).replace(/\(u-hidden\)/gi, "").trim();
  const date = clean(text.match(/^\d{1,2},\s*[A-Za-z]{3}\s*\d{4}/)?.[0] || "");
  const rest = clean(text.slice(date.length));
  const times = rest.match(/\(([^)]*Time[^)]*)\)/i)?.[1] || "";
  return { sold_by: clean(rest.replace(/\([^)]*Time[^)]*\)/i, "")), times_sold_text: clean(times) };
}

function sourceFields(row, sourceFile) {
  return {
    source_shard_date: clean(row.shard?.date),
    source_file: sourceFile,
    scraped_at: clean(row.scraped_at),
  };
}

function hashKey(parts) {
  return crypto.createHash("sha256").update(parts.map(String).join("\x1f")).digest("hex").slice(0, 24);
}

function parseSale(row, sourceFile) {
  const pathHtml = htmlColumn(row, "PATH_NAME");
  const propertyArea = splitPropertyArea(htmlTitle(pathHtml, "bold-title") || row.location_text);
  const statusType = parseStatusAndTypeFromTitle(pathHtml);
  const amountText = textColumn(row, "TOTAL_PRICE") || row.amount_text;
  const amountMatches = [...clean(amountText).matchAll(/AED\s*([\d,]+)/gi)].map((m) => Number(m[1].replace(/,/g, "")));
  const specs = textColumn(row, "BEDROOM") || row.specs_text;
  const dateText = textColumn(row, "SOLD_BY") || row.date_text;
  const transaction_date = parseSaleDate(dateText);
  const unit_number = parseUnit(row);
  const detail_url = clean(row.detail_url || (row.columns || []).flatMap((column) => column.links || []).find((link) => /\/sold\//.test(link.href || ""))?.href);
  const seller = parseSeller(dateText);
  if (!transaction_date) return null;
  return {
    record_key: hashKey([detail_url, transaction_date, unit_number, propertyArea.property_name, amountMatches[0] || "", parseSqft(specs) || ""]),
    transaction_date, property_name: propertyArea.property_name, area_name: propertyArea.area_name,
    status: statusType.status, property_type: statusType.property_type, unit_number,
    sale_amount_aed: amountMatches[0] || "", sale_price_per_sqft_aed: amountMatches[1] || "",
    transaction_size_sqft: parseSqft(specs), bua_sqft: parseBuaSqft(specs), bedrooms: parseBedrooms(specs),
    bedroom_label: parseBedroomLabel(specs), balcony_sqft: parseBalconySqft(specs), sold_by: seller.sold_by,
    times_sold_text: seller.times_sold_text, detail_url, ...sourceFields(row, sourceFile),
    raw_location_text: clean(row.location_text || textColumn(row, "PATH_NAME")), raw_amount_text: clean(row.amount_text || amountText),
    raw_specs_text: clean(row.specs_text || specs), raw_date_text: clean(row.date_text || dateText),
  };
}

function parseRental(row, sourceFile) {
  const pathHtml = htmlColumn(row, "PATH_NAME");
  const propertyArea = splitPropertyArea(htmlTitle(pathHtml, "bold-title") || row.location_text);
  const statusType = parseStatusAndTypeFromTitle(pathHtml);
  const amountText = textColumn(row, "TOTAL_PRICES") || row.amount_text;
  const specs = textColumn(row, "PROP_SIZES") || row.specs_text;
  const contract = parseContractDates(textColumn(row, "START_DATE") || row.date_text);
  if (!contract.contract_start_date) return null;
  const purchase_price_text = clean(row.purchase_price_text || textColumn(row, "PURCHASE_PRICE"));
  const unit_number = parseUnit(row);
  return {
    record_key: hashKey([contract.contract_start_date, contract.contract_end_date, unit_number, propertyArea.property_name, intFromText(amountText) || "", parseSqft(specs) || ""]),
    ...contract, property_name: propertyArea.property_name, area_name: propertyArea.area_name,
    contract_status: /\bRenewed\b/i.test(amountText) ? "Renewed" : /\bNew\b/i.test(amountText) ? "New" : statusType.status,
    property_type: statusType.property_type, unit_number, rent_amount_aed: intFromText(amountText),
    rental_yield_pct: numberFromText(amountText.match(/[+-]?\d+(?:\.\d+)?%/)?.[0] || ""),
    purchase_price_text, purchase_price_aed: parseMoneyCompact(purchase_price_text), size_sqft: parseSqft(specs),
    bedrooms: parseBedrooms(specs), bedroom_label: parseBedroomLabel(specs), ...sourceFields(row, sourceFile),
    raw_location_text: clean(row.location_text || textColumn(row, "PATH_NAME")), raw_amount_text: clean(row.amount_text || amountText),
    raw_specs_text: clean(row.specs_text || specs), raw_date_text: clean(row.date_text || textColumn(row, "START_DATE")),
  };
}

function discoverFiles(root) {
  const files = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) files.push(...discoverFiles(entryPath));
    else if (entry.name.endsWith(".jsonl") || entry.name.endsWith(".jsonl.gz")) files.push(entryPath);
  }
  return files.sort();
}

function readLines(filePath) {
  const raw = fs.readFileSync(filePath);
  return (filePath.endsWith(".gz") ? zlib.gunzipSync(raw) : raw).toString("utf8").split("\n").filter(Boolean);
}

function writePartitions(type, headers, records, dateColumn) {
  const grouped = new Map();
  for (const record of records) {
    const day = record[dateColumn];
    if (!grouped.has(day)) grouped.set(day, new Map());
    grouped.get(day).set(record.record_key, record);
  }
  const result = [];
  for (const [day, entries] of [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    const dir = path.join(outputRoot, type);
    fs.mkdirSync(dir, { recursive: true });
    const filePath = path.join(dir, `date=${day}.csv`);
    const rows = [...entries.values()].sort((a, b) => a.record_key.localeCompare(b.record_key));
    fs.writeFileSync(filePath, `${headers.map(csvEscape).join(",")}\n${rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")).join("\n")}\n`);
    result.push({ date: day, rows: rows.length, file: path.relative(outputRoot, filePath) });
  }
  return result;
}

const parsed = { sales: [], rentals: [] };
const rejected = { sales: 0, rentals: 0, malformed: 0 };
const files = discoverFiles(inputRoot);
for (const filePath of files) {
  const sourceFile = path.relative(inputRoot, filePath);
  for (const line of readLines(filePath)) {
    let row;
    try { row = JSON.parse(line); } catch { rejected.malformed += 1; continue; }
    const type = row.transaction_type === "sales" ? "sales" : row.transaction_type === "rentals" ? "rentals" : null;
    if (!type) { rejected.malformed += 1; continue; }
    const record = type === "sales" ? parseSale(row, sourceFile) : parseRental(row, sourceFile);
    if (record) parsed[type].push(record); else rejected[type] += 1;
  }
}
const manifest = {
  generated_at: new Date().toISOString(), input_root: path.resolve(inputRoot), files: files.length,
  sales: writePartitions("sales", SALES_HEADERS, parsed.sales, "transaction_date"),
  rentals: writePartitions("rentals", RENTAL_HEADERS, parsed.rentals, "contract_start_date"),
  accepted_rows: { sales: parsed.sales.length, rentals: parsed.rentals.length }, rejected,
};
fs.mkdirSync(outputRoot, { recursive: true });
fs.writeFileSync(path.join(outputRoot, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(JSON.stringify(manifest, null, 2));
