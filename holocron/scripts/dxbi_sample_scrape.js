#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("/Users/eier/VV/vitevue-platform/frontend/node_modules/playwright");

const CDP_ENDPOINT = process.env.DXBI_CDP_ENDPOINT || "http://127.0.0.1:9222";
const OUTPUT_DIR =
  process.env.DXBI_SAMPLE_OUTPUT_DIR ||
  path.resolve(__dirname, "..", ".local", "dxbi-sample");
const PAGE_SIZE = Number(process.env.DXBI_SAMPLE_PAGE_SIZE || 300);
const SHARD_DAYS = Number(process.env.DXBI_SAMPLE_SHARD_DAYS || 7);
const LOCATION_ID = process.env.DXBI_SAMPLE_LOCATION_ID || "1";
const LOCATION_TEXT = process.env.DXBI_SAMPLE_LOCATION_TEXT || "Dubai";
const END_DATE = process.env.DXBI_SAMPLE_END_DATE || new Date().toISOString().slice(0, 10);
const TOTAL_REQUESTS = Number(process.env.DXBI_SAMPLE_REQUESTS || 20);
const SALES_REQUESTS = Number(
  process.env.DXBI_SAMPLE_SALES_REQUESTS || Math.ceil(TOTAL_REQUESTS / 2),
);
const RENTAL_REQUESTS = Number(
  process.env.DXBI_SAMPLE_RENTAL_REQUESTS || Math.floor(TOTAL_REQUESTS / 2),
);

const REPORTS = [
  {
    name: "sales",
    reportId: "report_soldhistory",
    tableId: "report_table_soldhistory",
    requestCount: SALES_REQUESTS,
  },
  {
    name: "rentals",
    reportId: "report_rentHistory",
    tableId: "report_table_rentHistory",
    requestCount: RENTAL_REQUESTS,
  },
];

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function parseUnitNumber(text) {
  const matches = [...normalizeText(text).matchAll(/\bNo\.\s*([^,]+)/gi)]
    .map((match) => normalizeText(match[1]))
    .filter((value) => value && !/^u-hidden$/i.test(value));
  return matches.at(-1) || "";
}

function nowStamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function parseIsoDate(value) {
  const [year, month, day] = String(value || "").split("-").map(Number);
  if (!year || !month || !day) {
    throw new Error(`Invalid ISO date: ${value}`);
  }
  return new Date(Date.UTC(year, month - 1, day));
}

function addDays(date, days) {
  const copy = new Date(date.getTime());
  copy.setUTCDate(copy.getUTCDate() + days);
  return copy;
}

function formatIsoDate(date) {
  return date.toISOString().slice(0, 10);
}

function parsePaginateHref(href, reportId) {
  const pattern = /apex\.widget\.report\.paginate\('([^']+)'\s*,\s*'([^']+)'\s*,\s*\{min:(\d+),max:(\d+),fetched:(\d+)\}\)/;
  const match = String(href || "").match(pattern);
  if (!match) {
    return null;
  }
  return {
    regionId: match[1],
    checksum: match[2],
    min: Number(match[3]),
    max: Number(match[4]),
    fetched: Number(match[5]),
    reportId,
  };
}

async function findDxbPage(browser) {
  const pages = browser.contexts().flatMap((context) => context.pages());
  const page = pages.find((candidate) => candidate.url().includes("dxbinteract.com"));
  if (!page) {
    throw new Error("No dxbinteract.com page found in the remote-debug Chrome session.");
  }
  return page;
}

async function inspectPage(page) {
  return page.evaluate(() => {
    const item = (id) => document.querySelector(`#${id}`)?.value || "";
    return {
      url: location.href,
      title: document.title,
      location_id: item("P74_DLD_LOCATION_ID"),
      location_text: item("P74_DLD_LOCATION_TEXT"),
      start_date: item("P74_START_DATE"),
      end_date: item("P74_END_DATE"),
      status: item("P74_STATUS"),
      beds: item("P74_BEDS"),
      property_type: item("P74_PROP_TYPE"),
      metric_symbol: item("P0_METRIC_SYMBOL"),
    };
  });
}

