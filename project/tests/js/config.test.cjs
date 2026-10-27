const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const project = path.resolve(__dirname, '../..');
const scripts = path.join(project, 'src/taces/presentation/static/js');
const desired = { epsilon: 0.2, k: 6, epsilonTotal: 8 };

async function pageSaveBody() {
  const fields = new Map();
  let save;
  let body;
  const context = vm.createContext({
    document: {
      getElementById(id) {
        if (!fields.has(id)) fields.set(id, {
          value: '', hidden: true, disabled: false,
          addEventListener(event, callback) {
            if (id === 'saveConfig' && event === 'click') save = callback;
          },
        });
        return fields.get(id);
      },
    },
    window: {
      SHELL: { ready: Promise.resolve() },
      API: {
        async get() {
          return {
            values: { epsilon: 0.1, k: 5, epsilonTotal: 4 },
            ranges: {
              epsilon: { min: 0.01, max: 1 },
              k: { min: 3, max: 50 },
              epsilonTotal: { min: 0.1, max: 20 },
            },
            units: {},
          };
        },
        async patch(route, payload) {
          assert.equal(route, '/api/admin/config');
          body = JSON.parse(JSON.stringify(payload));
          return { values: desired };
        },
      },
    },
  });
  vm.runInContext(readFileSync(path.join(scripts, 'pages/config.js'), 'utf8'), context);
  await new Promise(setImmediate);
  for (const [key, value] of Object.entries(desired)) {
    fields.get(`${key}Input`).value = String(value);
  }
  await save();
  return body;
}

test('the configuration page produces a request accepted by the real authenticated API', async () => {
  const body = await pageSaveBody();
  const python = process.env.TACES_TEST_PYTHON || path.join(project, '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const result = spawnSync(python, ['-c', `
import json, sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path('src').resolve()))
from taces import create_app
with TemporaryDirectory(prefix='taces-config-contract-') as directory:
    app = create_app({'TESTING': True, 'DATA_DIR': Path(directory) / 'db'})
    app.extensions['taces_database'].initialize()
    auth = app.extensions['taces_auth']
    password = 'Config-contract-password-2026!'
    auth.bootstrap_admin('admin', password)
    token, _ = auth.login('admin', password)
    client = app.test_client()
    client.set_cookie('taces_session', token, path='/api')
    response = client.patch('/api/admin/config', json=json.load(sys.stdin),
        headers={'X-CSRF-Token': auth.current(token)['csrf_token']})
    assert response.status_code == 200, (response.status_code, response.json)
    assert client.get('/api/admin/config').json['data']['values'] == {
        'epsilon': 0.2, 'k': 6, 'epsilonTotal': 8}
`], { cwd: project, input: JSON.stringify(body), encoding: 'utf8' });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr || result.stdout);
});

test('the demo configuration accepts the same request and retains saved values on read', () => {
  const context = vm.createContext({ window: {} });
  vm.runInContext(readFileSync(path.join(scripts, 'mock.js'), 'utf8'), context);
  const config = context.window.MOCK['/api/admin/config'];
  config(desired, 'PATCH');
  assert.deepEqual(JSON.parse(JSON.stringify(config(undefined, 'GET').values)), desired);
});
