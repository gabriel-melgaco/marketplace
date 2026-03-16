import '@testing-library/jest-dom';
import { beforeEach } from 'vitest';

// Clear localStorage between tests to prevent token state leaking across files
beforeEach(() => {
  localStorage.clear();
});