async function captureTemplate(page, report) {
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().includes("/wwv_flow.ajax?p_context=litedxb/transactions/") &&
      (request.postData() || "").includes(report.reportId === "report_soldhistory"
        ? "29609740940913885923"
        : "47624226685649900817"),
    { timeout: 10000 },
  );

  const clicked = await page.evaluate(({ reportId }) => {
    const reportEl = document.querySelector(`#${reportId}`);
    if (!reportEl) return { ok: false, reason: `missing #${reportId}` };
    const link = [...reportEl.querySelectorAll('a[href*="apex.widget.report.paginate"]')][0];
    if (!link) return { ok: false, reason: `missing paginate link in #${reportId}` };
    link.click();
    return { ok: true, href: link.getAttribute("href") || "" };
  }, report);

  if (!clicked.ok) {
    throw new Error(`${report.name}: ${clicked.reason}`);
  }

  const request = await requestPromise;
  const parsed = parsePaginateHref(clicked.href, report.reportId);
  if (!parsed) {
    throw new Error(`${report.name}: could not parse pagination href`);
  }

  return {
    url: request.url(),
    postData: request.postData() || "",
    regionId: parsed.regionId,
    checksum: parsed.checksum,
  };
}

async function applyDateWindow(page, startDate, endDate) {
  return page.evaluate(
    ({ startDate, endDate, locationId, locationText }) => {
      if (typeof window.$s !== "function") {
        throw new Error("APEX $s is not available on the page");
      }
      window.$s("P74_DLD_LOCATION_ID", locationId, null, true);
      window.$s("P74_DLD_LOCATION_TEXT", locationText, null, true);
      window.$s("P74_START_DATE", startDate, null, true);
      window.$s("P74_END_DATE", endDate, null, true);
      return {
        location_id: document.querySelector("#P74_DLD_LOCATION_ID")?.value || "",
        location_text: document.querySelector("#P74_DLD_LOCATION_TEXT")?.value || "",
        start: document.querySelector("#P74_START_DATE")?.value || "",
        end: document.querySelector("#P74_END_DATE")?.value || "",
      };
    },
    { startDate, endDate, locationId: LOCATION_ID, locationText: LOCATION_TEXT },
  );
}

async function refreshReportRegions(page) {
  await page.evaluate(() => {
    if (!window.apex?.region) {
      throw new Error("APEX region API is not available on the page");
    }
    window.apex.region("soldhistory").refresh();
    window.apex.region("rentHistory").refresh();
  });
  await page.waitForTimeout(3000);
}

async function fetchReportPage(page, template, report, minRow) {
  return page.evaluate(
    async ({ template, report, minRow, pageSize, locationId, locationText }) => {
      const params = new URLSearchParams(template.postData);
      params.set("p_pg_min_row", String(minRow));
      params.set("p_pg_max_rows", String(minRow + pageSize - 1));
      params.set("p_pg_rows_fetched", String(pageSize));
      params.set("x01", template.regionId);
      const payload = JSON.parse(params.get("p_json"));
      for (const item of payload.pageItems?.itemsToSubmit || []) {
        if (item.n === "P74_DLD_LOCATION_ID") item.v = locationId;
        if (item.n === "P74_DLD_LOCATION_TEXT") item.v = locationText;
      }
      params.set("p_json", JSON.stringify(payload));

      const response = await fetch(template.url, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest",
          Accept: "text/html, */*; q=0.01",
        },
        body: params.toString(),
      });
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const table = doc.querySelector(`#${report.tableId}`);
      const headers = {};
      if (table) {
        table.querySelectorAll("thead th").forEach((th) => {
          if (th.id) headers[th.id] = (th.innerText || th.textContent || "").replace(/\s+/g, " ").trim();
        });
      }
      const rows = table
        ? [...table.querySelectorAll("tbody tr")].map((tr, rowIndex) => {
            const columns = [...tr.querySelectorAll("td")].map((td) => {
              const header = td.getAttribute("headers") || "";
              const text = (td.innerText || td.textContent || "").replace(/\s+/g, " ").trim();
              return {
                id: header,
                label: headers[header] || "",
                text,
                html: td.innerHTML || "",
                links: [...td.querySelectorAll("a[href]")].map((a) => ({
                  text: (a.innerText || a.textContent || "").replace(/\s+/g, " ").trim(),
                  href: a.href || a.getAttribute("href") || "",
                  class: a.getAttribute("class") || "",
                })),
              };
            });
            return {
              row_index_in_response: rowIndex + 1,
              columns,
            };
          })
        : [];

      return {
        status: response.status,
        byte_length: html.length,
        row_count: rows.length,
        rows,
      };
    },
    { template, report, minRow, pageSize: PAGE_SIZE, locationId: LOCATION_ID, locationText: LOCATION_TEXT },
  );
}

