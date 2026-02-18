import type { Page } from "@playwright/test";

const MOCK_USER = {
  id: 1,
  email: "test@example.com",
  full_name: "Test User",
  cpf: "12345678901",
  birthday: "1990-01-01",
  picture: "",
  is_active: true,
};

const MOCK_TOKENS = {
  access: "mock-access-token-for-e2e",
  refresh: "mock-refresh-token-for-e2e",
  access_expiration: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
  refresh_expiration: new Date(
    Date.now() + 7 * 24 * 60 * 60 * 1000,
  ).toISOString(),
};

/**
 * Sets mock auth data in localStorage so the app treats the user as authenticated.
 * Must be called AFTER page.goto() since localStorage is origin-scoped.
 *
 * Usage:
 *   await page.goto("/");
 *   await injectAuth(page);
 *   await page.goto("/create-listing"); // now authenticated
 */
export async function injectAuth(page: Page) {
  await page.evaluate(
    ({ user, tokens }) => {
      localStorage.setItem("@access_token", tokens.access);
      localStorage.setItem("@refresh_token", tokens.refresh);
      localStorage.setItem("@token_data", JSON.stringify(tokens));
      localStorage.setItem("@user_data", JSON.stringify(user));
    },
    { user: MOCK_USER, tokens: MOCK_TOKENS },
  );
}

/**
 * Clears all auth data from localStorage.
 */
export async function clearAuth(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("@access_token");
    localStorage.removeItem("@refresh_token");
    localStorage.removeItem("@token_data");
    localStorage.removeItem("@user_data");
  });
}
