import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const ADMIN_EMAIL = 'admin@demo.com';
const ADMIN_PASSWORD = 'admin123';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.context().clearCookies();
  });

  test('redirect to login when not authenticated', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page).toHaveURL(/\/login/);
  });

  test('login with correct credentials', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.getByLabel(/tenant/i).fill('demo');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /login/i }).click();
    await page.waitForURL(/\/datasets/);
    await expect(page).toHaveURL(/\/datasets/);
  });

  test('show error with wrong password', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    await page.getByLabel(/tenant/i).fill('demo');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill('wrongpass');
    await page.getByRole('button', { name: /login/i }).click();
    await expect(page.getByText(/invalid|error/i)).toBeVisible();
  });
});
