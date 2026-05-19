import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const ADMIN_EMAIL = 'admin@demo.com';
const ADMIN_PASSWORD = 'admin123';

test.describe('Record Approval', () => {
  test('create and approve record', async ({ page }) => {
    // Login as admin
    await page.goto(`${BASE_URL}/login`);
    await page.getByLabel(/tenant/i).fill('demo');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /login/i }).click();
    await page.waitForURL(/\/datasets/);

    // Enter first dataset
    await page.getByRole('link').first().click();
    await page.waitForURL(/\/datasets\/[^/]+$/);

    // Click new record button
    await page.getByRole('button', { name: /new|add/i }).click();
    await page.waitForURL(/\/new/);

    // Fill form fields
    const inputs = page.locator('input, textarea');
    const count = await inputs.count();
    for (let i = 0; i < count; i++) {
      await inputs.nth(i).fill(`Test ${i}`);
    }

    // Submit
    await page.getByRole('button', { name: /submit|save/i }).click();
    await page.waitForURL(/\/approvals\//);

    // Verify pending status on approval detail page
    await expect(page.getByText(/pending/i)).toBeVisible();

    // Approve
    await page.getByRole('button', { name: /approve/i }).first().click();
    await expect(page.getByText(/applied|approved/i)).toBeVisible();

    // Verify in dataset list
    await page.goto(`${BASE_URL}/datasets`);
    await page.getByRole('link').first().click();
    await expect(page.getByText(/Test 0/i)).toBeVisible();
  });
});
