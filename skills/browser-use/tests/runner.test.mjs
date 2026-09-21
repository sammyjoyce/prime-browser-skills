// Deterministic tests for browser-use runner.mjs (no browser, no model, no network).
// Covers: eventError, validateRequest, secretValues/redactText, executeRequest
// error paths that fail before BrowserUse.create, and the CLI stdin/stdout contract.
import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync as mkdtemp } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const runnerUrl = pathToFileURL(join(here, '..', 'runner.mjs')).href;
const { secretValues, redactText, eventError, validateRequest, executeRequest, browserModelOptions } = await import(runnerUrl);

// ---------------------------------------------------------------- secretValues
test('secretValues filters by name pattern and minimum length', () => {
  const env = {
    OPENAI_API_KEY: 'sk-1234567890abcdef',
    SHORT_KEY: 'abc',
    MY_TOKEN: 'tok-abcdefgh',
    HARMLESS: 'supersecretvalue', // long value but name does not match
    DB_PASSWORD: 'hunter2hunter2',
  };
  assert.deepEqual(secretValues(env).sort(), ['hunter2hunter2', 'sk-1234567890abcdef', 'tok-abcdefgh']);
});

test('secretValues sorts longest-first so overlapping secrets redact correctly', () => {
  const env = { A_SECRET: 'abcdef123456', B_SECRET: 'xyz-abcdef123456' };
  assert.deepEqual(secretValues(env), ['xyz-abcdef123456', 'abcdef123456']);
  const redacted = redactText('leak: xyz-abcdef123456 and abcdef123456', secretValues(env));
  assert.equal(redacted, 'leak: [REDACTED] and [REDACTED]');
});

// ---------------------------------------------------------------- redactText
test('redactText replaces every occurrence, keeps clean text untouched', () => {
  assert.equal(redactText('clean text', []), 'clean text');
  assert.equal(redactText('k1 and k1', ['k1']), '[REDACTED] and [REDACTED]');
  assert.equal(redactText('nothing here', ['missing-secret']), 'nothing here');
});

test('redactText is literal, not regex (regex-special secrets are safe)', () => {
  assert.equal(redactText('value a+b*c. here', ['a+b*c.']), 'value [REDACTED] here');
});

// ---------------------------------------------------------------- eventError
const mk = (event) => ({ sequence: 1, timestamp: 0, runId: 'r', ...event });

test('eventError: run_end surfaces result.error', () => {
  assert.equal(eventError(mk({ type: 'run_end', result: { status: 'error', error: 'boom' } })), 'boom');
});

test('eventError: run_end without error (completed) yields undefined', () => {
  assert.equal(eventError(mk({ type: 'run_end', result: { status: 'completed', output: 1 } })), undefined);
});

test('eventError: message_end carries message.errorMessage', () => {
  const e = mk({ type: 'agent_event', event: { type: 'message_end', message: { role: 'assistant', errorMessage: 'OpenAI API error (401): invalid key' } } });
  assert.equal(eventError(e), 'OpenAI API error (401): invalid key');
});

test('eventError: message_update delta error wins over message-level error (at(-1) order)', () => {
  const e = mk({
    type: 'agent_event',
    event: {
      type: 'message_update',
      message: { role: 'assistant', errorMessage: 'first' },
      assistantMessageEvent: { type: 'error', reason: 'error', error: { role: 'assistant', errorMessage: 'Connection error.' } },
    },
  });
  assert.equal(eventError(e), 'Connection error.');
});

test('eventError: agent_end returns the last errorMessage across messages', () => {
  const e = mk({ type: 'agent_event', event: { type: 'agent_end', messages: [
    { role: 'assistant', errorMessage: 'err-one' },
    { role: 'toolResult' },
    { role: 'assistant', errorMessage: 'err-two' },
  ] } });
  assert.equal(eventError(e), 'err-two');
});

