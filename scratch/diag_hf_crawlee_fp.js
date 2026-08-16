/**
 * Isolate the variable: does Crawlee's fingerprint injection (useFingerprints: true)
 * cause HF /join to serve a degraded/bot-challenge page with zero inputs?
 * Runs the SAME PlaywrightCrawler config as signup-crawler.js, toggling fingerprints.
 */
const path = require('path');
const ENGINE = 'C:\\god_ai\\api_money_bot_complete\\universal_harvester\\crawlee-engine';
process.chdir(ENGINE); // so crawlee storage resolves there
const { PlaywrightCrawler } = require(path.join(ENGINE, 'node_modules', 'crawlee'));
const { StealthUtils } = require(path.join(ENGINE, 'src', 'stealth-utils.js'));

const useFingerprints = process.argv[2] === 'fp';
console.log('=== testing with useFingerprints =', useFingerprints, '===');

(async () => {
  const stealth = new StealthUtils({ headless: false });
  const launchOptions = stealth.buildLaunchOptions();

  const crawler = new PlaywrightCrawler({
    launchContext: { launchOptions },
    browserPoolOptions: {
      useFingerprints,
      fingerprintOptions: {
        fingerprintGeneratorOptions: {
          browsers: ['chrome'],
          devices: ['desktop'],
          operatingSystems: ['windows'],
        },
      },
    },
    maxConcurrency: 1,
    requestHandlerTimeoutSecs: 120,
    async requestHandler({ page, log }) {
      await stealth.injectStealthScripts(page);
      const resp = await page.goto('https://huggingface.co/join', { waitUntil: 'domcontentloaded', timeout: 60000 });
      log.info(`status: ${resp && resp.status()}, url: ${page.url()}`);
      for (let i = 0; i < 12; i++) {
        await page.waitForTimeout(1000);
        const n = await page.locator('input:visible').count();
        if (n > 0) { log.info(`inputs visible after ${i + 1}s: ${n}`); break; }
      }
      const n = await page.locator('input:visible').count();
      log.info(`FINAL visible inputs: ${n}`);
      const body = (await page.locator('body').innerText().catch(() => '')).slice(0, 400);
      log.info(`body: ${body.replace(/\n+/g, ' | ')}`);
      await page.screenshot({ path: `d:\\omniroute-monetizer\\evidence\\hf_crawlee_fp_${useFingerprints}.png` });
    },
  });

  await crawler.run([{ url: 'https://huggingface.co/join', uniqueKey: `diag-${Date.now()}` }]);
  await crawler.teardown();
  process.exit(0);
})().catch((e) => { console.error('FATAL:', e); process.exit(1); });
