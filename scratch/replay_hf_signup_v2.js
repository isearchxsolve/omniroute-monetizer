/**
 * Faithful replay of the engine's HF signup with full network + DOM diagnostics.
 * Uses keyboard.type (like the engine) and captures every POST response.
 */
const path = require('path');
const fs = require('fs');
const ENGINE = 'C:\\god_ai\\api_money_bot_complete\\universal_harvester\\crawlee-engine';
const { chromium } = require(path.join(ENGINE, 'node_modules', 'playwright'));
const { StealthUtils } = require(path.join(ENGINE, 'src', 'stealth-utils.js'));

const acct = JSON.parse(fs.readFileSync('d:\\omniroute-monetizer\\state\\hf_experiment_account.json', 'utf8'));

(async () => {
  const stealth = new StealthUtils({ headless: false });
  const browser = await chromium.launch(stealth.buildLaunchOptions());
  const context = await browser.newContext(stealth.buildContextOptions());
  const page = await context.newPage();
  await stealth.injectStealthScripts(page);

  // capture ALL non-GET responses
  page.on('response', async (resp) => {
    const req = resp.request();
    if (req.method() === 'GET') return;
    const u = resp.url();
    if (u.includes('analytics') || u.includes('/event') || u.includes('sentry') || u.includes('stripe')) return;
    let body = '';
    try { body = (await resp.text()).slice(0, 500); } catch (e) {}
    console.log(`[NET] ${resp.status()} ${req.method()} ${u}\n      body: ${body}`);
  });

  await page.goto('https://huggingface.co/join', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('input[name="email"]', { state: 'visible', timeout: 15000 });
  await page.waitForTimeout(1500);
  console.log('form visible');

  // human-like typing like the engine
  async function humanType(selector, text) {
    const el = page.locator(selector).first();
    await el.click();
    await page.waitForTimeout(200);
    await page.keyboard.type(text, { delay: 50 });
  }

  await humanType('input[name="email"]', acct.email);
  await humanType('input[name="password"]', acct.password);
  await page.waitForTimeout(800);
  await page.click('button[type="submit"]');
  console.log('step1 (Next) clicked');

  // wait for step 2 to appear
  let advanced = false;
  for (let i = 0; i < 15; i++) {
    await page.waitForTimeout(1000);
    const n = await page.locator('input:visible').count();
    const hasUser = await page.locator('input[name="username"], input[autocomplete="username"]').count();
    if (hasUser > 0) { advanced = true; console.log(`advanced to step 2 after ${i + 1}s`); break; }
    if (n !== 3) console.log(`  ${i + 1}s: inputs=${n}`);
  }
  if (!advanced) {
    console.log('DID NOT ADVANCE. body:', (await page.locator('body').innerText()).slice(0, 500).replace(/\n+/g, ' | '));
    await page.screenshot({ path: 'd:\\omniroute-monetizer\\evidence\\hf_replay2_stuck.png', fullPage: true });
    await browser.close();
    return;
  }

  // dump step 2 fields
  const inputs2 = await page.locator('input:visible').all();
  for (const inp of inputs2) {
    console.log('  step2 input:', JSON.stringify({
      type: await inp.getAttribute('type'),
      name: await inp.getAttribute('name'),
      autocomplete: await inp.getAttribute('autocomplete'),
      placeholder: await inp.getAttribute('placeholder'),
    }));
  }

  await humanType('input[name="username"], input[autocomplete="username"]', acct.username);
  const nameInput = page.locator('input[name="fullname"], input[name="fullName"], input[autocomplete="name"]').first();
  if (await nameInput.count()) await humanType('input[name="fullname"], input[name="fullName"], input[autocomplete="name"]', acct.fullName);

  // check all checkboxes
  const boxes = await page.locator('input[type="checkbox"]:visible').all();
  for (const cb of boxes) {
    if (!(await cb.isChecked().catch(() => false))) { await cb.check().catch(() => {}); console.log('checkbox checked'); }
  }
  await page.waitForTimeout(800);

  // capture pre-submit state
  console.log('--- pre-submit body ---');
  console.log((await page.locator('body').innerText()).slice(0, 600).replace(/\n+/g, ' | '));

  const submit2 = page.locator('button[type="submit"]:visible').last();
  console.log('submit2 button text:', await submit2.innerText().catch(() => '?'));
  await submit2.click();
  console.log('step2 submit clicked, waiting 15s...');
  await page.waitForTimeout(15000);

  console.log('--- post-submit ---');
  console.log('url:', page.url());
  console.log('body:', (await page.locator('body').innerText()).slice(0, 1500).replace(/\n+/g, ' | '));

  // captcha iframes
  const iframes = await page.locator('iframe').all();
  for (const f of iframes) {
    console.log('iframe src:', await f.getAttribute('src').catch(() => ''));
  }

  await page.screenshot({ path: 'd:\\omniroute-monetizer\\evidence\\hf_replay2_final.png', fullPage: true });
  console.log('screenshot: evidence/hf_replay2_final.png');
  console.log('cookies:', (await context.cookies()).map(c => c.name).join(', ') || '(none)');
  await browser.close();
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
