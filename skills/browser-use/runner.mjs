import { Browser, BrowserUse, CDP, builtinModels } from '@browser_use/pi';
import { readFile, writeFile } from 'node:fs/promises';
import { isAbsolute, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

// One request per process. No browser or model state is retained in the Python kernel.
process.env.DO_NOT_TRACK = '1';
process.env.ANONYMIZED_TELEMETRY = 'false';
process.umask(0o077);

export function secretValues(env = process.env) {
  return Object.entries(env)
    .filter(([name, value]) => /API_KEY|TOKEN|SECRET|PASSWORD/i.test(name) && value.length >= 8)
    .map(([, value]) => value)
    .sort((a, b) => b.length - a.length);
}

export function redactText(text, secrets = secretValues()) {
  for (const secret of secrets) text = text.split(secret).join('[REDACTED]');
  return text;
}

export function eventError(event) {
  if (event.type === 'run_end') return event.result?.error;
  if (event.type !== 'agent_event') return undefined;
  const inner = event.event;
  // message_end and message_update carry message.errorMessage. agent_end carries messages.
  const messages = [inner?.message, ...(inner?.messages ?? [])];
  const errors = messages.map(message => message?.errorMessage).filter(Boolean);
  const deltaError = inner?.assistantMessageEvent?.error?.errorMessage;
  if (deltaError) errors.push(deltaError);
  return errors.at(-1);
}

export function browserModelOptions(model, env = process.env) {
  const baseUrl = env.OPENAI_BASE_URL?.trim();
  if (!model.startsWith('openai/') || !baseUrl) return {model};
  // The bundled SDK does not read OPENAI_BASE_URL. Retain the exact provider/id
  // and its auth resolver; replace only its transport URL using the public API.
  const url = new URL(baseUrl);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('OPENAI_BASE_URL must be an HTTP(S) endpoint without credentials, query, or fragment.');
  }
  const models = builtinModels();
  const provider = models.getProvider('openai');
  if (!provider) throw new Error('The bundled SDK has no OpenAI provider.');
  models.setProvider({
    ...provider,
    baseUrl,
    getModels: () => provider.getModels().map(entry => ({...entry, baseUrl})),
  });
  return {model, models};
}

export function validateRequest(request) {
  if (!request || !['run', 'login'].includes(request.op)) throw new Error('Expected op run or login.');
  for (const field of ['profile_dir', 'artifact_dir']) {
    if (typeof request[field] !== 'string' || !isAbsolute(request[field])) {
      throw new Error(`${field} must be an absolute path.`);
    }
  }
  if (!Number.isSafeInteger(request.timeout_ms) || request.timeout_ms <= 0) {
    throw new Error('timeout_ms must be a positive safe integer.');
  }
  if (request.op === 'login') {
    if (!['http:', 'https:'].includes(new URL(request.url).protocol)) throw new Error('Login URL must use HTTP or HTTPS.');
  } else {
    if (typeof request.task !== 'string' || !request.task.trim()) throw new Error('task must be nonempty.');
    if (!Number.isSafeInteger(request.max_steps) || request.max_steps <= 0) throw new Error('max_steps must be a positive safe integer.');
    if (!Number.isFinite(request.max_cost_usd) || request.max_cost_usd <= 0) throw new Error('max_cost_usd must be finite and positive.');
    if (request.schema != null && (typeof request.schema !== 'object' || Array.isArray(request.schema))) throw new Error('schema must be a JSON schema object.');
  }
  return request;
}

async function screenshot(agent, artifactDir, signal) {
  const file = join(artifactDir, 'screenshot.png');
  await agent.execute(`
    const screenshotResult = await page.cdp('Page.captureScreenshot', {format:'png'});
    await (await import('node:fs/promises')).writeFile(${JSON.stringify(file)}, Buffer.from(screenshotResult.data, 'base64'), {mode:0o600});
    'screenshot saved';
  `, { timeoutMs: 15_000, signal });
  return file;
}

async function login(agent, request, signal) {
  // execute initializes the tab but makes no model request.
  await agent.execute(`await page.goto(${JSON.stringify(request.url)}); 'login page opened';`, {timeoutMs: 30_000, signal});
  const [port, socketPath] = (await readFile(join(request.profile_dir, 'DevToolsActivePort'), 'utf8')).trim().split('\n');
  const connection = await CDP.connect(`ws://127.0.0.1:${port}${socketPath}`, 10_000);
  try {
    // Subscribe before discovery to avoid losing a fast close. Track the whole window,
    // including OAuth tabs, rather than assuming the original target survives sign-in.
    await connection.send('Target.setDiscoverTargets', {discover: true});
    process.stderr.write('Chrome is open. Sign in manually, then close ALL windows for this profile. No model is running.\n');
    const deadline = AbortSignal.timeout(request.timeout_ms);
    const combined = AbortSignal.any([signal, deadline]);
    while (true) {
      combined.throwIfAborted();
      // Register before the snapshot so a close between snapshot and wait is retained.
      const controller = new AbortController();
      const changed = connection.waitFor('Target.targetDestroyed', {
        signal: AbortSignal.any([combined, controller.signal]), timeoutMs: request.timeout_ms,
      });
      // Attach immediately: a browser disconnect can reject while getTargets is pending.
      changed.catch(() => {});
      try {
        const {targetInfos} = await connection.send('Target.getTargets');
        if (!targetInfos.some(target => target.type === 'page')) break;
        await changed;
      } catch (error) {
        if (String(error).includes('CDP connection closed')) break;
        throw error;
      } finally {
        controller.abort();
        await changed.catch(() => {});
      }
    }
    return {
      status: 'completed', output: {profile_dir: request.profile_dir, authenticated: null},
      text: 'Chrome closed. The profile was saved. Authentication has not been verified.',
      steps: 0, cost: 0, screenshot_path: null,
    };
  } finally {
    connection.close();
  }
}