test('eventError: non-model events yield undefined (tool errors are not model errors)', () => {
  assert.equal(eventError(mk({ type: 'run_start', task: 't', followUp: false })), undefined);
  assert.equal(eventError(mk({ type: 'warning', message: 'w' })), undefined);
  assert.equal(eventError(mk({ type: 'paused' })), undefined);
  assert.equal(eventError(mk({ type: 'agent_event', event: { type: 'tool_execution_end', toolName: 'javascript', result: {}, isError: true } })), undefined);
  assert.equal(eventError(mk({ type: 'agent_event', event: { type: 'turn_start' } })), undefined);
});


// ---------------------------------------------------------------- browserModelOptions
// Contract (verified live against a local mock): OPENAI_BASE_URL overrides only
// the openai provider's transport URL via the public builtinModels()/setProvider
// API; model id/provider/api and auth are preserved; other providers untouched.

test('browserModelOptions: no OPENAI_BASE_URL -> no models collection, selector unchanged', () => {
  assert.deepEqual(browserModelOptions('openai/gpt-6-astra', {}), { model: 'openai/gpt-6-astra' });
  assert.deepEqual(browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: '   ' }), { model: 'openai/gpt-6-astra' });
});

test('browserModelOptions: non-openai selectors are never overridden, even with env set', () => {
  const env = { OPENAI_BASE_URL: 'https://gw.example.com/v1' };
  assert.deepEqual(browserModelOptions('anthropic/claude-sonnet-4-6', env), { model: 'anthropic/claude-sonnet-4-6' });
  assert.deepEqual(browserModelOptions('openrouter/anthropic/claude-opus-5', env), { model: 'openrouter/anthropic/claude-opus-5' });
  assert.deepEqual(browserModelOptions('openai-codex/gpt-5.4', env), { model: 'openai-codex/gpt-5.4' }); // prefix must not match
});

test('browserModelOptions: openai + env -> baseUrl overridden, id/provider/api intact', () => {
  const { model, models } = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: 'https://gw.example.com/v1' });
  assert.equal(model, 'openai/gpt-6-astra'); // exact selector preserved
  const entry = models.getModel('openai', 'gpt-6-astra');
  assert.ok(entry, 'overridden collection resolves gpt-6-astra');
  assert.equal(entry.id, 'gpt-6-astra');
  assert.equal(entry.provider, 'openai');
  assert.equal(entry.api, 'openai-responses'); // transport class preserved
  assert.equal(entry.baseUrl, 'https://gw.example.com/v1');
  assert.ok(entry.contextWindow > 0 && entry.maxTokens > 0, 'catalog metadata preserved');
});

test('browserModelOptions: env value is trimmed', () => {
  const { models } = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: '  https://gw.example.com/v1  ' });
  assert.equal(models.getModel('openai', 'gpt-6-astra').baseUrl, 'https://gw.example.com/v1');
});

test('browserModelOptions: other providers in the overridden collection keep catalog baseUrl', () => {
  const { models } = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: 'https://gw.example.com/v1' });
  assert.equal(models.getModel('anthropic', 'claude-sonnet-4-6')?.baseUrl, 'https://api.anthropic.com');
  assert.equal(models.getModel('openai', 'gpt-5.4')?.baseUrl, 'https://gw.example.com/v1', 'whole openai provider overridden');
});

test('browserModelOptions: openai auth resolver is preserved (OPENAI_API_KEY path)', () => {
  const { models } = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: 'https://gw.example.com/v1' });
  const auth = models.getProvider('openai')?.auth;
  assert.equal(auth?.apiKey?.name, 'OpenAI API key'); // envApiKeyAuth shipped with the builtin provider
});

test('browserModelOptions: calls are isolated (fresh builtinModels per call)', () => {
  const a = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: 'https://a.example.com/v1' });
  const b = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: 'https://b.example.com/v1' });
  assert.equal(a.models.getModel('openai', 'gpt-6-astra').baseUrl, 'https://a.example.com/v1');
  assert.equal(b.models.getModel('openai', 'gpt-6-astra').baseUrl, 'https://b.example.com/v1');
});

