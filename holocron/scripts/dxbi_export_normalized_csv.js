#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");

const input =
  process.argv[2] || "/Users/eier/VV/DXBI-Samples/dxbi_sample_2026-07-08_latest.jsonl";
const outputDir = process.argv[3] || "/Users/eier/VV/DXBI-Samples";

function clean(value) {
  return String(value || "")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
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
  const text = clean(value);
  const match = text.match(/AED\s*([\d,.]+)\s*([KM])?/i);
  if (!match) return "";
  const amount = Number(match[1].replace(/,/g, ""));
  if (!Number.isFinite(amount)) return "";
  const suffix = (match[2] || "").toUpperCase();
  if (suffix === "M") return Math.round(amount * 1_000_000);
  if (suffix === "K") return Math.round(amount * 1_000);
  return Math.round(amount);
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
  const text = clean(value);
  const parts = text.split(",").map(clean).filter(Boolean);
  if (parts.length < 2) return { property_name: text, area_name: "" };
  return {
    property_name: parts.slice(0, -1).join(", "),
    area_name: parts.at(-1),
  };
}

function parseStatusAndTypeFromTitle(html) {
  const title = paragraphTitle(html);
  const match = title.match(/^(Offplan|Ready|New|Renewed)?\s*(.*)$/i);
  if (!match) return { status: "", property_type: "" };
  return {
    status: clean(match[1]),
    property_type: clean(match[2] || title),
  };
}

function parseUnit(row) {
  if (row.unit_number) return clean(row.unit_number);
  const location = textColumn(row, "PATH_NAME");
  const matches = [...location.matchAll(/\bNo\.\s*([^,]+)/gi)]
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
  const text = clean(specsText);
  if (/\bStudio\b/i.test(text)) return "Studio";
  const match = text.match(/\d+\s*Beds?/i);
  return match ? match[0] : "";
}

function parseSqft(specsText) {
  const match = clean(specsText).match(/([\d,]+)\s*sqft/i);
  return match ? Number(match[1].replace(/,/g, "")) : "";
}

function parseBuaSqft(specsText) {
  const match = clean(specsText).match(/•\s*([\d,]+|-)\s*sqft\s*BUA/i);
  if (!match || match[1] === "-") return "";
  return Number(match[1].replace(/,/g, ""));
}

function parseBalconySqft(specsText) {
  const match = clean(specsText).match(/Balcony\s*([\d,]+)\s*sqft/i);
  return match ? Number(match[1].replace(/,/g, "")) : "";
}

function parseSaleDate(value) {
  const match = clean(value).match(/(\d{1,2}),\s*([A-Za-z]{3})\s*(\d{4})/);
  if (!match) return "";
  const month = {
    Jan: "01",
    Feb: "02",
    Mar: "03",
    Apr: "04",
    May: "05",
    Jun: "06",
    Jul: "07",
    Aug: "08",
    Sep: "09",
    Oct: "10",
    Nov: "11",
    Dec: "12",
  }[match[2]];
  return month ? `${match[3]}-${month}-${match[1].padStart(2, "0")}` : "";
}

function parseContractDates(value) {
  const text = clean(value);
  const match = text.match(
    /(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})\s*-\s*(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})/i,
  );
  const months = text.match(/(\d+)\s*Months?/i);
  if (!match) {
    return { contract_start_date: "", contract_end_date: "", duration_months: months ? Number(months[1]) : "" };
  }
  const m = {
    Jan: "01",
    Feb: "02",
    Mar: "03",
    Apr: "04",
    May: "05",
    Jun: "06",
    Jul: "07",
    Aug: "08",
    Sep: "09",
    Oct: "10",
    Nov: "11",
    Dec: "12",
  };
  return {
    contract_start_date: `${match[3]}-${m[match[2]]}-${match[1].padStart(2, "0")}`,
    contract_end_date: `${match[6]}-${m[match[5]]}-${match[4].padStart(2, "0")}`,
    duration_months: months ? Number(months[1]) : "",
  };
}

function parseSeller(value) {
  const text = clean(value).replace(/\(u-hidden\)/gi, "").trim();
  const date = clean(text.match(/^\d{1,2},\s*[A-Za-z]{3}\s*\d{4}/)?.[0] || "");
  const rest = clean(text.slice(date.length));
  const times = rest.match(/\(([^)]*Time[^)]*)\)/i)?.[1] || "";
  const soldBy = clean(rest.replace(/\([^)]*Time[^)]*\)/i, ""));
  return { sold_by: soldBy, times_sold_text: clean(times) };
}

