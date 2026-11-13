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
    return { app, location };
}

for (const kind of ['checked', 'qingyunti']) {
    test(`${kind} refresh filters update targets and clears stale or unreadable selections`, async () => {
        let response = { ok: true, json: async () => ({ profiles: [
            { id: 'airport', name: 'Original subscription' },
            { id: 'saved', name: 'Generated', export_filename: 'saved.yaml' }
        ] }) };
        const { app } = setup(async url => {
            assert.equal(url, `/api/failover/profiles?kind=${kind}`);
            return response;
        });
        app.exportTargets.target_profile_id = 'saved';
        await app.loadExportTargets(kind);
        assert.equal(app.exportTargets.profiles.length, 1);
        assert.equal(app.exportTargets.target_profile_id, 'saved');
        app.exportTargets.target_profile_id = 'removed';
        await app.loadExportTargets(kind);
        assert.equal(app.exportTargets.target_profile_id, '');
        app.exportTargets.target_profile_id = 'saved';
        response = { ok: false, json: async () => ({ detail: 'Cannot read profiles' }) };
        await app.loadExportTargets(kind);
        assert.equal(app.exportTargets.target_profile_id, '');
        assert.equal(app.exportTargets.profiles.length, 0);
        assert.equal(app.exportTargets.loading, false);
        assert.equal(app.exportTargets.error, 'Cannot read profiles');
    });

    test(`${kind} sends the chosen update target and hides native import after saving`, async () => {
        let calls = 0;
        const { app, location } = setup(async (url, options) => {
            calls++;
            if (kind === 'checked') {
                assert.equal(url, '/api/export');
                assert.deepEqual(JSON.parse(options.body), { node_ids: [0], target_profile_id: 'saved / &' });
            } else {
                assert.equal(url, '/api/qingyunti/export?target_profile_id=saved%20%2F%20%26');
            }
            return { ok: true, json: async () => ({ yaml: 'proxies: []', node_count: 1,
                filename: 'saved.yaml', url: '/saved', export_kind: kind, updated_profile: 'Existing' }) };
        });
        app.exportTargets.target_profile_id = 'saved / &';
        app.selected = [0];
        await (kind === 'checked' ? app.exportYaml() : app.exportQingyunti());
        assert.equal(app.exportUpdatedProfile, 'Existing');
        assert.equal(app.importName, 'Existing');
        await app.importToClash();
        assert.equal(calls, 1);
        assert.equal(location.href, '');
    });

    test(`${kind} import detects existing subscriptions and sends new imports only once`, async () => {
        for (const existing of [true, false]) {
            let calls = 0;
            const { app, location } = setup(async url => {
                calls++;
                assert.equal(url, `/api/failover/profiles?kind=${kind}`);
                return { ok: true, json: async () => ({ profiles: existing
                    ? [{ name: 'Existing', export_filename: 'saved.yaml' }] : [] }) };
            });
            await app.showExport({ yaml: '', filename: 'saved.yaml', url: '/saved', export_kind: kind });
            await app.importToClash();
            await app.importToClash();
            assert.equal(calls, 1);
            assert.equal(app.exportUpdatedProfile, existing ? 'Existing' : '');
            assert.equal(location.href.startsWith('clash://'), !existing);
        }
    });
}
