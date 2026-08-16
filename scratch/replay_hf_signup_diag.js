/**
 * Replay the HF signup flow and capture exactly what the page says after each submit.
 * Uses plain Playwright (no fingerprints — proven to render the form).
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

  // capture network responses for the join API
  page.on('response', async (resp) => {
    const u = resp.url();
    if (u.includes('/join') || u.includes('/api/') || u.includes('signup') || u.includes('account')) {
      let body = '';
      try { body = (await resp.text()).slice(0, 300); } catch (e) {}
      console.log(`[NET] ${resp.status()} ${resp.request().method()} ${u}\n      body: ${body}`);
    }
  });

  await page.goto('https://huggingface.co/join', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('input[name="email"]', { state: 'visible', timeout: 15000 });
  console.log('form visible');

  // step 1: email + password
  await page.fill('input[name="email"]', acct.email);
  await page.fill('input[name="password"]', acct.password);
  await page.waitForTimeout(500);
  await page.click('button[type="submit"]');
  console.log('step1 submitted, waiting...');
  await page.waitForTimeout(4000);

  console.log('--- after step 1 ---');
  console.log('url:', page.url());
  const body1 = (await page.locator('body').innerText().catch(() => '')).slice(0, 600);
  console.log('body:', body1.replace(/\n+/g, ' | '));

  // step 2: username + fullname if present
  const inputs2 = await page.locator('input:visible').all();
  console.log('visible inputs now:', inputs2.length);
  for (const inp of inputs2) {
    const t = await inp.getAttribute('type').catch(() => '');
    const n = await inp.getAttribute('name').catch(() => '');
    const ac = await inp.getAttribute('autocomplete').catch(() => '');
    console.log(`  input type=${t} name=${n} autocomplete=${ac}`);
  }

  // try to fill username field
  const userInput = page.locator('input[name="username"], input[autocomplete="username"]').first();
  if (await userInput.count()) {
    await userInput.fill(acct.username);
    console.log('username filled');
  }
  const nameInput = page.locator('input[name="fullname"], input[name="fullName"], input[autocomplete="name"]').first();
  if (await nameInput.count()) {
    await nameInput.fill(acct.fullName);
    console.log('fullName filled');
  }
  // check all visible checkboxes
  const boxes = await page.locator('input[type="checkbox"]:visible').all();
  for (const cb of boxes) {
    const checked = await cb.isChecked().catch(() => false);
    if (!checked) { await cb.check().catch(() => {}); console.log('checkbox checked'); }
  }

  await page.waitForTimeout(500);
  const submit2 = page.locator('button[type="submit"]:visible').last();
  if (await submit2.count()) {
    await submit2.click();
    console.log('step2 submitted, waiting...');
  } else {
    console.log('NO step2 submit button found');
  }
  await page.waitForTimeout(6000);

  console.log('--- after step 2 ---');
  console.log('url:', page.url());
  const body2 = (await page.locator('body').innerText().catch(() => '')).slice(0, 1200);
  console.log('body:', body2.replace(/\n+/g, ' | '));

  // look for error messages
  const errs = await page.locator('[class*="error"], [class*="Error"], [role="alert"], .text-red-500, .text-red-600').allInnerTexts().catch(() => []);
  console.log('error elements:', JSON.stringify(errs.slice(0, 5)));

  // check for captcha
  const html = await page.content();
  console.log('captcha markers:', JSON.stringify({
    turnstile: (html.match(/turnstile/gi) || []).length,
    recaptcha: (html.match(/recaptcha/gi) || []).length,
    hcaptcha: (html.match(/hcaptcha/gi) || []).length,
  }));

  await page.screenshot({ path: 'd:\\omniroute-monetizer\\evidence\\hf_signup_replay_final.png', fullPage: true });
  console.log('screenshot: evidence/hf_signup_replay_final.png');

  const cookies = await context.cookies();
  console.log('cookies:', cookies.map(c => c.name).join(', ') || '(none)');

  await browser.close();
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
