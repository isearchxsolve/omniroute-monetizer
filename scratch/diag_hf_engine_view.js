/**
 * Diagnose what HF /join actually renders under the engine's exact launch options.
 * Mimics signup-crawler.js: StealthUtils launch options + stealth injection.
 */
const path = require('path');
const ENGINE = 'C:\\god_ai\\api_money_bot_complete\\universal_harvester\\crawlee-engine';
const { chromium } = require(path.join(ENGINE, 'node_modules', 'playwright'));
const { StealthUtils } = require(path.join(ENGINE, 'src', 'stealth-utils.js'));

(async () => {
  const stealth = new StealthUtils({ headless: false });
  const launchOptions = stealth.buildLaunchOptions();
  console.log('launching with headless =', launchOptions.headless);
  const browser = await chromium.launch(launchOptions);
  const context = await browser.newContext(stealth.buildContextOptions());
  const page = await context.newPage();
  await stealth.injectStealthScripts(page);

  const resp = await page.goto('https://huggingface.co/join', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('status:', resp && resp.status());
  console.log('final url:', page.url());
  console.log('title:', await page.title());

  // wait for hydration
  for (let i = 0; i < 10; i++) {
    await page.waitForTimeout(1000);
    const n = await page.locator('input:visible').count();
    if (n > 0) { console.log(`inputs visible after ${i + 1}s:`, n); break; }
  }

  const bodyText = (await page.locator('body').innerText().catch(() => '')).slice(0, 800);
  console.log('--- body text (first 800 chars) ---');
  console.log(bodyText);

  const inputs = await page.locator('input').all();
  console.log('--- all inputs (visible or not) ---');
  for (const inp of inputs) {
    const t = await inp.getAttribute('type').catch(() => '');
    const n = await inp.getAttribute('name').catch(() => '');
    const vis = await inp.isVisible().catch(() => false);
    console.log(JSON.stringify({ type: t, name: n, visible: vis }));
  }

  // check for challenge markers
  const html = await page.content();
  console.log('--- challenge markers ---');
  console.log(JSON.stringify({
    turnstile: (html.match(/turnstile/gi) || []).length,
    recaptcha: (html.match(/recaptcha/gi) || []).length,
    hcaptcha: (html.match(/hcaptcha/gi) || []).length,
    justAMoment: html.includes('Just a moment'),
    cloudflare: (html.match(/cloudflare/gi) || []).length,
  }));

  await page.screenshot({ path: 'd:\\omniroute-monetizer\\evidence\\hf_join_engine_diag.png', fullPage: true });
  console.log('screenshot saved to evidence/hf_join_engine_diag.png');
  await browser.close();
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
