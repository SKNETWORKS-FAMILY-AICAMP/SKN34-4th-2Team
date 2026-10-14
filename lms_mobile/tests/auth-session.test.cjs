// Run with node --test lms_mobile/tests/auth-session.test.cjs (mobile or web dependencies installed).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let ts;
try { ts = require('typescript'); } catch { ts = require('../../lms_react/node_modules/typescript'); }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
function load(file, mocks) {
  const source = fs.readFileSync(path.join(__dirname, '../src/data', file), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, process, require: id => { if (!(id in mocks)) throw Error(id); return mocks[id]; } });
  return exports;
}
function store(storage = {}) {
  const secure = { getItemAsync: async () => null, setItemAsync: async () => {}, deleteItemAsync: async () => {}, ...storage };
  const zustand = { create: init => {
    let state; const get = () => state;
    const set = value => { state = { ...state, ...(typeof value === 'function' ? value(state) : value) }; };
    state = init(set, get); return { getState: get };
  } };
  return load('sessionStore.ts', { 'expo-secure-store': secure, zustand }).useSessionStore;
}
test('late hydration cannot restore a token after logout', async () => {
  const pending = deferred(); const s = store({ getItemAsync: () => pending.promise });
  const hydrating = s.getState().hydrate(); s.getState().clear(); pending.resolve('old'); await hydrating;
  assert.equal(s.getState().refresh, null); assert.equal(s.getState().ready, true);
});
test('late hydration cannot overwrite a new login', async () => {
  const pending = deferred(); const s = store({ getItemAsync: () => pending.promise });
  const hydrating = s.getState().hydrate(); s.getState().setTokens('access', 'new'); pending.resolve('old'); await hydrating;
  assert.equal(s.getState().refresh, 'new');
});
test('secure storage writes preserve login/logout ordering', async () => {
  const pending = deferred(); const events = [];
  const s = store({ setItemAsync: async () => { events.push('save'); await pending.promise; }, deleteItemAsync: async () => { events.push('delete'); } });
  s.getState().setTokens('a', 'r'); s.getState().clear();
  await new Promise(setImmediate); assert.deepEqual(events, ['save']);
  pending.resolve(); await new Promise(setImmediate); assert.deepEqual(events, ['save', 'delete']);
});
function httpModule(s, post) {
  const client = { interceptors: { request: { use() {} }, response: { use() {} } } };
  let calls = 0;
  const axios = { create: () => ++calls === 1 ? client : { post }, isAxiosError: () => false };
  // __esModule 이 없으면 TS 6(esModuleInterop 기본 켜짐)이 { default } 로 한 번 더 감싼다
  return load('http.ts', { axios: { __esModule: true, default: axios }, './sessionStore': { useSessionStore: s } });
}
test('concurrent refresh shares one request and updates tokens', async () => {
  const s = store(); s.getState().setTokens('a', 'r'); const pending = deferred(); let calls = 0;
  const api = httpModule(s, () => { calls++; return pending.promise; });
  const a = api.refreshAccess(), b = api.refreshAccess(); assert.equal(calls, 1);
  pending.resolve({ data: { access: 'next', refresh: 'next-r' } }); await Promise.all([a, b]);
  assert.equal(s.getState().access, 'next');
});
test('refresh from the previous session cannot replace a new login', async () => {
  const s = store(); s.getState().setTokens('a', 'r'); const pending = deferred();
  const api = httpModule(s, () => pending.promise); const request = api.refreshAccess();
  s.getState().clear(); s.getState().setTokens('new-a', 'new-r');
  pending.resolve({ data: { access: 'stale', refresh: 'stale-r' } });
  await assert.rejects(request, /stale refresh/); assert.equal(s.getState().access, 'new-a');
});
