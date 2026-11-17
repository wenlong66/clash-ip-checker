const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup() {
    const context = vm.createContext({
        EventSource: class { close() {} },
        console: { error() {} }
    });
    vm.runInContext(readFileSync(join(__dirname, '../static/js/app.js'), 'utf8'), context);
    const app = context.app();
    app.isRunning = true;
    app.nodes = [{ id: 0, name: 'Test node', status: 'pending' }];
    app.connectSSE();
    return app;
}

test('Clash connection errors are visible instead of console-only', () => {
    const app = setup();
    app.eventSource.onmessage({ data: JSON.stringify({
        type: 'error', node_name: 'Clash API', error: 'Connection failed'
    }) });
    assert.match(app.error, /Connection failed/);
});

test('failed node progress replaces the pending row before completion', () => {
    const app = setup();
    app.eventSource.onmessage({ data: JSON.stringify({
        type: 'progress', progress: 1, total: 1,
        node: { id: 0, status: '❌ 失败', error: 'Source unavailable' }
    }) });
    app.eventSource.onmessage({ data: JSON.stringify({ type: 'complete', total: 1 }) });
    assert.equal(app.progress, 1);
    assert.equal(app.nodes[0].status, '❌ 失败');
    assert.equal(app.nodes[0].error, 'Source unavailable');
    assert.equal(app.isRunning, false);
});
