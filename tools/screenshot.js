// Снимки экранов портала для документации.
//
// Запуск:
//   PORTAL_URL=http://127.0.0.1 \
//   PORTAL_ADMIN_USER=admin PORTAL_ADMIN_PASS=***** \
//   PORTAL_CLIENT_USER=demo1 PORTAL_CLIENT_PASS=***** \
//   BROWSER_PATH="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" \
//   node tools/screenshot.js
//
// Требуется пакет playwright-core (npm i playwright-core).
//
// Перед съёмкой из DOM вырезаются персональные данные — список замен
// задаётся переменной MASK (формат "что=на что", через ;).
const { chromium } = require('playwright-core');
const path = require('path');
const fs = require('fs');

const BASE = process.env.PORTAL_URL || 'http://127.0.0.1';
const BROWSER = process.env.BROWSER_PATH || undefined;
const OUT = path.join(__dirname, '..', 'docs', 'screenshots');
const ADMIN = [process.env.PORTAL_ADMIN_USER || 'admin', process.env.PORTAL_ADMIN_PASS || ''];
const CLIENT = [process.env.PORTAL_CLIENT_USER || 'demo1', process.env.PORTAL_CLIENT_PASS || ''];

const DEFAULT_MASK = [
  'Гл. бухгалтер (Света)=Клиент 1',
  'Карпухин Я.В.=Клиент 2',
  'Карпухина С.В.=Клиент 3',
  'Стёпкина А.Е.=Клиент 4',
  'Евгений=Пользователь',
  'ООО «Постер57»=ООО «Пример»',
  'Бухгалтерия (1C-BUH-2025)=Бухгалтерия',
  'sveta=client1',
  'karpuhina=client3',
  'karpuhin=client2',
  'stepkina=client4',
  'dgek=demo',
];

const MASK = (process.env.MASK || DEFAULT_MASK.join(';'))
  .split(';')
  .filter(Boolean)
  .map(pair => pair.split('='))
  .filter(p => p.length === 2);

if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

async function maskPage(page) {
  await page.evaluate((pairs) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      let text = node.nodeValue;
      for (const [from, to] of pairs) {
        if (text.includes(from)) text = text.split(from).join(to);
      }
      if (text !== node.nodeValue) node.nodeValue = text;
    }
  }, MASK);
}

async function shot(page, file) {
  await maskPage(page);
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(OUT, file), fullPage: true });
}

async function login(page, user, pass) {
  await page.goto(BASE + '/login', { waitUntil: 'networkidle' });
  await page.fill('input[name=username]', user);
  await page.fill('input[name=password]', pass);
  await page.click('button[type=submit]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
}

(async () => {
  const browser = await chromium.launch({ executablePath: BROWSER, headless: true });
  const view = { viewport: { width: 1440, height: 900 }, locale: 'ru-RU' };

  const c1 = await browser.newContext(view);
  const p1 = await c1.newPage();
  await p1.goto(BASE + '/login', { waitUntil: 'networkidle' });
  await p1.waitForTimeout(600);
  await p1.screenshot({ path: path.join(OUT, '01-login.png') });

  const c2 = await browser.newContext(view);
  const p2 = await c2.newPage();
  await login(p2, CLIENT[0], CLIENT[1]);
  await shot(p2, '02-client-portal.png');
  await p2.click('button.base-config').catch(() => {});
  await p2.waitForTimeout(500);
  await shot(p2, '07-client-configurator-help.png');

  const c3 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', isMobile: true });
  const p3 = await c3.newPage();
  await login(p3, CLIENT[0], CLIENT[1]);
  await shot(p3, '03-client-mobile.png');

  const c4 = await browser.newContext(view);
  const p4 = await c4.newPage();
  await login(p4, ADMIN[0], ADMIN[1]);
  for (const [tab, file] of [['users', '04-admin-clients.png'],
                             ['bases', '05-admin-bases.png'],
                             ['access', '06-admin-access.png']]) {
    await p4.goto(`${BASE}/admin?tab=${tab}`, { waitUntil: 'networkidle' });
    await p4.waitForTimeout(400);
    await shot(p4, file);
  }

  console.log('Готово:', OUT);
  await browser.close();
})().catch(e => { console.error('Ошибка:', e.message); process.exit(1); });
