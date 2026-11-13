const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(fetch) {
    const location = { protocol: 'http:', host: '127.0.0.1:18080', href: '' };
    const context = vm.createContext({ fetch, window: { location }, alert() {} });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    app.$refs = { exportModal: { showModal() {} } };
    app.$nextTick = async () => {};
    app.testLocation = location;
    app.failover.profiles = [{ id: 'a', name: 'A', nodes: ['Japan'] }, { id: 'b', name: 'B', nodes: ['Japan'] }];
    app.failover.primary = { profile_id: 'a', node_name: 'Japan' };
    app.failover.backup = { profile_id: 'b', node_name: 'Japan' };
    return app;
}

test('same node names across subscriptions can generate with the chosen interval and import name', async () => {
    let request;
    const app = setup(async (url, options) => {
        request = { url, body: JSON.parse(options.body) };
        return { ok: true, json: async () => ({ yaml: 'proxies: []', filename: 'generated.yaml', url: '/exports/generated.yaml' }) };
    });
    app.failover.name = '我的主备';
    app.failover.interval = '60';
    await app.generateFailover();
    assert.equal(request.url, '/api/failover/export');
    assert.equal(request.body.interval, 60);
    assert.equal(request.body.primary.profile_id, 'a');
    assert.equal(request.body.backup.profile_id, 'b');
    assert.equal(app.importName, '我的主备');
    assert.equal(app.exportUrl, '/exports/generated.yaml');
    assert.equal(app.isExporting, false);
});

test('duplicate or incomplete selections do not generate', async () => {
    const app = setup(() => assert.fail('unexpected request'));
    app.failover.backup.profile_id = 'a';
    await app.generateFailover();
    app.failover.backup.node_name = '';
    await app.generateFailover();
    assert.equal(app.canGenerateFailover, false);
});

test('refresh drops removed nodes and failed generation can be retried', async () => {
    const app = setup(async () => ({ ok: true, json: async () => ({ profiles: [{ id: 'a', name: 'A', nodes: ['new-node'] }] }) }));
    await app.loadFailoverProfiles();
    assert.equal(app.failover.loaded, true);
    assert.equal(app.failover.primary.node_name, '');
    assert.equal(app.failover.backup.node_name, '');
    assert.equal(app.failover.loading, false);
    const failing = setup(async () => ({ ok: false, json: async () => ({ detail: '订阅已变化' }) }));
    await failing.generateFailover();
    assert.equal(failing.failover.error, '订阅已变化');
    assert.equal(failing.isExporting, false);
});

test('second backup must be complete and different from the other selections', async () => {
    let body;
    const app = setup(async (url, options) => {
        body = JSON.parse(options.body);
        return { ok: true, json: async () => ({ yaml: 'proxies: []', filename: 'generated.yaml', url: '/exports/generated.yaml' }) };
    });
    app.failover.backup2.profile_id = 'b';
    assert.equal(app.canGenerateFailover, false);
    app.failover.backup2.node_name = 'Japan';
    assert.equal(app.duplicateFailoverNodes, true);
    app.failover.profiles[1].nodes.push('US');
    app.failover.backup2.node_name = 'US';
    assert.equal(app.canGenerateFailover, true);
    await app.generateFailover();
    assert.equal(body.backup2.node_name, 'US');
});

test('one existing generated profile is selected for update and passed to the backend', async () => {
    const profiles = [{ id: 'a', name: 'A', nodes: ['Japan'] }, { id: 'b', name: 'B', nodes: ['Japan'] },
        { id: 'old', name: 'Existing', nodes: [], export_filename: 'old.yaml' }];
    let body;
    const app = setup(async (url, options) => {
        if (!options) return { ok: true, json: async () => ({ profiles }) };
        body = JSON.parse(options.body);
        return { ok: true, json: async () => ({ yaml: 'proxies: []', filename: 'old.yaml', url: '/exports/old.yaml', failover: true, updated_profile: 'Existing' }) };
    });
    await app.loadFailoverProfiles();
    assert.equal(app.failover.target_profile_id, 'old');
    await app.generateFailover();
    assert.equal(body.target_profile_id, 'old');
    assert.equal(app.exportUpdatedProfile, 'Existing');
    await app.importToClash();
    assert.equal(app.testLocation.href, '');
});

test('import guard detects an already imported export and avoids adding it again', async () => {
    const app = setup(async () => ({ ok: true, json: async () => ({ profiles: [
        { id: 'old', name: 'Existing', export_filename: 'same.yaml' }
    ] }) }));
    app.exportIsFailover = true;
    app.exportUrl = '/exports/same.yaml';
    app.exportFilename = 'same.yaml';
    await app.importToClash();
    assert.equal(app.exportUpdatedProfile, 'Existing');
    assert.equal(app.testLocation.href, '');
    assert.equal(app.isImporting, false);
});

test('a new failover export only sends one native import request per preview', async () => {
    let lookups = 0;
    const app = setup(async () => {
        lookups++;
        return { ok: true, json: async () => ({ profiles: [] }) };
    });
    app.exportIsFailover = true;
    app.exportUrl = '/exports/new.yaml';
    app.exportFilename = 'new.yaml';
    app.importName = 'New';
    await app.importToClash();
    assert.equal(app.importSent, true);
    assert.equal(new URL(app.testLocation.href).searchParams.get('url'), 'http://127.0.0.1:18080/exports/new.yaml');
    await app.importToClash();
    assert.equal(lookups, 1);
});
