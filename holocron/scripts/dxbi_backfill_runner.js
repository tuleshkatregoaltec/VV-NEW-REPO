#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("/Users/eier/VV/vitevue-platform/frontend/node_modules/playwright");

const CDP_ENDPOINT = process.env.DXBI_CDP_ENDPOINT || "http://127.0.0.1:9222";
const OUTPUT_DIR = process.env.DXBI_BACKFILL_OUTPUT_DIR || "/Users/eier/VV/DXBI-Backfill";
const STATE_PATH = process.env.DXBI_BACKFILL_STATE_PATH || path.join(OUTPUT_DIR, "checkpoint.json");
const PAGE_SIZE = Number(process.env.DXBI_BACKFILL_PAGE_SIZE || 300);
const SHARD_DAYS = Number(process.env.DXBI_BACKFILL_SHARD_DAYS || 1);
const START_DATE = process.env.DXBI_BACKFILL_START_DATE || "2007-12-26";
const END_DATE = process.env.DXBI_BACKFILL_END_DATE || new Date().toISOString().slice(0, 10);
const DIRECTION = process.env.DXBI_BACKFILL_DIRECTION || "desc";
const LOCATION_ID = process.env.DXBI_BACKFILL_LOCATION_ID || "1";
const LOCATION_TEXT = process.env.DXBI_BACKFILL_LOCATION_TEXT || "Dubai";
const MAX_REQUESTS = Number(process.env.DXBI_BACKFILL_MAX_REQUESTS || 5000);
const DELAY_MIN_MS = Number(process.env.DXBI_BACKFILL_DELAY_MIN_MS || 3500);
const DELAY_MAX_MS = Number(process.env.DXBI_BACKFILL_DELAY_MAX_MS || 6500);
const REPORT_NAMES = new Set(
  (process.env.DXBI_BACKFILL_REPORTS || "sales,rentals")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);

const REPORTS = [
  {
    name: "sales",
    reportId: "report_soldhistory",
    regionName: "soldhistory",
    tableId: "report_table_soldhistory",
    regionMarker: "29609740940913885923",
  },
  {
    name: "rentals",
    reportId: "report_rentHistory",
    regionName: "rentHistory",
    tableId: "report_table_rentHistory",
    regionMarker: "47624226685649900817",
  },
].filter((report) => REPORT_NAMES.has(report.name));

function clean(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function randomDelayMs() {
  if (DELAY_MAX_MS <= DELAY_MIN_MS) return DELAY_MIN_MS;
  return DELAY_MIN_MS + Math.floor(Math.random() * (DELAY_MAX_MS - DELAY_MIN_MS + 1));
}

function parsePaginateHref(href) {
  const pattern = /apex\.widget\.report\.paginate\('([^']+)'\s*,\s*'([^']+)'\s*,\s*\{min:(\d+),max:(\d+),fetched:(\d+)\}\)/;
  const match = String(href || "").match(pattern);
  if (!match) return null;
  return {
    regionId: match[1],
    checksum: match[2],
    min: Number(match[3]),
    max: Number(match[4]),
    fetched: Number(match[5]),
  };
}

function pageKey(reportName, startDate, endDate, minRow) {
  return `${reportName}|${startDate}|${endDate}|${minRow}`;
}

function windowKey(reportName, startDate, endDate) {
  return `${reportName}|${startDate}|${endDate}`;
}

function loadState() {
  if (!fs.existsSync(STATE_PATH)) {
    return {
      version: 1,
      location_id: LOCATION_ID,
      location_text: LOCATION_TEXT,
      completed_pages: {},
      completed_windows: {},
      failures: [],
    };
  }
  return JSON.parse(fs.readFileSync(STATE_PATH, "utf8"));
}

function saveState(state) {
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
  fs.writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
}

function* dateWindows() {
  const start = parseIsoDate(START_DATE);
  const end = parseIsoDate(END_DATE);
  if (DIRECTION === "asc") {
    let currentStart = start;
    while (currentStart <= end) {
      const currentEnd = addDays(currentStart, SHARD_DAYS - 1);
      yield {
        startDate: formatIsoDate(currentStart),
        endDate: formatIsoDate(currentEnd > end ? end : currentEnd),
      };
      currentStart = addDays(currentEnd, 1);
    }
    return;
  }
  let currentEnd = end;
  while (currentEnd >= start) {
    const currentStart = addDays(currentEnd, -(SHARD_DAYS - 1));
    yield {
      startDate: formatIsoDate(currentStart < start ? start : currentStart),
      endDate: formatIsoDate(currentEnd),
    };
    currentEnd = addDays(currentStart, -1);
  }
}

function parseUnitNumber(text) {
  const matches = [...clean(text).matchAll(/\bNo\.\s*([^,]+)/gi)]
    .map((match) => clean(match[1]))
    .filter((value) => value && !/^u-hidden$/i.test(value));
  return matches.at(-1) || "";
}

async function findDxbPage(browser) {
  const pages = browser.contexts().flatMap((context) => context.pages());
  const page =
    pages.find((candidate) => candidate.url().includes("dxbinteract.com")) ||
    pages.find((candidate) => candidate.url() !== "about:blank");
  if (!page) {
    throw new Error("No browser page found in the remote-debug Chrome session.");
  }
  if (!page.url().includes("dxbinteract.com")) {
    await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
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
      has_sales_region: Boolean(document.querySelector("#soldhistory")),
      has_rental_region: Boolean(document.querySelector("#rentHistory")),
      has_sales_report: Boolean(document.querySelector("#report_soldhistory")),
      has_rental_report: Boolean(document.querySelector("#report_rentHistory")),
    };
  });
}

