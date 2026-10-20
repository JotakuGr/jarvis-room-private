const paths = {
  monitor: 'M3 4h18v12H3z M8 21h8 M12 16v5',
  light: 'M9 18h6 M9 21h6 M8.5 14.5a6 6 0 1 1 7 0L15 18H9z',
  audio: 'M4 9h4l5-4v14l-5-4H4z M17 8a6 6 0 0 1 0 8 M19 5a10 10 0 0 1 0 14',
  climate: 'M3 8h14a3 3 0 1 0-3-3 M3 12h17 M3 16h11a3 3 0 1 1-3 3',
  sensor: 'M12 12h.01 M8 8a6 6 0 0 0 0 8 M16 8a6 6 0 0 1 0 8 M5 5a10 10 0 0 0 0 14 M19 5a10 10 0 0 1 0 14',
  brain: 'M12 4v16 M12 6C7 0 3 6 6 9c-5 3-2 9 2 9 1 4 4 3 4 1 M12 6c5-6 9 0 6 3 5 3 2 9-2 9-1 4-4 3-4 1',
  settings: 'M4 7h16 M4 17h16 M8 4v6 M16 14v6',
  expand: 'M8 3H3v5 M16 3h5v5 M3 16v5h5 M21 16v5h-5',
  arrow: 'M5 12h14 M13 6l6 6-6 6',
  close: 'M6 6l12 12 M18 6L6 18',
  lock: 'M6 10h12v11H6z M8 10V7a4 4 0 0 1 8 0v3',
  network: 'M5 16a10 10 0 0 1 14 0 M2 12a15 15 0 0 1 20 0 M8 19a6 6 0 0 1 8 0 M12 22h.01',
  play: 'M8 4l12 8-12 8z',
  clock: 'M12 7v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  spark: 'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
} as const;
export type IconName = keyof typeof paths;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>; }