function rowToRecord({ report, pageNumber, minRow, row }) {
  const byId = Object.fromEntries(row.columns.map((column) => [column.id, column]));
  const locationText = byId.PATH_NAME?.text || "";
  const specsText = byId.BEDROOM?.text || byId.PROP_SIZES?.text || "";
  const amountText = byId.TOTAL_PRICE?.text || byId.TOTAL_PRICES?.text || "";
  const dateText = byId.SOLD_BY?.text || byId.START_DATE?.text || "";
  const purchasePriceText = byId.PURCHASE_PRICE?.text || "";
  const links = row.columns.flatMap((column) => column.links || []);
  const detailUrl =
    links.find((link) => /\/sold\/t-/.test(link.href))?.href ||
    links.find((link) => /\/rent/.test(link.href))?.href ||
    "";

  return {
    transaction_type: report.name,
    page_number: pageNumber,
    shard_start_date: report.currentStartDate || "",
    shard_end_date: report.currentEndDate || "",
    min_row: minRow,
    row_index_in_response: row.row_index_in_response,
    absolute_row_number: minRow + row.row_index_in_response - 1,
    unit_number: parseUnitNumber(locationText),
    location_text: normalizeText(locationText),
    amount_text: normalizeText(amountText),
    specs_text: normalizeText(specsText),
    date_text: normalizeText(dateText),
    purchase_price_text: normalizeText(purchasePriceText),
    detail_url: detailUrl,
    columns: row.columns,
  };
}

async function run() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const stamp = nowStamp();
  const jsonlPath = path.join(OUTPUT_DIR, `dxbi_sample_${stamp}.jsonl`);
  const summaryPath = path.join(OUTPUT_DIR, `dxbi_sample_${stamp}_summary.json`);
  const stream = fs.createWriteStream(jsonlPath, { encoding: "utf8" });

  const browser = await chromium.connectOverCDP(CDP_ENDPOINT);
  try {
    const page = await findDxbPage(browser);
    const pageInfo = await inspectPage(page);
    const summary = {
      cdp_endpoint: CDP_ENDPOINT,
      page_size: PAGE_SIZE,
      shard_days: SHARD_DAYS,
      forced_location_id: LOCATION_ID,
      forced_location_text: LOCATION_TEXT,
      output_jsonl: jsonlPath,
      page: pageInfo,
      reports: [],
      started_at: new Date().toISOString(),
    };
    const endDate = parseIsoDate(END_DATE);

    for (const report of REPORTS) {
      if (report.requestCount <= 0) continue;
      const reportSummary = {
        name: report.name,
        request_count: report.requestCount,
        region_id: "",
        rows: 0,
        responses: [],
      };

      for (let index = 0; index < report.requestCount; index += 1) {
        const shardEnd = addDays(endDate, -(index * SHARD_DAYS));
        const shardStart = addDays(shardEnd, -(SHARD_DAYS - 1));
        const sampleStartDate = formatIsoDate(shardStart);
        const sampleEndDate = formatIsoDate(shardEnd);
        await applyDateWindow(page, sampleStartDate, sampleEndDate);
        await refreshReportRegions(page);
        console.error(
          `Capturing ${report.name} template for ${sampleStartDate}..${sampleEndDate}...`,
        );
        const template = await captureTemplate(page, report);
        reportSummary.region_id = template.regionId;
        report.currentStartDate = sampleStartDate;
        report.currentEndDate = sampleEndDate;
        const minRow = 1;
        const pageNumber = index + 1;
        const response = await fetchReportPage(page, template, report, minRow);
        reportSummary.responses.push({
          page_number: pageNumber,
          start_date: sampleStartDate,
          end_date: sampleEndDate,
          min_row: minRow,
          status: response.status,
          row_count: response.row_count,
          byte_length: response.byte_length,
        });

        for (const row of response.rows) {
          stream.write(
            `${JSON.stringify(rowToRecord({ report, pageNumber, minRow, row }))}\n`,
          );
        }
        reportSummary.rows += response.row_count;
        console.error(
          `${report.name} ${sampleStartDate}..${sampleEndDate} request ${pageNumber}/${report.requestCount}: ${response.row_count} rows`,
        );
      }
      summary.reports.push(reportSummary);
    }

    summary.finished_at = new Date().toISOString();
    stream.end();
    await new Promise((resolve) => stream.on("finish", resolve));
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    console.log(JSON.stringify({ jsonlPath, summaryPath, summary }, null, 2));
  } finally {
    if (typeof browser.disconnect === "function") {
      await browser.disconnect();
    }
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
