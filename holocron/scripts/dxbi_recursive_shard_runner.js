#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("/Users/eier/VV/vitevue-platform/frontend/node_modules/playwright");

const CDP_ENDPOINT = process.env.DXBI_CDP_ENDPOINT || "http://127.0.0.1:9222";
const OUTPUT_DIR = process.env.DXBI_SHARD_OUTPUT_DIR || "/Users/eier/VV/DXBI-Backfill/recursive-shards";
const STATE_PATH = process.env.DXBI_SHARD_STATE_PATH || path.join(OUTPUT_DIR, "checkpoint.json");
const START_DATE = process.env.DXBI_SHARD_START_DATE || "2007-01-01";
const END_DATE = process.env.DXBI_SHARD_END_DATE || new Date().toISOString().slice(0, 10);
const DIRECTION = process.env.DXBI_SHARD_DIRECTION || "desc";
const LOCATION_ID = process.env.DXBI_SHARD_LOCATION_ID || "1";
const LOCATION_TEXT = process.env.DXBI_SHARD_LOCATION_TEXT || "Dubai";
const LOCATION_SLUG = process.env.DXBI_SHARD_LOCATION_SLUG || "dubai";
const PAGE_SIZE = Number(process.env.DXBI_SHARD_PAGE_SIZE || 300);
const MAX_REQUESTS = Number(process.env.DXBI_SHARD_MAX_REQUESTS || 15000);
const DELAY_MIN_MS = Number(process.env.DXBI_SHARD_DELAY_MIN_MS || 2500);
const DELAY_MAX_MS = Number(process.env.DXBI_SHARD_DELAY_MAX_MS || 5500);
const MAX_SPLIT_DEPTH = Number(process.env.DXBI_SHARD_MAX_SPLIT_DEPTH || 16);
const MIN_PRICE_SPAN = Number(process.env.DXBI_SHARD_MIN_PRICE_SPAN || 1000);
const REPORT_NAMES = new Set(
  (process.env.DXBI_SHARD_REPORTS || "sales,rentals")
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
    priceBuckets: [
      [0, 250000],
      [250000, 500000],
      [500000, 750000],
      [750000, 1000000],
      [1000000, 1500000],
      [1500000, 2000000],
      [2000000, 3000000],
      [3000000, 5000000],
      [5000000, 10000000],
      [10000000, 20000000],
      [20000000, 50000000],
      [50000000, null],
    ],
  },
  {
    name: "rentals",
    reportId: "report_rentHistory",
    regionName: "rentHistory",
    tableId: "report_table_rentHistory",
    regionMarker: "47624226685649900817",
    priceBuckets: [
      [0, 25000],
      [25000, 50000],
      [50000, 75000],
      [75000, 100000],
      [100000, 125000],
      [125000, 150000],
      [150000, 200000],
      [200000, 300000],
      [300000, 500000],
      [500000, 1000000],
      [1000000, null],
    ],
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
  if (!year || !month || !day) throw new Error(`Invalid ISO date: ${value}`);
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

function* datesNewestFirst() {
  const start = parseIsoDate(START_DATE);
  const end = parseIsoDate(END_DATE);
  if (DIRECTION === "asc") {
    for (let day = start; day <= end; day = addDays(day, 1)) yield formatIsoDate(day);
    return;
  }
  for (let day = end; day >= start; day = addDays(day, -1)) yield formatIsoDate(day);
}

function loadState() {
  if (!fs.existsSync(STATE_PATH)) {
    return {
      version: 1,
      completed_shards: {},
      expanded_shards: {},
      failed_shards: {},
    };
  }
  return JSON.parse(fs.readFileSync(STATE_PATH, "utf8"));
}

function saveState(state) {
  fs.mkdirSync(path.dirname(STATE_PATH), { recursive: true });
  fs.writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
}

function shardKey(shard) {
  return [
    shard.report,
    shard.date,
    shard.minPrice ?? "",
    shard.maxPrice ?? "",
    shard.depth,
    shard.path,
  ].join("|");
}

function parsePaginateHref(href) {
  const pattern = /apex\.widget\.report\.paginate\('([^']+)'\s*,\s*'([^']+)'\s*,\s*\{min:(\d+),max:(\d+),fetched:(\d+)\}\)/;
  const match = String(href || "").match(pattern);
  if (!match) return null;
  return { regionId: match[1], checksum: match[2] };
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
  if (!page) throw new Error("No browser page found in the remote-debug Chrome session.");
  if (!page.url().includes("dxbinteract.com") || page.url().includes("/valuation/")) {
    await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
  }
  return page;
}

async function ensureTransactionRegions(page) {
  const info = await page.evaluate(() => ({
    url: location.href,
    has_sales_report: Boolean(document.querySelector("#report_soldhistory")),
    has_rental_report: Boolean(document.querySelector("#report_rentHistory")),
  }));
  if (info.has_sales_report && info.has_rental_report) return;
  await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  const retry = await page.evaluate(() => ({
    url: location.href,
    has_sales_report: Boolean(document.querySelector("#report_soldhistory")),
    has_rental_report: Boolean(document.querySelector("#report_rentHistory")),
  }));
  if (!retry.has_sales_report || !retry.has_rental_report) {
    throw new Error(`DXB transaction reports not found: ${JSON.stringify(retry)}`);
  }
}

async function applyShardFilters(page, shard) {
  await page.evaluate(
    ({ date, locationId, locationText, locationSlug, minPrice, maxPrice }) => {
      if (typeof window.$s !== "function") throw new Error("APEX $s is not available on the page");
      const set = (id, value) => {
        if (document.querySelector(`#${id}`)) window.$s(id, value, null, true);
      };
      set("P74_DLD_LOCATION_ID", locationId);
      set("P74_DLD_LOCATION_TEXT", locationText);
      set("P74_DLD_LOCATION", locationSlug);
      set("P74_START_DATE", date);
      set("P74_END_DATE", date);
      set("P74_MIN_PRICE", minPrice == null ? "" : String(minPrice));
      set("P74_MAX_PRICE", maxPrice == null ? "" : String(maxPrice));
      set("P74_PROJECT", "");
      set("P74_PROJECT_A", "");
      set("P74_PROJECT_A_HIDDENVALUE", "");
      set("P74_PROJECT_B", "");
      set("P74_PROJECT_B_HIDDENVALUE", "");
      set("P74_MY_PROJECT", "");
      set("P74_MY_PROJECT_HIDDENVALUE", "");
    },
    {
      date: shard.date,
      locationId: LOCATION_ID,
      locationText: LOCATION_TEXT,
      locationSlug: LOCATION_SLUG,
      minPrice: shard.minPrice,
      maxPrice: shard.maxPrice,
    },
  );
}

async function refreshReportRegion(page, report) {
  await page.evaluate(({ regionName }) => {
    if (!window.apex?.region) throw new Error("APEX region API is not available on the page");
    window.apex.region(regionName).refresh();
  }, report);
  await page.waitForTimeout(2200);
}

async function visibleRows(page, report) {
  return page.evaluate(({ tableId }) => {
    const table = document.querySelector(`#${tableId}`);
    if (!table) return [];
    const headers = {};
    table.querySelectorAll("thead th").forEach((th) => {
      if (th.id) headers[th.id] = (th.innerText || th.textContent || "").replace(/\s+/g, " ").trim();
    });
    return [...table.querySelectorAll("tbody tr")].map((tr, rowIndex) => ({
      row_index_in_response: rowIndex + 1,
      columns: [...tr.querySelectorAll("td")].map((td) => {
        const header = td.getAttribute("headers") || "";
        return {
          id: header,
          label: headers[header] || "",
          text: (td.innerText || td.textContent || "").replace(/\s+/g, " ").trim(),
          html: td.innerHTML || "",
          links: [...td.querySelectorAll("a[href]")].map((a) => ({
            text: (a.innerText || a.textContent || "").replace(/\s+/g, " ").trim(),
            href: a.href || a.getAttribute("href") || "",
            class: a.getAttribute("class") || "",
          })),
        };
      }),
    }));
  }, report);
}

async function captureTemplate(page, report) {
  const linkInfo = await page.evaluate(({ reportId }) => {
    const reportEl = document.querySelector(`#${reportId}`);
    if (!reportEl) return { ok: false, retryable: true, reason: `missing #${reportId}` };
    const link = [...reportEl.querySelectorAll('a[href*="apex.widget.report.paginate"]')][0];
    if (!link) return { ok: false, retryable: false, reason: `missing paginate link in #${reportId}` };
    return { ok: true, href: link.getAttribute("href") || "" };
  }, report);
  if (!linkInfo.ok) return linkInfo;

  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      request.url().includes("/wwv_flow.ajax?p_context=litedxb/transactions/") &&
      (request.postData() || "").includes(report.regionMarker),
    { timeout: 10000 },
  );
  await page.evaluate(({ reportId }) => {
    const link = document.querySelector(`#${reportId} a[href*="apex.widget.report.paginate"]`);
    link.click();
  }, report);
  const request = await requestPromise;
  const parsed = parsePaginateHref(linkInfo.href);
  if (!parsed) throw new Error(`${report.name}: could not parse pagination href`);
  return {
    ok: true,
    url: request.url(),
    postData: request.postData() || "",
    regionId: parsed.regionId,
  };
}