async function ensureTransactionRegions(page) {
  if (page.url().includes("/valuation/")) {
    await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
  }
  let info = await inspectPage(page);
  if (info.has_sales_report && info.has_rental_report) return info;
  await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  info = await inspectPage(page);
  if (!info.has_sales_report || !info.has_rental_report) {
    throw new Error(
      `DXB transaction reports not found. Current page: ${JSON.stringify(info)}`,
    );
  }
  return info;
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

async function refreshReportRegion(page, report) {
  await page.evaluate(({ regionName }) => {
    if (!window.apex?.region) {
      throw new Error("APEX region API is not available on the page");
    }
    window.apex.region(regionName).refresh();
  }, report);
  await page.waitForTimeout(2500);
}

async function captureTemplate(page, report) {
  const linkInfo = await page.evaluate(({ reportId }) => {
    const reportEl = document.querySelector(`#${reportId}`);
    if (!reportEl) return { ok: false, retryable: true, reason: `missing #${reportId}` };
    const link = [...reportEl.querySelectorAll('a[href*="apex.widget.report.paginate"]')][0];
    if (!link) return { ok: false, retryable: false, reason: `missing paginate link in #${reportId}` };
    return { ok: true, href: link.getAttribute("href") || "" };
  }, report);

  if (!linkInfo.ok) {
    return { empty: !linkInfo.retryable, retryable: Boolean(linkInfo.retryable), reason: linkInfo.reason };
  }

  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().includes("/wwv_flow.ajax?p_context=litedxb/transactions/") &&
      (request.postData() || "").includes(report.regionMarker),
    { timeout: 10000 },
  );
  await page.evaluate(({ reportId }) => {
    const reportEl = document.querySelector(`#${reportId}`);
    const link = [...reportEl.querySelectorAll('a[href*="apex.widget.report.paginate"]')][0];
    link.click();
  }, report);
  const request = await requestPromise;
  const parsed = parsePaginateHref(linkInfo.href);
  if (!parsed) {
    throw new Error(`${report.name}: could not parse pagination href`);
  }
  return {
    empty: false,
    url: request.url(),
    postData: request.postData() || "",
    regionId: parsed.regionId,
    checksum: parsed.checksum,
    pageSize: parsed.fetched || parsed.max || PAGE_SIZE,
  };
}

async function fetchReportPage(page, template, report, minRow) {
  return page.evaluate(
    async ({ template, report, minRow, pageSize, locationId, locationText }) => {
      const params = new URLSearchParams(template.postData);
      params.set("p_pg_min_row", String(minRow));
      params.set("p_pg_max_rows", String(pageSize));
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
      if (/login|sign in/i.test(response.url) || /P9999_USERNAME|apex_authentication/i.test(html)) {
        return { status: response.status, loginRedirect: true, byte_length: html.length, rows: [] };
      }
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
            return { row_index_in_response: rowIndex + 1, columns };
          })
        : [];

      return {
        status: response.status,
        loginRedirect: false,
        byte_length: html.length,
        rows,
      };
    },
    {
      template,
      report,
      minRow,
      pageSize: template.pageSize || PAGE_SIZE,
      locationId: LOCATION_ID,
      locationText: LOCATION_TEXT,
    },
  );
}

function rowToRecord({ report, startDate, endDate, minRow, row }) {
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
    shard_start_date: startDate,
    shard_end_date: endDate,
    min_row: minRow,
    row_index_in_response: row.row_index_in_response,
    absolute_row_number: minRow + row.row_index_in_response - 1,
    unit_number: parseUnitNumber(locationText),
    location_text: clean(locationText),
    amount_text: clean(amountText),
    specs_text: clean(specsText),
    date_text: clean(dateText),
    purchase_price_text: clean(purchasePriceText),
    detail_url: detailUrl,
    columns: row.columns,
  };
}

