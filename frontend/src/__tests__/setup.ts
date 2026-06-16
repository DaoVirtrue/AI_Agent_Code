// Setup file for Vitest tests
// This runs before each test file to configure the test environment

import { beforeEach, afterEach, vi } from 'vitest';

// Ensure localStorage is available and resets between tests
// jsdom provides a basic localStorage, but we wrap it to be safe
function createLocalStorageMock(): Storage {
  let store: Record<string, string> = {};

  return {
    getItem(key: string): string | null {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    setItem(key: string, value: string): void {
      store[key] = String(value);
    },
    removeItem(key: string): void {
      delete store[key];
    },
    clear(): void {
      store = {};
    },
    get length(): number {
      return Object.keys(store).length;
    },
    key(index: number): string | null {
      const keys = Object.keys(store);
      return index < keys.length ? keys[index] : null;
    },
  };
}

// Polyfill localStorage if not available (jsdom normally provides this)
if (typeof globalThis.localStorage === 'undefined') {
  Object.defineProperty(globalThis, 'localStorage', {
    value: createLocalStorageMock(),
    writable: true,
    configurable: true,
  });
}

// Reset localStorage before each test
beforeEach(() => {
  localStorage.clear();
});

// Restore all mocks after each test
afterEach(() => {
  vi.restoreAllMocks();
});

// Ensure atob and btoa are available (jsdom provides these)
if (typeof globalThis.atob === 'undefined') {
  globalThis.atob = (data: string) => Buffer.from(data, 'base64').toString('binary');
}
if (typeof globalThis.btoa === 'undefined') {
  globalThis.btoa = (data: string) => Buffer.from(data, 'binary').toString('base64');
}
