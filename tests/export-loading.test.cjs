const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(fetch) {
    const alerts = [];
    const location = { protocol: 'http:', host: '127.0.0.1:18080', href: '' };
    const context = vm.createContext({ fetch, alert: message => alerts.push(message), window: { location } });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    let modalOpened = false;
    app.selected = [0];
    app.$refs = { exportModal: { showModal: () => { modalOpened = true; } } };
    app.$nextTick = async () => {};
    return { app, alerts, location, modalOpened: () => modalOpened };
}

test('export stays busy until response and rejects duplicate requests', async () => {
    let finish;
    let calls = 0;
    const { app, modalOpened } = setup(() => {
        calls++;
        return new Promise(resolve => { finish = resolve; });
    });
    const exporting = app.exportYaml();
    assert.equal(app.isExporting, true);
    await app.exportYaml();
    assert.equal(calls, 1);
    finish({ ok: true, json: async () => ({ yaml: 'proxies: []', filename: 'nodes.yaml', url: '/exports/nodes.yaml' }) });
    await exporting;
    assert.equal(app.isExporting, false);
    assert.equal(app.exportedYaml, 'proxies: []');
    assert.equal(app.importName, 'nodes');
    assert.equal(modalOpened(), true);
});

test('HTTP and network errors clear loading and allow retry', async () => {
    for (const fetch of [
        async () => ({ ok: false, json: async () => ({ detail: 'export error' }) }),
        async () => { throw new Error('network error'); }
    ]) {
        const { app, alerts, modalOpened } = setup(fetch);
        await app.exportYaml();
        assert.equal(app.isExporting, false);
        assert.equal(modalOpened(), false);
        assert.match(alerts[0], /error/);
        await app.exportYaml();
        assert.equal(alerts.length, 2);
    }
});

test('empty selection does not start exporting', async () => {
    const { app, alerts } = setup(() => assert.fail('unexpected request'));
    app.selected = [];
    await app.exportYaml();
    assert.equal(app.isExporting, false);
    assert.equal(alerts.length, 1);
});

test('Clash import uses the custom name with URL encoding', () => {
    const { app, location } = setup();
    app.exportUrl = '/exports/nodes.yaml';
    app.exportFilename = 'nodes.yaml';
    app.importName = '  我的订阅 & 测试 #1  ';
    app.importToClash();
    const link = new URL(location.href);
    assert.equal(link.protocol, 'clash:');
    assert.equal(link.hostname, 'install-config');
    assert.equal(link.searchParams.get('name'), '我的订阅 & 测试 #1');
    assert.equal(link.searchParams.get('url'), 'http://127.0.0.1:18080/exports/nodes.yaml');
});

test('Clash import falls back to the filename for a blank name', () => {
    const { app, location } = setup();
    app.exportUrl = '/exports/nodes.yaml';
    app.exportFilename = 'nodes.yaml';
    app.importName = '   ';
    app.importToClash();
    assert.equal(new URL(location.href).searchParams.get('name'), 'nodes');
});

test('Clash import without an export link does not navigate', () => {
    const { app, alerts, location } = setup();
    app.importToClash();
    assert.equal(location.href, '');
    assert.equal(alerts.length, 1);
});
