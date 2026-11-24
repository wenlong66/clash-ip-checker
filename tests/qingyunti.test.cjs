const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

for (const kind of ['nodes', 'rules']) {
    test(`Shadowrocket ${kind} download uses its separate protected endpoint`, async () => {
        const filename = kind === 'rules' ? 'shadowrocket-rules.conf' : 'shadowrocket.txt';
        let downloaded;
        const context = vm.createContext({
            fetch: async url => {
                assert.equal(url, `/api/qingyunti/download/token/${filename}`);
                return { ok: true, blob: async () => ({}) };
            },
            URL: { createObjectURL: () => 'blob:fixture', revokeObjectURL() {} },
            document: { createElement: () => {
                const link = { click() { downloaded = link.download; } };
                return link;
            } },
            alert() { throw new Error('Unexpected download error'); },
        });
        vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
        const app = context.app();
        app.exportKind = 'qingyunti';
        app.exportUrl = '/api/qingyunti/download/token';
        if (kind === 'nodes') await app.downloadShadowrocket();
        else await app.downloadShadowrocket(kind);
        assert.equal(downloaded, `qingyunti-${filename}`);
        assert.equal(app.isExporting, false);
    });
}

test('Shadowrocket download ignores unsupported kinds and duplicate requests', async () => {
    const app = setup(() => { throw new Error('Unexpected download request'); });
    app.exportKind = 'qingyunti';
    app.exportUrl = '/api/qingyunti/download/token';
    await app.downloadShadowrocket('conf');
    app.isExporting = true;
    await app.downloadShadowrocket('rules');
    app.isExporting = false;
    app.exportKind = 'failover';
    await app.downloadShadowrocket('rules');
    app.exportKind = 'qingyunti';
    app.exportUrl = '';
    await app.downloadShadowrocket('rules');
});

test('Shadowrocket subscription download displays errors and allows retry', async () => {
    let message;
    const context = vm.createContext({
        fetch: async url => {
            assert.equal(url, '/api/qingyunti/download/token/shadowrocket.txt');
            return { ok: false, json: async () => ({ detail: '节点无法转换' }) };
        },
        alert(value) { message = value; },
    });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    app.exportKind = 'qingyunti';
    app.exportUrl = '/api/qingyunti/download/token';
    await app.downloadShadowrocket();
    assert.equal(message, '节点无法转换');
    assert.equal(app.isExporting, false);
});

function setup(fetch) {
    const context = vm.createContext({ fetch });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    app.$refs = { exportModal: { showModal() {} } };
    app.$nextTick = async () => {};
    return app;
}

test('extract opens the shared preview with the protected import URL and default name', async () => {
    const app = setup(async (url, options) => {
        assert.equal(url, '/api/qingyunti/export');
        assert.equal(options.method, 'POST');
        return { ok: true, json: async () => ({ yaml: 'proxies: []', node_count: 62,
            filename: 'qingyunti-clash.yaml', url: '/api/qingyunti/download/token',
            import_url: 'http://10.12.64.8:18080/api/qingyunti/download/token' }) };
    });
    await app.exportQingyunti();
    assert.equal(app.importName, '梯子导出');
    assert.equal(app.exportUrl, '/api/qingyunti/download/token');
    assert.equal(app.exportImportUrl, 'http://10.12.64.8:18080/api/qingyunti/download/token');
    assert.equal(app.qingyunti.nodeCount, 62);
    assert.equal(app.qingyunti.loading, false);
});

test('loading prevents duplicate requests and clears on failure so extraction can retry', async () => {
    let complete;
    let calls = 0;
    const app = setup(() => {
        calls += 1;
        return new Promise(resolve => { complete = resolve; });
    });
    const pending = app.exportQingyunti();
    assert.equal(app.qingyunti.loading, true);
    await app.exportQingyunti();
    assert.equal(calls, 1);
    complete({ ok: false, json: async () => ({ detail: '请启动梯子客户端' }) });
    await pending;
    assert.equal(app.qingyunti.error, '请启动梯子客户端');
    assert.equal(app.qingyunti.loading, false);
    const retry = app.exportQingyunti();
    assert.equal(calls, 2);
    complete({ ok: false, json: async () => { throw new Error('网络断开'); } });
    await retry;
    assert.equal(app.qingyunti.error, '网络断开');
    assert.equal(app.qingyunti.loading, false);
});
