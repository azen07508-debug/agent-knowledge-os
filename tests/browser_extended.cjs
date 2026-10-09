const { chromium } = require("playwright");
const fs = require("fs");
const baseURL = process.env.MINGLI_UI_URL || "http://127.0.0.1:8023";
(async () => {
  const browser = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 393, height: 852 },
    });
    const errors = [],
      external = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) => {
      if (new URL(r.url()).origin !== new URL(baseURL).origin)
        external.push(r.url());
    });
    page.on("response", (r) => {
      if (r.status() >= 400) errors.push(r.status() + " " + r.url());
    });
    await page.goto(baseURL);
    await page.evaluate(() => document.fonts.ready);
    fs.mkdirSync("reports/ui", { recursive: true });
    await page.locator('[data-tab="chart"]').click();
    await page.locator('#chart-view [data-run="western"]').click();
    await page.locator("#birth_place").selectOption("shanghai");
    if ((await page.locator("#timezone").inputValue()) !== "Asia/Shanghai")
      throw Error("city timezone");
    await page.locator("#submit-birth").click();
    await page.locator("#house-list .fact-card").first().waitFor();
    if ((await page.locator("#house-list .fact-card").count()) !== 12)
      throw Error("houses missing");
    if ((await page.locator("#planet-list article").count()) !== 10)
      throw Error("planets missing");
    if (
      !(await page
        .locator("#western-detail")
        .innerText()
        .then((t) => t.includes("金牛座")))
    )
      throw Error("ascendant missing");
    await page.screenshot({ path: "reports/ui/mobile-full-chart.png" });
    await page
      .locator(".result-links button")
      .filter({ hasText: "宫位" })
      .click();
    await page.waitForTimeout(900);
    await page.screenshot({ path: "reports/ui/mobile-houses.png" });
    await page
      .locator(".result-links button")
      .filter({ hasText: "相位" })
      .click();
    await page.waitForTimeout(900);
    await page.screenshot({ path: "reports/ui/mobile-aspects.png" });
    await page.locator("#result-view [data-edit]").click();
    await page.locator("#house_system").selectOption("equal");
    await page.locator("#submit-birth").click();
    await page
      .locator("#western-detail button")
      .filter({ hasText: "补充" })
      .click();
    await page.locator("#submit-birth").click();
    await page.locator("#house-list").waitFor();
    await page.waitForFunction(
      () =>
        document.querySelector("#raw-details").hidden === false &&
        JSON.parse(document.querySelector("#result").textContent).chart
          .house_system === "equal",
    );
    const data = await page.locator("#result").textContent().then(JSON.parse);
    if (
      Math.abs(
        data.chart.houses[0].cusp_longitude_deg -
          data.chart.ascendant.longitude_deg,
      ) > 1e-8
    )
      throw Error("equal cusp");
    await page.locator('[data-tab="chart"]').click();
    await page.locator('[data-run="synthesis"]').click();
    await page.locator("#question").fill("我想了解事业中的表达方式");
    await page.locator("#submit-birth").click();
    await page.locator(".theme-card").first().waitFor();
    if (
      !(await page
        .locator(".system-strip")
        .innerText()
        .then((t) => t.includes("八字") && t.includes("紫微")))
    )
      throw Error("systems absent");
    if (
      !(await page
        .locator(".theme-card")
        .first()
        .innerText()
        .then((t) => t.includes("行动方式")))
    )
      throw Error("question focus absent");
    await page.screenshot({ path: "reports/ui/mobile-synthesis.png" });
    await page.locator("#result-view [data-edit]").click();
    await page.locator("#time_precision").selectOption("day");
    await page.locator("#submit-birth").click();
    await page.locator('[data-tab="chart"]').click();
    await page.locator('[data-run="synthesis"]').click();
    await page.locator("#submit-birth").click();
    await page.waitForFunction(
      () =>
        document.querySelector("#raw-details").hidden === false &&
        JSON.parse(document.querySelector("#result").textContent).charts
          ?.bazi === null,
    );
    if (
      !(await page
        .locator(".system-strip")
        .innerText()
        .then((t) => t.includes("时刻待补")))
    )
      throw Error("partial synthesis fabricated");
    await page.locator('[data-tab="chart"]').click();
    await page.locator('#chart-view [data-run="western"]').click();
    await page.waitForFunction(
      () =>
        document.querySelector("#raw-details").hidden === false &&
        JSON.parse(document.querySelector("#result").textContent).chart
          ?.time_precision === "day",
    );
    if (
      (await page.locator("#house-list .fact-card").count()) !== 0 ||
      (await page.locator(".aspect-row").count()) !== 0
    )
      throw Error("unknown time fabricated");
    await page.locator("#result-view [data-edit]").click();
    await page.locator("#time_precision").selectOption("minute");
    await page.locator("#longitude").fill("");
    await page.locator("#latitude").fill("");
    await page.locator("#submit-birth").click();
    await page.locator('[data-tab="chart"]').click();
    await page.locator('#chart-view [data-run="western"]').click();
    await page.waitForFunction(
      () =>
        document.querySelector("#raw-details").hidden === false &&
        JSON.parse(document.querySelector("#result").textContent).chart
          ?.time_precision === "minute",
    );
    if ((await page.locator("#house-list .fact-card").count()) !== 0)
      throw Error("missing place fabricated");
    if ((await page.locator("#planet-list article").count()) !== 10)
      throw Error("missing place lost planets");
    await page.screenshot({ path: "reports/ui/mobile-partial-chart.png" });
    await page
      .locator("#western-detail button")
      .filter({ hasText: "补充" })
      .click();
    await page.locator("#birth_place").selectOption("shanghai");
    await page.locator("#submit-birth").click();
    await page.locator("#house-list .fact-card").first().waitFor();
    for (const width of [320, 393, 1440]) {
      await page.setViewportSize({
        width,
        height: width === 1440 ? 1000 : 852,
      });
      if (
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        )
      )
        throw Error("overflow " + width);
    }
    await page.screenshot({
      path: "reports/ui/desktop-full-chart.png",
      fullPage: true,
    });
    await page.locator('[data-tab="chart"]').click();
    await page.locator('[data-run="synthesis"]').click();
    await page.locator("#submit-birth").click();
    await page.locator(".theme-card").first().waitFor();
    await page.screenshot({
      path: "reports/ui/desktop-synthesis.png",
      fullPage: true,
    });
    if (errors.length || external.length)
      throw Error(JSON.stringify({ errors, external }));
    console.log(
      "PASS: city input, 10 bodies, ascendant, 12 houses, house-system switching, aspects, section navigation, three-system evidence, question focus, date-only/missing-place partial results, 320/393/1440 responsive; 0 JS/HTTP errors; 0 external requests",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
