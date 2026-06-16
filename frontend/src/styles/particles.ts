import type { ISourceOptions } from '@tsparticles/engine';

export const particlesOptions: ISourceOptions = {
  background: { color: { value: 'transparent' } },
  fpsLimit: 60,
  particles: {
    number: { value: 120, density: { enable: true, area: 800 } },
    color: { value: ['#ffffff', '#aaccff', '#ffddaa', '#ffcccc', '#ccddff'] },
    shape: { type: 'circle' },
    opacity: {
      value: { min: 0.2, max: 0.9 },
      animation: { enable: true, speed: 0.5, sync: false, mode: 'random' },
    },
    size: {
      value: { min: 0.5, max: 2.5 },
      animation: { enable: true, speed: 1, sync: false, mode: 'random' },
    },
    move: {
      enable: true,
      speed: { min: 0.1, max: 0.4 },
      direction: 'none',
      random: true,
      straight: false,
      outModes: { default: 'bounce' },
    },
    links: {
      enable: true,
      color: '#4488cc',
      distance: 120,
      opacity: 0.08,
      width: 0.5,
    },
  },
  interactivity: {
    events: {
      onHover: { enable: true, mode: 'grab' },
      onClick: { enable: true, mode: 'push' },
    },
    modes: {
      grab: { distance: 200, links: { opacity: 0.3, color: '#88bbff' } },
      push: { quantity: 5 },
    },
  },
  detectRetina: true,
};
