import '@testing-library/jest-dom';
import { beforeEach, vi } from 'vitest';

// Clear localStorage between tests to prevent token state leaking across files
beforeEach(() => {
  localStorage.clear();
});

vi.stubEnv('VITE_STRIPE_PUBLIC_KEY', 'pk_test_stub');