async function fetchCappedRows(page, template, report, shard) {
  return page.evaluate(
    async ({ template, report, pageSize, locationId, locationText, locationSlug, shard }) => {
      const params = new URLSearchParams(template.postData);
      params.set("p_pg_min_row", "1");
      params.set("p_pg_max_rows", String(pageSize));
      params.set("p_pg_rows_fetched", String(pageSize));
      params.set("x01", template.regionId);
      const payload = JSON.parse(params.get("p_json"));
      for (const item of payload.pageItems?.itemsToSubmit || []) {
        if (item.n === "P74_DLD_LOCATION_ID") item.v = locationId;
        if (item.n === "P74_DLD_LOCATION_TEXT") item.v = locationText;
        if (item.n === "P74_DLD_LOCATION") item.v = locationSlug;
        if (item.n === "P74_START_DATE") item.v = shard.date;
        if (item.n === "P74_END_DATE") item.v = shard.date;
        if (item.n === "P74_MIN_PRICE") item.v = shard.minPrice == null ? "" : String(shard.minPrice);
        if (item.n === "P74_MAX_PRICE") item.v = shard.maxPrice == null ? "" : String(shard.maxPrice);
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
      if (/P9999_USERNAME|apex_authentication/i.test(html)) {
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
        ? [...table.querySelectorAll("tbody tr")].map((tr, rowIndex) => ({
            row_index_in_response: rowIndex + 1,
            columns: [...tr.querySelectorAll("td")].map((td) => {
              const header = td.getAttribute("headers") || "";
              return {
                id: header,
                label: headers[header] || "",
                text: (td.innerText || td.textContent || "").replace(/\s+/g, " ").trim(),
                html: td.innerHTML || "",
                links: [...td.querySelectorAll("a[href]")].map((a) => ({
                  text: (a.innerText || a.textContent || "").replace(/\s+/g, " ").trim(),
                  href: a.href || a.getAttribute("href") || "",
                  class: a.getAttribute("class") || "",
                })),
              };
            }),
          }))
        : [];
      return { status: response.status, loginRedirect: false, byte_length: html.length, rows };
    },
    {
      template,
      report,
      pageSize: PAGE_SIZE,
      locationId: LOCATION_ID,
      locationText: LOCATION_TEXT,
      locationSlug: LOCATION_SLUG,
      shard,
    },
  );
}

function rowToRecord({ report, shard, row }) {
  const byId = Object.fromEntries(row.columns.map((column) => [column.id, column]));
  const locationText = byId.PATH_NAME?.text || "";
  const specsText = byId.BEDROOM?.text || byId.PROP_SIZES?.text || "";
  const amountText = byId.TOTAL_PRICE?.text || byId.TOTAL_PRICES?.text || "";
  const dateText = byId.SOLD_BY?.text || byId.START_DATE?.text || "";
  const purchasePriceText = byId.PURCHASE_PRICE?.text || "";
  const links = row.columns.flatMap((column) => column.links || []);
  return {
    transaction_type: report.name,
    shard_date: shard.date,
    shard_min_price: shard.minPrice ?? "",
    shard_max_price: shard.maxPrice ?? "",
    shard_depth: shard.depth,
    shard_path: shard.path,
    row_index_in_response: row.row_index_in_response,
    unit_number: parseUnitNumber(locationText),
    location_text: clean(locationText),
    amount_text: clean(amountText),
    specs_text: clean(specsText),
    date_text: clean(dateText),
    purchase_price_text: clean(purchasePriceText),
    detail_url:
      links.find((link) => /\/sold\/t-/.test(link.href))?.href ||
      links.find((link) => /\/rent/.test(link.href))?.href ||
      "",
    columns: row.columns,
  };
}

function splitShard(report, shard) {
  if (shard.depth >= MAX_SPLIT_DEPTH) return [];
  const min = shard.minPrice;
  const max = shard.maxPrice;
  if (min == null && max == null) {
    return report.priceBuckets.map(([bucketMin, bucketMax], index) => ({
      ...shard,
      minPrice: bucketMin,
      maxPrice: bucketMax,
      depth: shard.depth + 1,
      path: `${shard.path}/bucket${index}`,
    }));
  }
  if (max == null) {
    const nextMax = Math.max((min || 1) * 2, (min || 0) + MIN_PRICE_SPAN);
    return [
      { ...shard, maxPrice: nextMax, depth: shard.depth + 1, path: `${shard.path}/lte${nextMax}` },
      { ...shard, minPrice: nextMax, maxPrice: null, depth: shard.depth + 1, path: `${shard.path}/gt${nextMax}` },
    ];
  }
  if (min == null) {
    const mid = Math.floor(max / 2);
    return [
      { ...shard, minPrice: 0, maxPrice: mid, depth: shard.depth + 1, path: `${shard.path}/lte${mid}` },
      { ...shard, minPrice: mid, maxPrice: max, depth: shard.depth + 1, path: `${shard.path}/gt${mid}` },
    ];
  }
  if (max - min <= MIN_PRICE_SPAN) return [];
  const mid = Math.floor((min + max) / 2);
  return [
    { ...shard, maxPrice: mid, depth: shard.depth + 1, path: `${shard.path}/lte${mid}` },
    { ...shard, minPrice: mid, maxPrice: max, depth: shard.depth + 1, path: `${shard.path}/gt${mid}` },
  ];
}

async function run() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const state = loadState();
  const runStamp = nowStamp();
  const jsonlPath = path.join(OUTPUT_DIR, `dxbi_recursive_${runStamp}.jsonl`);
  const summaryPath = path.join(OUTPUT_DIR, `dxbi_recursive_${runStamp}_summary.json`);
  const stream = fs.createWriteStream(jsonlPath, { flags: "a", encoding: "utf8" });
  const summary = {
    started_at: new Date().toISOString(),
    output_jsonl: jsonlPath,
    checkpoint: STATE_PATH,
    requests: 0,
    terminal_shards: 0,
    expanded_shards: 0,
    rows: 0,
    stopped_reason: "",
    config: {
      start_date: START_DATE,
      end_date: END_DATE,
      direction: DIRECTION,
      reports: [...REPORT_NAMES],
      page_size: PAGE_SIZE,
      max_requests: MAX_REQUESTS,
      delay_min_ms: DELAY_MIN_MS,
      delay_max_ms: DELAY_MAX_MS,
    },
  };

  async function processShard(page, report, shard) {
    const key = shardKey(shard);
    if (state.completed_shards[key] || state.expanded_shards[key]) return;
    if (summary.requests >= MAX_REQUESTS) {
      summary.stopped_reason = "max_requests_reached";
      return;
    }

    await applyShardFilters(page, shard);
    await refreshReportRegion(page, report);
    let template = await captureTemplate(page, report);
    for (let attempt = 1; template.retryable && attempt <= 3; attempt += 1) {
      console.error(`${key}: retry ${attempt} after ${template.reason}`);
      await page.goto("https://dxbinteract.com/", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);
      await ensureTransactionRegions(page);
      await applyShardFilters(page, shard);
      await refreshReportRegion(page, report);
      template = await captureTemplate(page, report);
    }

    let response;
    if (!template.ok) {
      if (template.retryable) {
        state.failed_shards[key] = {
          reason: template.reason,
          failed_at: new Date().toISOString(),
        };
        saveState(state);
        return;
      }
      response = { status: 200, rows: await visibleRows(page, report), byte_length: 0, visibleFallback: true };
    } else {
      response = await fetchCappedRows(page, template, report, shard);
      summary.requests += 1;
      if (response.loginRedirect) throw new Error(`${key}: login redirect detected`);
      if (response.status >= 400) throw new Error(`${key}: HTTP ${response.status}`);
      await sleep(randomDelayMs());
    }

    console.error(
      `${report.name} ${shard.date} ${shard.minPrice ?? ""}-${shard.maxPrice ?? ""} depth=${shard.depth}: ${response.rows.length} rows`,
    );

    if (response.rows.length < PAGE_SIZE) {
      for (const row of response.rows) {
        stream.write(`${JSON.stringify(rowToRecord({ report, shard, row }))}\n`);
      }
      state.completed_shards[key] = {
        rows: response.rows.length,
        visible_fallback: Boolean(response.visibleFallback),
        completed_at: new Date().toISOString(),
      };
      summary.terminal_shards += 1;
      summary.rows += response.rows.length;
      saveState(state);
      return;
    }

    const children = splitShard(report, shard);
    if (!children.length) {
      state.failed_shards[key] = {
        reason: "capped shard could not be split further",
        rows: response.rows.length,
        failed_at: new Date().toISOString(),
      };
      saveState(state);
      return;
    }
    state.expanded_shards[key] = {
      rows: response.rows.length,
      child_count: children.length,
      expanded_at: new Date().toISOString(),
    };
    summary.expanded_shards += 1;
    saveState(state);
    for (const child of children) {
      await processShard(page, report, child);
      if (summary.requests >= MAX_REQUESTS) return;
    }
  }

  const browser = await chromium.connectOverCDP(CDP_ENDPOINT);
  try {
    const page = await findDxbPage(browser);
    await ensureTransactionRegions(page);
    for (const date of datesNewestFirst()) {
      for (const report of REPORTS) {
        await processShard(page, report, {
          report: report.name,
          date,
          minPrice: null,
          maxPrice: null,
          depth: 0,
          path: "root",
        });
        if (summary.requests >= MAX_REQUESTS) return;
      }
    }
    summary.stopped_reason = "completed_range";
  } finally {
    summary.finished_at = new Date().toISOString();
    stream.end();
    await new Promise((resolve) => stream.on("finish", resolve));
    fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
    if (typeof browser.disconnect === "function") await browser.disconnect();
    console.log(JSON.stringify({ jsonlPath, summaryPath, summary }, null, 2));
  }
}

run()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