test('browserModelOptions: rejects malformed or unsafe OPENAI_BASE_URL values', () => {
  const check = (value) => browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: value });
  assert.throws(() => check('not a url'), /Invalid URL/); // raw TypeError from new URL, same as login url handling
  for (const bad of [
    'ftp://gw.example.com/v1',                                  // wrong scheme
    'http://user:pass@gw.example.com/v1',                       // embedded credentials
    'https://user@gw.example.com/v1',                           // username only
    'https://gw.example.com/v1?token=abc',                      // query string
    'https://gw.example.com/v1#section',                        // fragment
  ]) {
    assert.throws(() => check(bad), /OPENAI_BASE_URL must be an HTTP\(S\) endpoint without credentials, query, or fragment/, bad);
  }
});

test('browserModelOptions: plain http(s) URLs without userinfo/query are accepted', () => {
  for (const ok of ['https://gw.example.com/v1', 'http://127.0.0.1:8080/v1', 'https://gw.example.com/openai/v1']) {
    const { models } = browserModelOptions('openai/gpt-6-astra', { OPENAI_BASE_URL: ok });
    assert.equal(models.getModel('openai', 'gpt-6-astra').baseUrl, ok);
  }
});

// ---------------------------------------------------------------- validateRequest
const base = { op: 'run', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 60000 };

test('validateRequest accepts a minimal run request and returns it', () => {
  const ok = { ...base, task: 'do it', max_steps: 5, max_cost_usd: 1 };
  assert.equal(validateRequest(ok), ok);
});

test('validateRequest accepts a run request with a plain JSON schema and with schema omitted', () => {
  validateRequest({ ...base, task: 't', max_steps: 1, max_cost_usd: 1, schema: { type: 'object', properties: { ok: { type: 'boolean' } }, required: ['ok'], additionalProperties: false } });
  validateRequest({ ...base, task: 't', max_steps: 1, max_cost_usd: 1, schema: null });
});

test('validateRequest accepts a login request with an http(s) URL', () => {
  validateRequest({ op: 'login', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 1000, url: 'https://example.com/login' });
});

test('validateRequest rejects bad op', () => {
  assert.throws(() => validateRequest({ ...base, op: 'nope', task: 't', max_steps: 1, max_cost_usd: 1 }), /Expected op run or login/);
});

test('validateRequest requires absolute profile_dir and artifact_dir', () => {
  assert.throws(() => validateRequest({ ...base, profile_dir: 'relative/p', task: 't', max_steps: 1, max_cost_usd: 1 }), /profile_dir must be an absolute path/);
  assert.throws(() => validateRequest({ ...base, artifact_dir: 'relative/a', task: 't', max_steps: 1, max_cost_usd: 1 }), /artifact_dir must be an absolute path/);
  assert.throws(() => validateRequest({ ...base, profile_dir: 5, task: 't', max_steps: 1, max_cost_usd: 1 }), /profile_dir must be an absolute path/);
});

test('validateRequest requires a positive safe integer timeout_ms', () => {
  for (const timeout_ms of [0, -1, 1.5, '60', Number.MAX_SAFE_INTEGER * 2]) {
    assert.throws(() => validateRequest({ ...base, timeout_ms, task: 't', max_steps: 1, max_cost_usd: 1 }), /timeout_ms/);
  }
});

test('validateRequest login: URL must be http(s) and parseable', () => {
  const login = { op: 'login', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 1000 };
  assert.throws(() => validateRequest({ ...login, url: 'ftp://example.com' }), /Login URL must use HTTP or HTTPS/);
  assert.throws(() => validateRequest({ ...login, url: 'not a url' }), /Invalid URL|Login URL/);
  assert.throws(() => validateRequest(login), /Invalid URL/);
});

