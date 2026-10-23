import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { expect, test } from '@playwright/test';

/** Somente o harness escreve stdin; browser continua com GET SSE de produção. */
class BackendFixture {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending: ((value: Record<string, unknown>) => void)[] = [];
  private lines: Record<string, unknown>[] = [];
  private error = '';
  private next(): Promise<Record<string, unknown>> {
    const line = this.lines.shift();
    return line ? Promise.resolve(line) : new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`Fixture sem resposta: ${this.error}`)), 8000);
      this.pending.push(value => { clearTimeout(timer); resolve(value); });
    });
  }
  async start() {
    this.lines = []; this.pending = []; this.error = '';
    this.child = spawn('python3.11', ['tests/backend_fixture.py'], { env: { ...process.env, JARVIS_PRESENTATION_E2E: '1', PYTHONUNBUFFERED: '1', HF_HUB_OFFLINE: '1', TRANSFORMERS_OFFLINE: '1', CUDA_VISIBLE_DEVICES: '' }, stdio: 'pipe' });
    const reader = createInterface({ input: this.child.stdout });
    reader.on('line', line => { const data = JSON.parse(line); const resolve = this.pending.shift(); if (resolve) resolve(data); else this.lines.push(data); });
    this.child.stderr.on('data', chunk => { this.error += chunk; });
    const ready = await Promise.race([
      this.next(),
      once(this.child, 'exit').then(() => { throw new Error(`Fixture não iniciou (porta de teste 18765 deve estar livre): ${this.error}`); }),
    ]);
    expect(ready.ready).toBe(true);
  }
  async send(type: string, payload: object) {
    this.child!.stdin.write(JSON.stringify({ type, payload }) + '\n');
    const result = await this.next(); expect(result.ok).toBe(true);
    return result.sessionId as string;
  }
  async disconnectProducer() {
    this.child!.stdin.write(JSON.stringify({ disconnect: true }) + '\n');
    expect((await this.next()).ok).toBe(true);
  }
  async reconnectPublisher() {
    this.child!.stdin.write(JSON.stringify({ reconnect: true }) + '\n');
    expect((await this.next()).ok).toBe(true);
  }
  async stop() {
    if (!this.child || this.child.exitCode !== null) return;
    const child = this.child;
    const exited = once(child, 'exit');
    child.kill('SIGTERM');
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    try { await exited; } finally { clearTimeout(timer); this.child = null; }
  }
}

test.describe('Python Unix → SSE → Vite → dois monitores (produtor falso)', () => {
  let backend: BackendFixture;
  test.beforeEach(async ({ context }) => {
    backend = new BackendFixture(); await backend.start();
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      return url.origin === 'http://127.0.0.1:15174' && route.request().method() === 'GET' ? route.continue() : route.abort();
    });
    await context.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
        return String(args[0]).startsWith('webgl') ? null : original.apply(this, args);
      } as typeof original;
    });
  });
  test.afterEach(async () => { await backend?.stop(); });

  test('enters LIVE automatically and carries six real backend states and playback events', async ({ context }) => {
    const one = await context.newPage(); const two = await context.newPage();
    await one.emulateMedia({ reducedMotion: 'no-preference' });
    await one.goto('/monitor/1'); await two.goto('/monitor/2');
    await expect(one.locator('.monitor-one-meta .demo-badge')).toHaveText('LIVE · Conectado');
    await expect(two.locator('.connection-label')).toHaveText('Conectado');
    for (const state of ['IDLE', 'LISTENING', 'TRANSCRIBING', 'THINKING', 'RESPONDING', 'ERROR']) {
      await backend.send('voice_state', { state });
      await expect(one.getByTestId('voice-state')).toHaveText(state);
      await expect(two.locator('.voice-session>strong')).toHaveText(state);
    }
    await backend.send('voice_state', { state: 'RESPONDING' });
    await backend.send('playback_status', { state: 'synthesizing' });
    await expect(one.locator('.monitor-one')).toHaveCSS('--voice-energy', '0');
    await backend.send('playback_status', { state: 'playing' });
    await backend.send('voice_amplitude', { amplitude: .65 });
    await expect(one.locator('.monitor-one')).toHaveCSS('--voice-energy', '0.65');
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 65%');
    await backend.send('playback_status', { state: 'idle' });
    await expect(one.locator('.monitor-one')).toHaveCSS('--voice-energy', '0');
    await one.close();
    await backend.send('voice_state', { state: 'IDLE' });
    await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
    await expect(two.locator('[data-device-id="room_main_lights"] .status-label')).toHaveText('Planejado');
    await expect(two.getByLabel('Mostrar conteúdo compartilhado pelo operador')).not.toBeChecked();
    await backend.send('voice_state', { state: 'RESPONDING' });
    await backend.send('playback_status', { state: 'playing' });
    await backend.send('voice_amplitude', { amplitude: .5 });
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 50%');
    await backend.reconnectPublisher();
    await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 0%');
    await backend.disconnectProducer();
    await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 0%');
    await expect(two.locator('[data-service-id="voice"] .status-label')).toHaveText('Indisponível');
    await expect(two.locator('.connection-label')).toHaveText('Conectado');
  });

  test('invalidates observations and reconnects to a restarted backend without reload', async ({ context }) => {
    const one = await context.newPage(); const two = await context.newPage();
    await one.goto('/monitor/1'); await two.goto('/monitor/2');
    await expect(two.locator('.connection-label')).toHaveText('Conectado');
    const old = await backend.send('service_status', { id: 'llm', status: 'unknown', detail: 'qwen3.5:4b · instalado; sem resposta observada' });
    await expect(two.locator('[data-service-id="llm"]')).toContainText('instalado; sem resposta observada');
    await expect(two.locator('[data-service-id="llm"] .status-label')).toHaveText('Uso não observado');
    await backend.send('service_status', { id: 'llm', status: 'connected', detail: 'qwen3.5:4b · resposta gerada nesta sessão' });
    await expect(two.locator('[data-service-id="llm"]')).toContainText('resposta gerada nesta sessão');
    await expect(two.locator('[data-service-id="llm"] .status-label')).toHaveText('Observado');
    await backend.send('voice_state', { state: 'RESPONDING' });
    await backend.send('playback_status', { state: 'playing' });
    await backend.send('voice_amplitude', { amplitude: .7 });
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 70%');
    await two.getByLabel('Mostrar conteúdo compartilhado pelo operador').check();
    await backend.stop();
    await expect(two.locator('.connection-label')).toHaveText('Desconectado · reconectando');
    await expect(one.getByTestId('voice-state')).toHaveText('IDLE');
    await expect(two.locator('.voice-session small')).toContainText('Amplitude 0%');
    await backend.start();
    await expect(one.locator('.monitor-one-meta .demo-badge')).toHaveText('LIVE · Conectado');
    await expect(two.locator('.connection-label')).toHaveText('Conectado');
    await expect(two.getByLabel('Mostrar conteúdo compartilhado pelo operador')).not.toBeChecked();
    const current = await backend.send('voice_state', { state: 'LISTENING' });
    expect(current).not.toBe(old);
    await expect(one.getByTestId('voice-state')).toHaveText('LISTENING');
    await expect(two.locator('.voice-session>strong')).toHaveText('LISTENING');
    await expect(two.locator('[data-service-id="llm"]')).not.toContainText('resposta gerada');
    await expect(two.locator('.live-observations')).toContainText('Sem leitura autorizada');
  });
});