async function run() {
  if (!REPORTS.length) {
    throw new Error("No reports selected. Set DXBI_BACKFILL_REPORTS=sales,rentals");
  }
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const state = loadState();
  const runStamp = nowStamp();
  const jsonlPath = path.join(OUTPUT_DIR, `dxbi_backfill_${runStamp}.jsonl`);
  const summaryPath = path.join(OUTPUT_DIR, `dxbi_backfill_${runStamp}_summary.json`);
  const stream = fs.createWriteStream(jsonlPath, { flags: "a", encoding: "utf8" });
  const summary = {
    started_at: new Date().toISOString(),
    output_jsonl: jsonlPath,
    checkpoint: STATE_PATH,
    config: {
      reports: [...REPORT_NAMES],
      start_date: START_DATE,
      end_date: END_DATE,
      direction: DIRECTION,
      shard_days: SHARD_DAYS,
      page_size: PAGE_SIZE,
      max_requests: MAX_REQUESTS,
      delay_min_ms: DELAY_MIN_MS,
      delay_max_ms: DELAY_MAX_MS,
      location_id: LOCATION_ID,
      location_text: LOCATION_TEXT,
    },
    requests: 0,
    rows: 0,
    windows: [],
    stopped_reason: "",
  };

  const browser = await chromium.connectOverCDP(CDP_ENDPOINT);
  try {
    const page = await findDxbPage(browser);
    summary.page = await ensureTransactionRegions(page);

    for (const { startDate, endDate } of dateWindows()) {
      for (const report of REPORTS) {
        const wKey = windowKey(report.name, startDate, endDate);
        if (state.completed_windows[wKey]) continue;
        if (summary.requests >= MAX_REQUESTS) {
          summary.stopped_reason = "max_requests_reached";
          return;
        }

        await applyDateWindow(page, startDate, endDate);
        await refreshReportRegion(page, report);
        let template = await captureTemplate(page, report);
        if (template.retryable) {
          console.error(`${report.name} ${startDate}..${endDate}: retrying after ${template.reason}`);
          await ensureTransactionRegions(page);
          await applyDateWindow(page, startDate, endDate);
          await refreshReportRegion(page, report);
          template = await captureTemplate(page, report);
        }
        if (template.retryable) {
          throw new Error(`${report.name} ${startDate}..${endDate}: ${template.reason}`);
        }
        if (template.empty) {
          state.completed_windows[wKey] = {
            rows: 0,
            reason: template.reason,
            completed_at: new Date().toISOString(),
          };
          saveState(state);
          summary.windows.push({ report: report.name, startDate, endDate, rows: 0, pages: 0, empty: true });
          console.error(`${report.name} ${startDate}..${endDate}: empty (${template.reason})`);
          continue;
        }

        let windowRows = 0;
        let windowPages = 0;
        const effectivePageSize = template.pageSize || PAGE_SIZE;
        for (let minRow = 1; ; minRow += effectivePageSize) {
          if (summary.requests >= MAX_REQUESTS) {
            summary.stopped_reason = "max_requests_reached";
            return;
          }
          const pKey = pageKey(report.name, startDate, endDate, minRow);
          if (state.completed_pages[pKey]) {
            if (state.completed_pages[pKey].row_count < PAGE_SIZE) break;
            continue;
          }

          const response = await fetchReportPage(page, template, report, minRow);
          summary.requests += 1;
          if (response.loginRedirect) {
            throw new Error(`${report.name} ${startDate}..${endDate} min=${minRow}: login redirect detected`);
          }
          if (response.status >= 400) {
            throw new Error(`${report.name} ${startDate}..${endDate} min=${minRow}: HTTP ${response.status}`);
          }

          for (const row of response.rows) {
            stream.write(
              `${JSON.stringify(rowToRecord({ report, startDate, endDate, minRow, row }))}\n`,
            );
          }
          windowRows += response.rows.length;
          windowPages += 1;
          summary.rows += response.rows.length;
          state.completed_pages[pKey] = {
            row_count: response.rows.length,
            status: response.status,
            byte_length: response.byte_length,
            completed_at: new Date().toISOString(),
          };
          saveState(state);
          console.error(
            `${report.name} ${startDate}..${endDate} min=${minRow}: ${response.rows.length} rows`,
          );

          await sleep(randomDelayMs());
          if (response.rows.length < effectivePageSize) break;
        }
        state.completed_windows[wKey] = {
          rows: windowRows,
          pages: windowPages,
          completed_at: new Date().toISOString(),
        };
        saveState(state);
        summary.windows.push({ report: report.name, startDate, endDate, rows: windowRows, pages: windowPages });
      }
    }
    summary.stopped_reason = "completed_range";
  } finally {
    summary.finished_at = new Date().toISOString();
    stream.end();
    await new Promise((resolve) => stream.on("finish", resolve));
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    if (typeof browser.disconnect === "function") {
      await browser.disconnect();
    }
    console.log(JSON.stringify({ jsonlPath, summaryPath, summary }, null, 2));
  }
}

run()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