test('validateRequest run: task, max_steps, max_cost_usd branches', () => {
  const t = (patch) => validateRequest({ task: 't', max_steps: 2, max_cost_usd: 0.5, ...base, ...patch });
  assert.throws(() => t({ task: '   ' }), /task must be nonempty/);
  assert.throws(() => t({ max_steps: 0 }), /max_steps/);
  assert.throws(() => t({ max_steps: 2.5 }), /max_steps/);
  for (const max_cost_usd of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.throws(() => t({ max_cost_usd }), /max_cost_usd/);
  }
});

test('validateRequest rejects non-object schemas but allows plain objects', () => {
  assert.throws(() => validateRequest({ ...base, task: 't', max_steps: 1, max_cost_usd: 1, schema: ['nope'] }), /schema must be a JSON schema object/);
  assert.throws(() => validateRequest({ ...base, task: 't', max_steps: 1, max_cost_usd: 1, schema: 'string' }), /schema must be a JSON schema object/);
});

// ------------------------------------------------- executeRequest (pre-create failures)
// NOTE (pinned behavior, reported as a runner issue): validateRequest() runs
// BEFORE the try block inside executeRequest(), so invalid requests REJECT the
// exported promise instead of resolving to {status:'error'}. Only the CLI
// main() catch normalizes them. Tests below pin the current contract; the CLI
// tests at the end cover the normalized shape.

test('executeRequest rejects invalid requests instead of returning an error result', async () => {
  await assert.rejects(
    executeRequest({ op: 'run', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 60000 }),
    /task must be nonempty/,
  );
  await assert.rejects(
    executeRequest({ op: 'login', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 1000, url: '::bad::' }),
    /Invalid URL/,
  );
  await assert.rejects(
    executeRequest({ op: 'bogus', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 1000 }),
    /Expected op run or login/,
  );
});

test('executeRequest validation rejects before any browser or model work starts', async () => {
  // No browser launch may happen for a semantically invalid request: the throw
  // is synchronous within the first statement (runner.mjs validateRequest call).
  const start = Date.now();
  await assert.rejects(
    executeRequest({ op: 'run', profile_dir: '/tmp/p', artifact_dir: '/tmp/a', timeout_ms: 1, task: ' ', max_steps: 1, max_cost_usd: 1 }),
    /task must be nonempty/,
  );
  assert.ok(Date.now() - start < 5000, 'validation must fail fast');
});

// ---------------------------------------------------------------- CLI contract
test('CLI: invalid JSON on stdin yields one error JSON line on stdout', { timeout: 30000 }, () => {
  const out = execFileSync('node', ['runner.mjs'], { cwd: join(here, '..'), input: 'not json', encoding: 'utf8', timeout: 20000 });
  const parsed = JSON.parse(out.trim().split('\n').at(-1));
  assert.equal(parsed.status, 'error');
  assert.ok(typeof parsed.error === 'string');
});

test('CLI: rejected op is reported as error, not run', { timeout: 30000 }, () => {
  const dir = mkdtemp(join(tmpdir(), 'bu-runner-test-'));
  const request = JSON.stringify({ op: 'nope', profile_dir: join(dir, 'profile'), artifact_dir: dir, timeout_ms: 1000 });
  const out = execFileSync('node', ['runner.mjs'], { cwd: join(here, '..'), input: request, encoding: 'utf8', timeout: 20000 });
  const parsed = JSON.parse(out.trim().split('\n').at(-1));
  assert.equal(parsed.status, 'error');
  assert.match(parsed.error, /Expected op run or login/);
});

test('importing runner.mjs as a module does not start main()', () => {
  // The tests above imported the module at load time; if main() had run, this
  // process would have consumed stdin and already exited before any test ran.
  assert.equal(typeof executeRequest, 'function');
  assert.equal(typeof secretValues, 'function');
  assert.equal(typeof redactText, 'function');
  assert.equal(typeof eventError, 'function');
  assert.equal(typeof validateRequest, 'function');
});