export async function executeRequest(request) {
  validateRequest(request);
  const controller = new AbortController();
  const stop = () => controller.abort(new Error('Browser task cancelled by parent.'));
  process.once('SIGTERM', stop);
  process.once('SIGINT', stop);
  let agent;
  let events;
  let consume;
  let lastError;
  let eventStreamError;
  let result;
  const warnings = [];
  try {
    agent = await BrowserUse.create({
      ...browserModelOptions(request.model ?? process.env.BROWSER_USE_MODEL ?? 'openai/gpt-6-astra'),
      telemetry: false,
      browser: Browser.chromium({profileDir: request.profile_dir, headless: request.op !== 'login'}),
      workspace: request.artifact_dir,
      log: false,
      redact: secretValues(),
      modelTimeoutMs: Math.min(request.timeout_ms, 180_000),
    });
    controller.signal.throwIfAborted();
    if (request.op === 'login') {
      result = await login(agent, request, controller.signal);
    } else {
      events = agent.events();
      consume = (async () => {
        try {
          for await (const event of events) {
            const message = eventError(event);
            if (message) lastError = message;
          }
        } catch (error) {
          eventStreamError = String(error);
        }
      })();
      const run = await agent.run(request.task, {
        ...(request.schema == null ? {} : {schema: request.schema}),
        maxSteps: request.max_steps, timeoutMs: request.timeout_ms,
        maxCostUsd: request.max_cost_usd, signal: controller.signal,
      });
      result = {
        status: run.status, output: run.output ?? null, text: run.text ?? '',
        steps: run.steps, cost: run.usage.cost.total, usage: run.usage,
        duration_ms: run.durationMs, model: run.model,
        screenshot_path: null, history_path: run.historyPath ?? null,
        events_path: run.eventsPath ?? null, partial: run.partial ?? null,
        warnings: run.warnings ?? [],
        ...(run.status === 'completed' ? {} : {error: run.error}),
      };
      if (!controller.signal.aborted) {
        try {
          result.screenshot_path = await screenshot(agent, request.artifact_dir, controller.signal);
        } catch (error) {
          warnings.push(`Screenshot unavailable: ${String(error)}`);
          // A successful task without its required screenshot is not a successful skill call.
          if (result.status === 'completed') {
            result.status = 'artifact_error';
            result.error = warnings.at(-1);
          }
        }
      }
    }
  } catch (error) {
    result = {
      status: controller.signal.aborted ? 'cancelled' : error?.name === 'TimeoutError' ? 'timeout' : 'error',
      error: String(error?.message ?? error), output: null, text: '', steps: 0, cost: 0,
      screenshot_path: null,
    };
  } finally {
    try {
      await agent?.close();
    } catch (error) {
      // SDK 0.1.0 reconnects to owned tabs during close(), even after the user quit
      // headed Chrome. Ignore only this known error, and only after lock cleanup.
      let alreadyClosed = request.op === 'login' && result?.status === 'completed'
        && error?.message === 'Could not connect to CDP endpoint.';
      if (alreadyClosed) {
        try {
          await readFile(join(request.profile_dir, '.bu-pi.lock'));
          alreadyClosed = false;
        } catch (lockError) {
          alreadyClosed = lockError?.code === 'ENOENT';
        }
      }
      warnings.push(alreadyClosed
        ? 'Chrome already exited; profile lock cleanup verified.'
        : `Browser cleanup failed: ${String(error)}`);
      if (!alreadyClosed && result?.status === 'completed') {
        result.status = 'cleanup_error';
        result.error = warnings.at(-1);
      }
    }
    await events?.return();
    await consume;
    process.removeListener('SIGTERM', stop);
    process.removeListener('SIGINT', stop);
  }
  if (eventStreamError) warnings.push(`Event stream: ${eventStreamError}`);
  if (result.status !== 'completed') {
    result.error = lastError || result.error || `Browser task stopped: ${result.status}. ${result.text}`;
  }
  result.warnings = [...(result.warnings ?? []), ...warnings];
  result.artifact_dir = request.artifact_dir;
  result.profile_dir = request.profile_dir;
  return JSON.parse(redactText(JSON.stringify(result)));
}

async function main() {
  let result;
  try {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    result = await executeRequest(request);
    await writeFile(join(request.artifact_dir, 'result.json'), JSON.stringify(result, null, 2) + '\n', {mode: 0o600});
  } catch (error) {
    result = {status:'error', error:redactText(String(error?.message ?? error)), output:null, text:'', steps:0, cost:0, screenshot_path:null};
  }
  process.stdout.write(JSON.stringify(result) + '\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await main();
