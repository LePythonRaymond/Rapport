const { CookieManager, log } = require('./utils');

/**
 * Notion authentication handler
 */
class NotionAuth {
  constructor(email, password, cookieFilePath) {
    this.email = email;
    this.password = password;
    this.cookieManager = new CookieManager(cookieFilePath);
  }

  /**
   * Check if user is already authenticated via cookies
   */
  async isAuthenticated(page) {
    try {
      const cookies = await this.cookieManager.loadCookies();

      if (!cookies || cookies.length === 0) {
        log('info', 'No cookies found, authentication required');
        return false;
      }

      // Check if cookies are expired
      if (this.cookieManager.isCookiesExpired(cookies)) {
        log('info', 'Cookies expired, re-authentication required');
        return false;
      }

      // Set cookies and check if still valid
      await page.setCookie(...cookies);
      await page.goto('https://www.notion.so', { waitUntil: 'networkidle2', timeout: 10000 });

      // Check if we're logged in by looking for login indicators
      const isLoggedIn = await page.evaluate(() => {
        // Check for logged-in indicators (no login form, has workspace)
        return !document.querySelector('input[type="email"]') &&
               !document.querySelector('input[type="password"]');
      });

      if (isLoggedIn) {
        log('info', '✅ Authentication valid (cookies)');
        return true;
      } else {
        log('info', 'Cookies invalid, re-authentication required');
        return false;
      }
    } catch (error) {
      log('error', 'Error checking authentication', { error: error.message });
      return false;
    }
  }

  /**
   * Login to Notion
   */
  async login(page) {
    try {
      log('info', 'Starting Notion login process...');

      // Navigate to login page
      await page.goto('https://www.notion.so/login', {
        waitUntil: 'networkidle2',
        timeout: 30000
      });

      // Wait for email input
      await page.waitForSelector('input[type="email"]', { timeout: 10000 });
      log('debug', 'Email input found');

      // Enter email
      await page.type('input[type="email"]', this.email, { delay: 100 });
      log('debug', 'Email entered');

      // Click continue/submit button
      const continueButton = await page.$('button[type="submit"]') ||
                            await page.$('button:has-text("Continue")') ||
                            await page.$('button:has-text("Continue with email")');

      if (continueButton) {
        await continueButton.click();
        await page.waitForTimeout(2000);
        log('debug', 'Continue button clicked');
      } else {
        // Try pressing Enter
        await page.keyboard.press('Enter');
        await page.waitForTimeout(2000);
      }

      // Wait for password input (may take a moment)
      await page.waitForSelector('input[type="password"]', { timeout: 15000 });
      log('debug', 'Password input found');

      // Enter password
      await page.type('input[type="password"]', this.password, { delay: 100 });
      log('debug', 'Password entered');

      // Submit login form
      const submitButton = await page.$('button[type="submit"]') ||
                          await page.$('button:has-text("Continue")') ||
                          await page.$('button:has-text("Log in")');

      if (submitButton) {
        await submitButton.click();
      } else {
        await page.keyboard.press('Enter');
      }

      // Wait for navigation to complete (login success)
      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 });
      log('info', '✅ Login navigation completed');

      // Wait a bit more for any redirects
      await page.waitForTimeout(3000);

      // Check if login was successful
      const currentUrl = page.url();
      if (currentUrl.includes('notion.so/login') || currentUrl.includes('login')) {
        throw new Error('Login failed - still on login page');
      }

      // Save cookies for future use
      const cookies = await page.cookies();
      await this.cookieManager.saveCookies(cookies);

      log('info', '✅ Login successful, cookies saved');
      return true;

    } catch (error) {
      log('error', 'Login failed', { error: error.message });

      // Check for 2FA requirement
      const pageContent = await page.content();
      if (pageContent.includes('two-factor') ||
          pageContent.includes('2FA') ||
          pageContent.includes('verification code')) {
        throw new Error('2FA (Two-Factor Authentication) is required. Please disable 2FA or handle manually.');
      }

      throw error;
    }
  }

  /**
   * Ensure authentication (check cookies first, login if needed)
   */
  async ensureAuthenticated(page) {
    const isAuth = await this.isAuthenticated(page);
    if (!isAuth) {
      await this.login(page);
    }
    return true;
  }
}

module.exports = NotionAuth;
