const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { chromium, firefox } = require('playwright-core');

const root = path.resolve(__dirname, '..');
const rendered = spawnSync(process.env.PYTHON || 'python', ['-c', `
import ast
import json
import sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

source = (Path(sys.argv[1]) / 'app.py').read_text(encoding='utf-8-sig')
version = next(statement.value.args[1].value for statement in ast.parse(source).body
         if isinstance(statement, ast.Assign) and any(
           isinstance(target, ast.Name) and target.id == 'APP_VERSION'
           for target in statement.targets))
env = Environment(loader=FileSystemLoader(sys.argv[1] + '/templates'),
                  autoescape=select_autoescape(['html']))
env.filters['dt_ru'] = lambda value: str(value or '')
def url_for(endpoint, **values):
    routes = {
        'help_page': '/help', 'logout': '/logout',
        'base_v8i': '/bases/1/v8i', 'portal_base_jobs': '/bases/1/jobs',
        'sandbox_delete': '/sandbox/2/delete',
    }
    return routes.get(endpoint, '/' + endpoint)
env.globals.update(asset=lambda name: '/static/' + name + '?v=' + version, url_for=url_for,
                   csrf_token=lambda: 'ui-test', get_flashed_messages=lambda: [])
context = dict(
  app_version=version, session={'name': 'Test client'}, maint=None,
    bases=[dict(id=1, slug='demo', title='Demo database', organization='Sample company',
                description='', url_path='/WEB/demo/', db_name='demo')],
    sizes={'demo': '69 MB'}, jobs={}, sandbox_keep=3, vpn_ready=False,
    sandboxes=[dict(id=2, slug='sb_demo', sandbox_title='Test sandbox',
                    source_title='Demo database', source_slug='demo', owner_name='Test client',
                    owner_login='ui-test', dump_date='2026-11-09', created_at='2026-11-09',
                    expires_at='2026-11-12', status='ready')],
    sandbox_links={2: True}, ic_host='portal.test', ic_server='server.test',
    support_name='Test support', support_url='https://example.test')
pages = {name: env.get_template(name + '.html').render(**context)
         for name in ('portal', 'help')}
pages['version'] = version
print(json.dumps(pages))
`, root], { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
assert.equal(rendered.status, 0, rendered.stderr || String(rendered.error || 'Render failed'));
const html = JSON.parse(rendered.stdout);
const engineName = process.env.PORTAL_UI_ENGINE || 'chromium';
const label = process.env.PORTAL_UI_LABEL || engineName;

async function checkViewport(browser, viewport) {
  const context = await browser.newContext({ viewport, locale: 'ru-RU' });
  let job = { active: false };
  let jobStatus = 200;
  const mutations = [];
  const errors = [];
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    assert.equal(url.origin, 'http://portal.test', 'Unexpected external request');
    if (request.method() === 'POST') mutations.push(url.pathname);
    const json = body => route.fulfill({ json: body });
    if (url.pathname === '/jobs/active') return route.fulfill({ status: jobStatus, json: job });
    if (url.pathname === '/bases/1/copies') {
      return json({ enabled: true, keep_days: 3, existing: null,
        copies: [{ path: '/test/demo.dump', when: '2026-11-09', size_h: '69 MB' }] });
    }
    if (url.pathname === '/settings/password') return json({ ok: false, error: 'Test rejection' });
    if (url.pathname === '/settings/2fa') return json({ enabled: true, backup_left: 8 });
    if (url.pathname === '/sandbox/pending') return json({ pending: 0 });
    if (url.pathname === '/logout') {
      return route.fulfill({ contentType: 'text/html', body: '<a href="/">Test login</a>' });
    }
    if (url.pathname === '/' || url.pathname === '/help') {
      return route.fulfill({ contentType: 'text/html', body: html[url.pathname === '/' ? 'portal' : 'help'] });
    }
    if (url.pathname.startsWith('/static/')) {
      const file = path.join(root, url.pathname);
      const types = { '.css': 'text/css', '.js': 'application/javascript',
        '.png': 'image/png', '.woff2': 'font/woff2' };
      return route.fulfill({ contentType: types[path.extname(file)] || 'application/octet-stream',
        body: fs.readFileSync(file) });
    }
    throw new Error('Unexpected request: ' + request.method() + ' ' + url.pathname);
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.setDefaultTimeout(5000);
  await page.clock.install();
  await page.goto('http://portal.test/');
  await page.waitForFunction(() => !!document.querySelector('[data-open="dlg-settings"] svg'));
  assert.equal(await page.locator('.brand-version').textContent(), 'v' + html.version);
  const stylesheets = await page.locator('link[rel="stylesheet"]').evaluateAll(
    links => links.map(link => link.href));
  assert.ok(stylesheets.every(href => new URL(href).searchParams.get('v') === html.version));
  const settings = page.locator('#dlg-settings');
  const band = page.locator('#job-band');
  const openSettings = () => page.locator('[data-open="dlg-settings"]').click();
  const noDialogs = async () => {
    assert.equal(await page.locator('dialog[open]').count(), 0);
    assert.equal(await page.locator('dialog:visible').count(), 0);
  };
  const oneDialog = async id => {
    assert.equal(await page.locator('dialog[open]').count(), 1);
    assert.equal(await page.locator('dialog:visible').count(), 1);
    assert.equal(await page.locator('#' + id).isVisible(), true);
  };

  await noDialogs();
  assert.equal(await band.isVisible(), false);
  await openSettings();
  await oneDialog('dlg-settings');
  assert.deepEqual(await settings.locator('.settings-view:visible').evaluateAll(
    views => views.map(view => view.id)), ['set-view-menu']);
  const bounds = await settings.boundingBox();
  assert.ok(bounds.x >= 0 && bounds.y >= 0);
  assert.ok(bounds.x + bounds.width <= viewport.width + 1);
  assert.ok(bounds.y + bounds.height <= viewport.height + 1);
  if (process.env.PORTAL_UI_ARTIFACTS) {
    fs.mkdirSync(process.env.PORTAL_UI_ARTIFACTS, { recursive: true });
    await page.screenshot({ path: path.join(process.env.PORTAL_UI_ARTIFACTS,
      `${label}-${viewport.width}-settings.png`) });
  }
  await settings.locator('[data-close]').click();
  await noDialogs();

  await openSettings();
  await page.mouse.click(3, 3);
  await noDialogs();
  await openSettings();
  await page.keyboard.press('Escape');
  await noDialogs();
  await openSettings();
  await page.mouse.click(bounds.x + bounds.width - 3, bounds.y + 55);
  await oneDialog('dlg-settings');
  await settings.locator('[data-settings-go="password"]').click();
  assert.deepEqual(await settings.locator('.settings-view:visible').evaluateAll(
    views => views.map(view => view.id)), ['set-view-password']);
  await settings.locator('[name="current"]').fill('test-only-password1');
  await settings.locator('[name="new"]').fill('test-only-password2');
  await settings.locator('[name="repeat"]').fill('test-only-password2');
  await settings.locator('form[data-settings-form="password"] button[type="submit"]').click();
  await page.waitForFunction(() => document.querySelector('#set-view-password [data-settings-msg]')
    .textContent === 'Test rejection');
  assert.equal(await page.locator('.job-overlay:visible').count(), 0);
  assert.equal(await band.isVisible(), false);
  await settings.locator('#set-view-password .settings-back').click();
  await settings.locator('[data-settings-go="2fa"]').click();
  await settings.locator('[data-settings-form="2fa-disable"]').waitFor();
  assert.deepEqual(await settings.locator('.settings-view:visible').evaluateAll(
    views => views.map(view => view.id)), ['set-view-2fa']);
  await settings.locator('#set-view-2fa .settings-back').click();
  const popupPromise = page.waitForEvent('popup');
  await settings.locator('a[href="/help"][target="_blank"]').click();
  const help = await popupPromise;
  await help.waitForLoadState();
  assert.equal(new URL(help.url()).pathname, '/help');
  assert.equal(await help.locator('a.button[href="/"]').count(), 1);
  await help.emulateMedia({ media: 'print' });
  assert.equal(await help.locator('.help-body h3:visible').count(), 8);
  assert.equal(await help.locator('.heading-actions').isVisible(), false);
  const printLayout = await help.locator('.help-body').evaluate(body => ({
    visibility: getComputedStyle(body).visibility,
    maxHeight: getComputedStyle(body).maxHeight,
    overflowY: getComputedStyle(body).overflowY,
    clipped: body.scrollHeight > body.clientHeight + 1
  }));
  assert.deepEqual(printLayout, {
    visibility: 'visible', maxHeight: 'none', overflowY: 'visible', clipped: false
  });
  if (engineName === 'chromium') {
    const pdf = await help.pdf({ format: 'A4', preferCSSPageSize: true });
    assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
    assert.ok(pdf.length > 10000, 'Instruction PDF is unexpectedly small');
    if (process.env.PORTAL_UI_ARTIFACTS) {
      fs.writeFileSync(path.join(process.env.PORTAL_UI_ARTIFACTS,
        `${label}-${viewport.width}-help.pdf`), pdf);
      await help.screenshot({ path: path.join(process.env.PORTAL_UI_ARTIFACTS,
        `${label}-${viewport.width}-help-print.png`), fullPage: true });
    }
  }
  await help.emulateMedia({ media: 'screen' });
  const equipment = await help.locator('.help-body h3').filter({ hasText: /^6\./ })
    .locator('xpath=following-sibling::ul[1]/li').allTextContents();
  assert.equal(equipment.length, 2);
  assert.ok(equipment.every(text => text.includes('через тонкого/толстого клиента')));
  await help.evaluate(() => {
    window.printCalls = 0;
    window.print = () => { window.printCalls += 1; };
  });
  const printButtons = help.locator('button[onclick="window.print()"]');
  assert.equal(await printButtons.count(), 2);
  await printButtons.nth(0).click();
  await printButtons.nth(1).click();
  assert.equal(await help.evaluate(() => window.printCalls), 2);
  await help.locator('a.button[href="/"]').click();
  await page.waitForFunction(() => document.getElementById('dlg-settings').open);
  await page.evaluate(() => document.querySelector('[data-open="dlg-config"]').click());
  await oneDialog('dlg-config');
  await page.locator('#dlg-config .modal-footer [data-close]').click();
  await noDialogs();

  for (const id of ['dlg-connect', 'dlg-v8i', 'dlg-copies', 'dlg-sb-request']) {
    await page.locator('[data-open="' + id + '"]').click();
    await oneDialog(id);
    if (id === 'dlg-v8i') {
      assert.equal(await page.locator('#v8i-download').getAttribute('href'), '/bases/1/v8i');
      assert.equal(await page.locator('#v8i-download').getAttribute('download'), 'demo.v8i');
    }
    if (id === 'dlg-copies') {
      await page.locator('#copies-list input[type="radio"]').waitFor();
      assert.equal(await page.locator('#copies-form').getAttribute('action'), '/bases/1/sandbox');
    }
    if (id === 'dlg-sb-request') {
      assert.equal(await page.locator('#sb-request-form').getAttribute('action'),
        '/sandbox/2/request-transfer');
    }
    await page.keyboard.press('Escape');
    await noDialogs();
  }
  await page.locator('form[data-confirm][data-job] button[type="submit"]').click();
  await oneDialog('dlg-confirm');
  assert.equal(await page.locator('.job-overlay:visible').count(), 0);
  assert.equal(await band.isVisible(), false);
  await page.locator('#dlg-confirm .modal-footer [data-close]').click();
  await noDialogs();
  assert.deepEqual(mutations, ['/settings/password']);

  await openSettings();
  await page.evaluate(() => {
    document.getElementById('job-band').hidden = false;
    window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
  });
  await noDialogs();
  assert.equal(await band.isVisible(), false);
  job = { active: true, title: 'Test sandbox job', percent: 42, admin: false };
  await page.clock.runFor(5100);
  await band.waitFor({ state: 'visible' });
  assert.equal(await page.locator('#job-band-pct').textContent(), '42%');
  assert.equal(await page.locator('#job-band-link').isVisible(), false);
  jobStatus = 503;
  await page.clock.runFor(5100);
  await band.waitFor({ state: 'hidden' });
  jobStatus = 200;
  await page.clock.runFor(5100);
  await band.waitFor({ state: 'visible' });
  job = { active: false };
  await page.clock.runFor(5100);
  await band.waitFor({ state: 'hidden' });
  await openSettings();
  await page.reload();
  await noDialogs();
  assert.equal(await band.isVisible(), false);
  await page.locator('.header-tools form[action="/logout"] button').click();
  await page.waitForURL('**/logout');
  await page.locator('a[href="/"]').click();
  await noDialogs();
  assert.equal(await band.isVisible(), false);
  assert.deepEqual(errors, []);
  if (process.env.PORTAL_UI_ARTIFACTS) {
    await page.screenshot({ path: path.join(process.env.PORTAL_UI_ARTIFACTS,
      `${label}-${viewport.width}-idle.png`), fullPage: true });
  }
  console.log(`PASS ${label} ${viewport.width}x${viewport.height}: version, dialogs, settings, help text/print/PDF, cancelled forms, job lifecycle, reload, logout`);
  await context.close();
}

(async () => {
  const engine = engineName === 'firefox' ? firefox : chromium;
  const options = { headless: true };
  if (process.env.BROWSER_PATH) options.executablePath = process.env.BROWSER_PATH;
  else if (engineName === 'chromium') options.channel = 'chrome';
  const browser = await engine.launch(options);
  try {
    for (const viewport of [{ width: 1920, height: 1080 }, { width: 390, height: 844 }]) {
      await checkViewport(browser, viewport);
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
