import { expect, test } from '@playwright/test';

test.beforeEach(async ({ context }) => {
  // UI checks deliberately avoid GPU animation, audio and external traffic.
  await context.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
      if (String(args[0]).startsWith('webgl')) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://127.0.0.1:5174' || route.request().method() !== 'GET') return route.abort();
    return route.continue();
  });
});

test('Monitor 1 has the approved room backplate and visible compatibility mode', async ({ page }) => {
  await page.goto('/monitor/1');
  await expect(page.getByRole('heading', { name: 'J.A.R.V.I.S.' })).toBeVisible();
  await expect(page.locator('[data-renderer="fallback"]')).toBeVisible();
  await expect(page.getByTestId('voice-state')).toHaveText('IDLE');
  await expect(page.locator('.demo-badge').first()).toHaveText('DEMO');
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
  await one.getByRole('button', { name: 'RESPONDING', exact: true }).click();
  await expect(two.locator('.voice-session>strong')).toHaveText('RESPONDING');
  await one.getByRole('button', { name: 'Retornar a IDLE' }).click();
  await expect(two.locator('.voice-session>strong')).toHaveText('IDLE');
});

test('switching to future source opens no connection or fabricated telemetry', async ({ page }) => {
  const forbidden: string[] = [];
  page.on('request', request => { if (new URL(request.url()).origin !== 'http://127.0.0.1:5174') forbidden.push(request.url()); });
  await page.goto('/monitor/2');
  await page.getByRole('button', { name: 'Abrir controles de demonstração' }).click();
  await page.getByLabel('Fonte de dados').selectOption('backend');
  await expect(page.getByText('Nenhum endpoint configurado.', { exact: false })).toBeVisible();
  await expect(page.locator('.connection-label')).toHaveText('Sem fonte ao vivo');
  expect(forbidden).toEqual([]);
});
