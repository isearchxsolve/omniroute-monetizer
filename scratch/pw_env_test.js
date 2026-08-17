// Simulate the OmniRoute service environment (LocalSystem, no LOCALAPPDATA)
// and test whether the bundled playwright resolves + launches chromium.
delete process.env.LOCALAPPDATA;
process.env.HOME = 'C:\\Users\\Admin';
process.env.USERPROFILE = 'C:\\Users\\Admin';
process.env.PLAYWRIGHT_BROWSERS_PATH = 'C:\\Users\\Admin\\AppData\\Local\\ms-playwright';

const os = require('os');
const fs = require('fs');
console.log('homedir=', os.homedir());
console.log('cwd=', process.cwd());
console.log('PLAYWRIGHT_BROWSERS_PATH=', process.env.PLAYWRIGHT_BROWSERS_PATH);

const pwPath = 'C:\\Users\\Admin\\AppData\\Local\\hermes\\node\\node_modules\\omniroute\\dist\\node_modules\\playwright';
(async () => {
  const { chromium } = require(pwPath);
  const exec = chromium.executablePath();
  console.log('executablePath=', exec);
  console.log('exists=', fs.existsSync(exec));
  if (!fs.existsSync(exec)) { console.log('SKIP LAUNCH'); return; }
  try {
    const browser = await chromium.launch({ headless: true });
    console.log('LAUNCH OK, version=', browser.version());
    await browser.close();
  } catch (e) {
    console.log('LAUNCH ERR:', e.message.split('\n').slice(0, 5).join(' | '));
  }
})();
