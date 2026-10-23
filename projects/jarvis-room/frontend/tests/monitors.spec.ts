import { expect, test } from '@playwright/test';

declare global {
  interface Window {
    __sseFail: boolean;
    __sse: { onmessage: ((event: MessageEvent) => void) | null; onerror: ((event: Event) => void) | null; closed: boolean }[];
  }
}

test.beforeEach(async ({ context }) => {
  context.on('page', page => page.on('pageerror', error => console.error('Frontend page error:', error.message)));
  context.on('response', async response => { if (response.status() >= 400) console.error('Frontend HTTP error:', response.status(), response.url(), (await response.text()).slice(0, 400)); });
  // UI checks deliberately avoid GPU animation, audio and external traffic.
  await context.addInitScript(() => {
    window.__sse = []; window.__sseFail = new URLSearchParams(location.search).has('sse-fail');
    class FakeEventSource {
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      closed = false;
      constructor(url: string) {
        if (url !== '/api/presentation/events') throw new Error('unexpected endpoint');
        window.__sse.push(this);
        setTimeout(() => { if (window.__sseFail && !this.closed) this.onerror?.(new Event('error')); }, 0);
      }
      close() { this.closed = true; }
    }
    window.EventSource = FakeEventSource as unknown as typeof EventSource;
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
      if (String(args[0]).startsWith('webgl')) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:15174' || route.request().method() !== 'GET') return route.abort();
    return route.continue();
  });
});

test('Monitor 1 has the approved room backplate and visible compatibility mode', async ({ page }) => {
  await page.goto('/monitor/1');
  await expect(page.getByRole('heading', { name: 'J.A.R.V.I.S.' })).toBeVisible();
  await expect(page.locator('[data-renderer="fallback"]')).toBeVisible();
  await expect(page.getByTestId('voice-state')).toHaveText('IDLE');
  await expect(page.locator('.demo-badge').first()).toContainText('LIVE');
  await expect(page.locator('.lab-backdrop')).toHaveCSS('background-image', /lab-environment.png/);
});

test('dashboard lists exactly the nine canonical devices and previews scenes', async ({ page }) => {
  await page.goto('/monitor/2');
  await expect(page.locator('[data-device-id]')).toHaveCount(9);
  await expect(page.getByText('Sem medição de temperatura disponível.')).toBeVisible();
  await page.getByRole('button', { name: /Modo apresentação/ }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.locator('.scene-steps li')).toHaveCount(6);
  await expect(page.getByText('Controle físico desabilitado. A prévia não comprova estados reais.')).toBeVisible();
  await page.getByRole('button', { name: 'Fechar prévia', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('two independent windows share only simulated voice presentation', async ({ context }) => {
  const one = await context.newPage(); const two = await context.newPage();
  await one.goto('/monitor/1'); await two.goto('/monitor/2');
  await one.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
  await one.getByLabel('Fonte de dados').selectOption('demo');
  await two.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
  await two.getByLabel('Fonte de dados').selectOption('demo');
  await one.getByRole('button', { name: 'RESPONDING', exact: true }).click();
  await expect(two.locator('.voice-session>strong')).toHaveText('RESPONDING');
  await one.getByRole('button', { name: 'Retornar a IDLE' }).click();
  await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
});

test('LIVE transport failure is visible without fabricated telemetry', async ({ page }) => {
  const forbidden: string[] = [];
  page.on('request', request => { if (new URL(request.url()).origin !== 'http://127.0.0.1:15174') forbidden.push(request.url()); });
  await page.goto('/monitor/2?sse-fail');
  await page.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
  await expect(page.locator('.connection-label')).toHaveText('Desconectado · reconectando');
  await expect(page.locator('.voice-session>strong')).toHaveText('IDLE');
  await expect(page.getByText('LIVE · Desconectado · reconectando.', { exact: false })).toBeVisible();
  expect(forbidden).toEqual([]);
});

test('both LIVE monitors consume the same typed voice events, without device control', async ({ context }) => {
  const one = await context.newPage(); const two = await context.newPage();
  for (const [page, route] of [[one, '/monitor/1'], [two, '/monitor/2']] as const) {
    await page.goto(route);
    await page.evaluate(() => { window.__sseFail = false; });
    await page.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
    await page.getByLabel('Fonte de dados').selectOption('backend');
  }
  const events = [
    ['connection', { state: 'connected' }],
    ['voice_state', { state: 'RESPONDING' }],
    ['playback_status', { state: 'playing' }],
    ['voice_amplitude', { amplitude: .75 }],
  ] as const;
  for (const page of [one, two]) {
    await page.evaluate(events => {
      events.forEach(([type, payload], index) => window.__sse.at(-1)?.onmessage?.(new MessageEvent('message', { data: JSON.stringify({ version: 2, source: 'backend', sessionId: '11111111-1111-4111-8111-111111111111', sequence: index + 1, observedAt: new Date().toISOString(), type, payload }) })));
    }, events);
  }
  await expect(one.getByTestId('voice-state')).toHaveText('RESPONDING');
  await expect(two.locator('.voice-session>strong')).toHaveText('RESPONDING');
  await expect(two.locator('.connection-label')).toHaveText('Conectado');
  await expect(two.locator('.voice-session small')).toContainText('Reprodução real do TTS');
  await expect(two.locator('[data-device-id="room_main_lights"] .status-label')).toHaveText('Planejado');
  await two.evaluate(() => window.__sse.at(-1)?.onerror?.(new Event('error')));
  await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
  await expect(two.locator('.voice-session small')).toContainText('Amplitude 0%');
});

test('informational conversation is hidden until the operator enables display', async ({ page }) => {
  await page.goto('/monitor/2');
  await page.evaluate(() => { window.__sseFail = false; });
  await page.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
  await page.getByLabel('Fonte de dados').selectOption('backend');
  await page.evaluate(() => {
    [['connection', { state: 'connected' }], ['conversation', { question: 'Qual é a função do Home Assistant?', answer: 'Informação experimental.' }]].forEach(([type, payload], index) => window.__sse.at(-1)?.onmessage?.(new MessageEvent('message', { data: JSON.stringify({ version: 2, source: 'backend', sessionId: '11111111-1111-4111-8111-111111111111', sequence: index + 1, observedAt: new Date().toISOString(), type, payload }) })));
  });
  await expect(page.getByText('Informação experimental.', { exact: false })).toHaveCount(0);
  await page.getByLabel('Mostrar conteúdo compartilhado pelo operador').check();
  await expect(page.getByText('Informação experimental.', { exact: false })).toBeVisible();
});
