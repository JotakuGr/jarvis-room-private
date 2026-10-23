import { renderToString } from 'react-dom/server';
import { expect, it } from 'vitest';
import { PresentationProvider, usePresentation } from './state';

it('starts both monitors with a safe LIVE snapshot before any subscription', () => {
  function Probe() {
    const { mode, snapshot, demo } = usePresentation();
    return <span>{`${mode}:${snapshot.connection.state}:${snapshot.voiceState}:${snapshot.amplitude}:${demo === null}`}</span>;
  }
  expect(renderToString(<PresentationProvider><Probe /></PresentationProvider>)).toContain('backend:disconnected:IDLE:0:true');
});