function parseSale(row) {
  const pathHtml = htmlColumn(row, "PATH_NAME");
  const propertyArea = splitPropertyArea(htmlTitle(pathHtml, "bold-title") || row.location_text);
  const statusType = parseStatusAndTypeFromTitle(pathHtml);
  const amountText = textColumn(row, "TOTAL_PRICE") || row.amount_text;
  const amountMatches = [...clean(amountText).matchAll(/AED\s*([\d,]+)/gi)].map((m) =>
    Number(m[1].replace(/,/g, "")),
  );
  const specs = textColumn(row, "BEDROOM") || row.specs_text;
  const soldText = textColumn(row, "SOLD_BY") || row.date_text;
  const seller = parseSeller(soldText);
  return {
    transaction_type: "sales",
    shard_start_date: row.shard_start_date,
    shard_end_date: row.shard_end_date,
    transaction_date: parseSaleDate(soldText),
    property_name: propertyArea.property_name,
    area_name: propertyArea.area_name,
    status: statusType.status,
    property_type: statusType.property_type,
    unit_number: parseUnit(row),
    sale_amount_aed: amountMatches[0] || "",
    sale_price_per_sqft_aed: amountMatches[1] || "",
    transaction_size_sqft: parseSqft(specs),
    bua_sqft: parseBuaSqft(specs),
    bedrooms: parseBedrooms(specs),
    bedroom_label: parseBedroomLabel(specs),
    balcony_sqft: parseBalconySqft(specs),
    sold_by: seller.sold_by,
    times_sold_text: seller.times_sold_text,
    detail_url: row.detail_url,
    raw_location_text: row.location_text,
    raw_amount_text: row.amount_text,
    raw_specs_text: row.specs_text,
    raw_date_text: row.date_text,
  };
}

function parseRentalStatus(value) {
  const text = clean(value);
  if (/\bRenewed\b/i.test(text)) return "Renewed";
  if (/\bNew\b/i.test(text)) return "New";
  return "";
}

function parseRental(row) {
  const pathHtml = htmlColumn(row, "PATH_NAME");
  const propertyArea = splitPropertyArea(htmlTitle(pathHtml, "bold-title") || row.location_text);
  const statusType = parseStatusAndTypeFromTitle(pathHtml);
  const amountText = textColumn(row, "TOTAL_PRICES") || row.amount_text;
  const specs = textColumn(row, "PROP_SIZES") || row.specs_text;
  const contract = parseContractDates(textColumn(row, "START_DATE") || row.date_text);
  return {
    transaction_type: "rentals",
    shard_start_date: row.shard_start_date,
    shard_end_date: row.shard_end_date,
    contract_start_date: contract.contract_start_date,
    contract_end_date: contract.contract_end_date,
    duration_months: contract.duration_months,
    property_name: propertyArea.property_name,
    area_name: propertyArea.area_name,
    contract_status: parseRentalStatus(amountText) || statusType.status,
    property_type: statusType.property_type,
    unit_number: parseUnit(row),
    rent_amount_aed: intFromText(amountText),
    rental_yield_pct: numberFromText(amountText.match(/[+-]?\d+(?:\.\d+)?%/)?.[0] || ""),
    purchase_price_text: row.purchase_price_text || textColumn(row, "PURCHASE_PRICE"),
    purchase_price_aed: parseMoneyCompact(row.purchase_price_text || textColumn(row, "PURCHASE_PRICE")),
    size_sqft: parseSqft(specs),
    bedrooms: parseBedrooms(specs),
    bedroom_label: parseBedroomLabel(specs),
    raw_location_text: row.location_text,
    raw_amount_text: row.amount_text,
    raw_specs_text: row.specs_text,
    raw_date_text: row.date_text,
  };
}

function writeCsv(filePath, headers, rows) {
  const lines = [headers.map(csvEscape).join(",")];
  for (const row of rows) {
    lines.push(headers.map((header) => csvEscape(row[header])).join(","));
  }
  fs.writeFileSync(filePath, `${lines.join("\n")}\n`);
}

fs.mkdirSync(outputDir, { recursive: true });
const records = fs.readFileSync(input, "utf8").trim().split("\n").filter(Boolean).map(JSON.parse);
const sales = records.filter((row) => row.transaction_type === "sales").map(parseSale);
const rentals = records.filter((row) => row.transaction_type === "rentals").map(parseRental);

const salesHeaders = [
  "transaction_type",
  "shard_start_date",
  "shard_end_date",
  "transaction_date",
  "property_name",
  "area_name",
  "status",
  "property_type",
  "unit_number",
  "sale_amount_aed",
  "sale_price_per_sqft_aed",
  "transaction_size_sqft",
  "bua_sqft",
  "bedrooms",
  "bedroom_label",
  "balcony_sqft",
  "sold_by",
  "times_sold_text",
  "detail_url",
  "raw_location_text",
  "raw_amount_text",
  "raw_specs_text",
  "raw_date_text",
];
const rentalHeaders = [
  "transaction_type",
  "shard_start_date",
  "shard_end_date",
  "contract_start_date",
  "contract_end_date",
  "duration_months",
  "property_name",
  "area_name",
  "contract_status",
  "property_type",
  "unit_number",
  "rent_amount_aed",
  "rental_yield_pct",
  "purchase_price_text",
  "purchase_price_aed",
  "size_sqft",
  "bedrooms",
  "bedroom_label",
  "raw_location_text",
  "raw_amount_text",
  "raw_specs_text",
  "raw_date_text",
];

const salesPath = path.join(outputDir, "dxbi_sample_2026-07-08_sales_normalized.csv");
const rentalsPath = path.join(outputDir, "dxbi_sample_2026-07-08_rentals_normalized.csv");
writeCsv(salesPath, salesHeaders, sales);
writeCsv(rentalsPath, rentalHeaders, rentals);

console.log(
  JSON.stringify(
    {
      input,
      sales_rows: sales.length,
      rentals_rows: rentals.length,
      salesPath,
      rentalsPath,
    },
    null,
    2,
  ),
);
