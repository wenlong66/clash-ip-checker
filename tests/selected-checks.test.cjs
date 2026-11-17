const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup(fetch) {
    const context = vm.createContext({ fetch, console, setTimeout: () => {} });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    app.yamlContent = 'proxies: [{name: A}, {name: B}, {name: C}]';
    app.connectSSE = () => { app.connected = true; };
    return app;
}

const nodes = [
    { id: 0, name: 'A-checked', risk: '12%', status: '✅' },
    { id: 2, name: 'B', status: 'pending' },
    { id: 3, name: 'C', status: 'pending' }
];

test('loading lists nodes for selection without starting a check', async () => {
    const calls = [];
    const app = setup(async (url, options) => {
        calls.push({ url, body: JSON.parse(options.body) });
        return { ok: true, json: async () => ({ nodes }) };
    });
    await app.loadNodes();
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, '/api/prepare');
    assert.equal(calls[0].body.yaml_content, app.yamlContent);
    assert.equal(app.nodes.length, 3);
    assert.deepEqual(Array.from(app.selected), [0, 2, 3]);
    assert.equal(app.isRunning, false);
    assert.equal(app.isLoadingNodes, false);
    assert.equal(app.connected, undefined);
});

test('start sends only selected IDs and preserves other rows and selection', async () => {
    const calls = [];
    const app = setup(async (url, options) => {
        calls.push({ url, body: JSON.parse(options.body) });
        if (url === '/api/validate') return { json: async () => ({ valid: true }) };
        return { ok: true, json: async () => ({ task_id: 'task', total: 2 }) };
    });
    app.nodes = nodes;
    app.selected = ['2', '3'];
    await app.startCheck();
    const start = calls.find(call => call.url === '/api/start');
    assert.deepEqual(start.body.node_ids, [2, 3]);
    assert.equal(app.nodes[0], nodes[0]);
    assert.deepEqual(Array.from(app.nodes, node => node.id), [0, 2, 3]);
    assert.deepEqual(Array.from(app.selected, Number), [2, 3]);
    assert.equal(app.total, 2);
    assert.equal(app.connected, true);
});

test('empty selection never sends a request or silently checks all nodes', async () => {
    const app = setup(() => assert.fail('unexpected request'));
    app.nodes = nodes;
    app.selected = [];
    await app.startCheck();
    assert.match(app.error, /选择|勾选/);
    assert.equal(app.isRunning, false);
});

test('a rejected start preserves results and displays the reload instruction', async () => {
    const app = setup(async url => url === '/api/validate'
        ? { json: async () => ({ valid: true }) }
        : { ok: false, status: 400, json: async () => ({ detail: '配置已改变，请重新加载节点' }) });
    app.nodes = nodes;
    app.selected = [2];
    await app.startCheck();
    assert.match(app.error, /重新加载节点/);
    assert.equal(app.nodes, nodes);
    assert.deepEqual(Array.from(app.selected), [2]);
    assert.equal(app.connected, undefined);
});

test('loading and checking cannot start during another operation', async () => {
    for (const flag of ['isRunning', 'isRechecking', 'isLoadingNodes']) {
        const app = setup(() => assert.fail('unexpected request'));
        app[flag] = true;
        app.selected = [0];
        await app.loadNodes();
        await app.startCheck();
    }
});
