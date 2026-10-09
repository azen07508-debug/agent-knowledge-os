const { chromium } = require("playwright");
const fs = require("fs");
const baseURL = process.env.MINGLI_UI_URL || "http://127.0.0.1:8023";
(async () => {
  const browser = await chromium.launch({
    executablePath: "/usr/bin/chromium",
    headless: true,
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage({
    viewport: { width: 393, height: 852 },
    deviceScaleFactor: 1,
  });
  const errors = [],
    external = [];
  page.on("response", (r) => {
    if (r.status() >= 400) errors.push(r.status() + " " + r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (!r.url().startsWith(baseURL)) external.push(r.url());
  });
  await page.goto(baseURL);
  await page.evaluate(() => document.fonts.ready);
  fs.mkdirSync("reports/ui", { recursive: true });
  await page.screenshot({
    path: "reports/ui/mobile-daily.png",
    fullPage: false,
  });
  await page.locator('[data-tab="overview"]').click();
  await page.screenshot({
    path: "reports/ui/mobile-overview.png",
    fullPage: false,
  });
  await page.locator('[data-run="chart"]').first().click();
  await page.locator("#birth-dialog").waitFor({ state: "visible" });
  await page.screenshot({ path: "reports/ui/mobile-birth.png" });
  await page.locator("#submit-birth").click();
  await page.locator(".pillar").first().waitFor();
  if (await page.evaluate(() => localStorage.getItem("mingli-birth")))
    throw Error("birth information stored without opting in");
  if ((await page.locator(".pillar").count()) !== 4)
    throw Error("four pillars absent");
  await page.screenshot({
    path: "reports/ui/mobile-chart.png",
    fullPage: false,
  });
  await page.locator("#back").click();
  await page.locator('[data-run="ziwei"]').first().click();
  await page.locator(".palace-grid article").first().waitFor();
  if ((await page.locator(".palace-grid article").count()) !== 12)
    throw Error("12 palaces absent");
  await page.locator("#back").click();
  await page.locator('[data-run="western"]').first().click();
  await page.locator("#western-summary").waitFor({ state: "visible" });
  if ((await page.locator("#sun-sign").innerText()) !== "水瓶座")
    throw Error("sun wrong");
  if ((await page.locator("#moon-sign").innerText()) !== "白羊座")
    throw Error("moon wrong");
  await page.screenshot({
    path: "reports/ui/mobile-western.png",
    fullPage: false,
  });
  await page.locator("#back").click();
  await page.locator('[data-tab="chart"]').click();
  await page.locator('[data-run="windows"]').first().click();
  await page.locator("#submit-birth").click();
  await page.locator("#raw-details").waitFor({ state: "visible" });
  await page.locator('[data-tab="daily"]').click();
  await page.locator("#save-note").click();
  await page.locator('[data-tab="mine"]').click();
  if (!(await page.locator("#saved-note").innerText()).includes("静而后"))
    throw Error("save broken");
  await page.locator('[data-run="analyze"]').click();
  await page.locator("#question").fill("   ");
  await page.locator("#submit-birth").click();
  await page.locator("#form-error").waitFor({ state: "visible" });
  await page.locator("#question").fill("命盘结构");
  await page.locator("#submit-birth").click();
  await page.locator(".pillar").first().waitFor();
  await page.locator('[data-tab="overview"]').click();
  await page.locator("#overview-view [data-edit]").click();
  await page.locator("#time_precision").selectOption("day");
  await page.locator("#year").fill("2024");
  await page.locator("#month").fill("3");
  await page.locator("#day").fill("20");
  await page.locator("#timezone").fill("UTC");
  await page.locator("#submit-birth").click();
  await page.locator('[data-run="western"]').first().click();
  await page.locator("#western-summary").waitFor({ state: "visible" });
  if (
    !(await page.locator("#sun-sign").innerText()).includes("双鱼座 / 白羊座")
  )
    throw Error("date-only boundary absent");
  await page.locator('[data-tab="overview"]').click();
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("mobile overflow");
  const cards = await page.locator(".portrait").evaluateAll((els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      return { left: r.left, right: r.right };
    }),
  );
  if (cards[1].left - cards[0].right < 15)
    throw Error("portrait cards overlap");
  await page.setViewportSize({ width: 320, height: 740 });
  if (
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)
  )
    throw Error("small mobile overflow");
  await page.setViewportSize({ width: 393, height: 852 });
  await page.locator("#overview-view [data-edit]").click();
  await page.locator("#remember").check();
  await page.locator("#submit-birth").click();
  await page.reload();
  await page.locator('[data-tab="mine"]').click();
  if (
    !(await page.locator("#mine-view .profile-summary").innerText()).includes(
      "2024",
    )
  )
    throw Error("opted-in birth information not restored");
  await page.locator("#forget-profile").click();
  await page.reload();
  await page.locator('[data-tab="mine"]').click();
  if (
    (await page.locator("#mine-view .profile-summary").innerText()) !==
    "尚未填写"
  )
    throw Error("cleared profile restored");
  await page.locator("#mine-view [data-edit]").click();
  await page.keyboard.press("Escape");
  await page.locator("#birth-dialog").waitFor({ state: "hidden" });
  await page.locator('[data-tab="overview"]').click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "reports/ui/desktop-overview.png",
    fullPage: false,
  });
  await page.locator('[data-tab="daily"]').click();
  await page.screenshot({
    path: "reports/ui/desktop-daily.png",
    fullPage: false,
  });
  if (errors.length || external.length)
    throw Error(JSON.stringify({ errors, external }));
  console.log(
    "PASS: navigation, 5 real API flows, 4 pillars, 12 palaces, zodiac, date-only boundary, blank question, collection, responsive layout; 0 JS errors; 0 external requests",
  );
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
