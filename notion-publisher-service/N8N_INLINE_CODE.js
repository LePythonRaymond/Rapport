// Complete inline code for n8n Code node
// This version works in n8n's VM2 sandbox environment
// Simplified workflow: Extracts public URL from already-published Notion pages
// by navigating to the internal page, clicking "View site" button, and extracting the public URL

// Get data from previous node
const pageUrl = $input.first().json.body.data.url;
const pageId = $input.first().json.body.data.id || null;

// Get credentials from n8n environment variables
// Use $vars if available, otherwise try process.env
const email = $vars?.NOTION_EMAIL || (typeof process !== 'undefined' && process.env?.NOTION_EMAIL) || 'taddeo.carpinelli@merciraymond.fr';
const password = $vars?.NOTION_PASSWORD || (typeof process !== 'undefined' && process.env?.NOTION_PASSWORD) || 'Raymond2025-';

if (!email || !password) {
  throw new Error('Notion credentials not found. Set NOTION_EMAIL and NOTION_PASSWORD.');
}

// Import puppeteer (must be installed in n8n's node_modules)
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs').promises;

// Use stealth plugin
puppeteer.use(StealthPlugin());

// Helper: Wait function (replaces page.waitForTimeout)
function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Helper: Log function
function log(level, message, data = null) {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
  console.log(logMessage);
  if (data) {
    console.log(JSON.stringify(data, null, 2));
  }
}

// Helper: Validate Notion URL
function validateNotionUrl(url) {
  if (!url || typeof url !== 'string') {
    return false;
  }
  const notionUrlPattern = /^https:\/\/(www\.)?notion\.so\/.+$/;
  return notionUrlPattern.test(url);
}

// Helper: Cookie Manager
class CookieManager {
  constructor(cookieFilePath = '/tmp/.notion-cookies.json') {
    this.cookieFilePath = cookieFilePath;
  }

  async saveCookies(cookies) {
    try {
      await fs.writeFile(this.cookieFilePath, JSON.stringify(cookies, null, 2), 'utf8');
      log('info', `Cookies saved to ${this.cookieFilePath}`);
    } catch (error) {
      log('error', `Error saving cookies: ${error.message}`);
    }
  }

  async loadCookies() {
    try {
      const data = await fs.readFile(this.cookieFilePath, 'utf8');
      const cookies = JSON.parse(data);
      log('info', `Cookies loaded from ${this.cookieFilePath}`);
      return cookies;
    } catch (error) {
      if (error.code === 'ENOENT') {
        log('info', 'No existing cookies file found');
      }
      return null;
    }
  }

  isCookiesExpired(cookies) {
    if (!cookies || cookies.length === 0) return true;
    const now = Date.now();
    const sevenDays = 7 * 24 * 60 * 60 * 1000;
    return cookies.some(cookie => {
      if (cookie.expires) {
        const expires = typeof cookie.expires === 'number' ? cookie.expires * 1000 : new Date(cookie.expires).getTime();
        return expires < now || (now - expires) > sevenDays;
      }
      return false;
    });
  }
}

// Helper: Selector Utils
class SelectorUtils {
  static async waitForAnySelector(page, selectors, timeout = 5000) {
    for (const selector of selectors) {
      try {
        await page.waitForSelector(selector, { timeout });
        return selector;
      } catch (error) {
        continue;
      }
    }
    throw new Error(`None of the selectors found: ${selectors.join(', ')}`);
  }

  static getViewSiteButtonSelectors() {
    return [
      'button[aria-label*="View site"]',
      'button[aria-label*="View"]',
      'a[href*="notion.site"]',
      '[data-testid="view-site-button"]',
      '.notion-topbar-view-site',
      'button:has-text("View site")' // Note: Will use page.evaluate() for text-based search
    ];
  }
}

// Helper: Notion Auth
class NotionAuth {
  constructor(email, password, cookieFilePath) {
    this.email = email;
    this.password = password;
    this.cookieManager = new CookieManager(cookieFilePath);
  }

  async isAuthenticated(page) {
    try {
      const cookies = await this.cookieManager.loadCookies();
      if (!cookies || cookies.length === 0 || this.cookieManager.isCookiesExpired(cookies)) {
        return false;
      }
      await page.setCookie(...cookies);
      await page.goto('https://www.notion.so', { waitUntil: 'networkidle2', timeout: 10000 });
      const isLoggedIn = await page.evaluate(() => {
        return !document.querySelector('input[type="email"]') && !document.querySelector('input[type="password"]');
      });
      return isLoggedIn;
    } catch (error) {
      return false;
    }
  }

  async login(page) {
    try {
      log('info', 'Starting Notion login process...');
      await page.goto('https://www.notion.so/login', { waitUntil: 'networkidle2', timeout: 30000 });
      await page.waitForSelector('input[type="email"]', { timeout: 10000 });
      await page.type('input[type="email"]', this.email, { delay: 100 });

      // Find and click continue button
      await wait(1000);
      const continueClicked = await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const continueBtn = buttons.find(btn =>
          btn.textContent.includes('Continue') || btn.type === 'submit'
        );
        if (continueBtn) {
          continueBtn.click();
          return true;
        }
        return false;
      });

      if (!continueClicked) {
        await page.keyboard.press('Enter');
      }
      await wait(2000);

      await page.waitForSelector('input[type="password"]', { timeout: 15000 });
      await page.type('input[type="password"]', this.password, { delay: 100 });

      // Find and click login button
      await wait(1000);
      const loginClicked = await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button'));
        const loginBtn = buttons.find(btn =>
          btn.textContent.includes('Continue') ||
          btn.textContent.includes('Log in') ||
          btn.type === 'submit'
        );
        if (loginBtn) {
          loginBtn.click();
          return true;
        }
        return false;
      });

      if (!loginClicked) {
        await page.keyboard.press('Enter');
      }

      await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 60000 });
      await wait(3000);
      const currentUrl = page.url();
      if (currentUrl.includes('notion.so/login') || currentUrl.includes('login')) {
        throw new Error('Login failed - still on login page');
      }
      const cookies = await page.cookies();
      await this.cookieManager.saveCookies(cookies);
      log('info', 'Login successful, cookies saved');
      return true;
    } catch (error) {
      log('error', 'Login failed', { error: error.message });
      throw error;
    }
  }

  async ensureAuthenticated(page) {
    const isAuth = await this.isAuthenticated(page);
    if (!isAuth) {
      await this.login(page);
    }
    return true;
  }
}

// Main function to extract public URL from already-published Notion page
async function publishNotionPage(pageUrl, pageId, email, password, options = {}) {
  const {
    timeout = 30000,
    maxRetries = 3,
    retryDelay = 5000,
    cookieFilePath = '/tmp/.notion-cookies.json'
  } = options;

  if (!validateNotionUrl(pageUrl)) {
    throw new Error(`Invalid Notion URL: ${pageUrl}`);
  }

  let browser = null;
  let attempt = 0;
  let lastError = null;

  try {
    while (attempt < maxRetries) {
      attempt++;
      log('info', `Extracting public URL attempt ${attempt}/${maxRetries} for ${pageUrl}`);

      try {
        browser = await puppeteer.launch({
          headless: true,
          args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu'
          ],
          defaultViewport: {
            width: 1280,
            height: 720
          }
        });

        let page = await browser.newPage();
        page.setDefaultTimeout(timeout);
        page.setDefaultNavigationTimeout(timeout);

        const auth = new NotionAuth(email, password, cookieFilePath);
        await auth.ensureAuthenticated(page);

        log('info', `Navigating to internal page: ${pageUrl}`);
        await page.goto(pageUrl, { waitUntil: 'networkidle2', timeout: timeout });
        await wait(3000); // Increased wait time for page to fully load

        // Scroll to top to ensure navigation bar is visible
        await page.evaluate(() => window.scrollTo(0, 0));
        await wait(1000);

        log('info', 'Looking for "Share" button to open menu...');
        // First, try to click "Share" button to open the menu where "View site" might be
        let shareMenuOpened = false;
        try {
          const shareClicked = await page.evaluate(() => {
            const buttons = Array.from(document.querySelectorAll('button, a, [role="button"], div'));
            const shareBtn = buttons.find(btn => {
              const text = (btn.textContent || btn.innerText || '').toLowerCase().trim();
              const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
              return (text === 'share' || ariaLabel === 'share') && btn.offsetParent !== null;
            });
            if (shareBtn) {
              shareBtn.click();
              return true;
            }
            return false;
          });

          if (shareClicked) {
            log('info', 'Share button clicked, waiting for menu to open...');
        await wait(2000);
            shareMenuOpened = true;
          }
        } catch (e) {
          log('warn', `Could not click Share button: ${e.message}`);
        }

        log('info', 'Looking for "View site" button...');
        const viewSiteSelectors = SelectorUtils.getViewSiteButtonSelectors();
        let viewSiteClicked = false;
        let navigatedViaHref = false;
        let debugInfo = {
          buttonsFound: [],
          currentUrl: null,
          pageTitle: null,
          screenshotBase64: null,
          buttonSearchAttempts: []
        };

        // Try CSS selectors first
        for (const selector of viewSiteSelectors) {
          // Skip the :has-text() selector as it's not valid CSS
          if (selector.includes(':has-text(')) {
            continue;
          }
          try {
            await page.waitForSelector(selector, { timeout: 5000 });
            await page.click(selector);
            viewSiteClicked = true;
            log('info', `"View site" button clicked using selector: ${selector}`);
                break;
          } catch (error) {
            continue;
          }
        }

        // If CSS selectors didn't work, try finding by text content (English and French)
        if (!viewSiteClicked) {
          log('info', 'Trying to find "View site" button by text content (English/French)...');

          // First, get all buttons/links for debugging
          const allButtons = await page.evaluate(() => {
            const elements = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            return elements.map(el => ({
              tag: el.tagName,
              text: (el.textContent || el.innerText || '').trim(),
              ariaLabel: el.getAttribute('aria-label') || '',
              href: el.getAttribute('href') || '',
              visible: el.offsetParent !== null
            })).filter(el => el.text || el.ariaLabel);
          });

          debugInfo.buttonsFound = allButtons;
          debugInfo.currentUrl = page.url();
          debugInfo.pageTitle = await page.title();

          log('info', `Found ${allButtons.length} buttons/links on page. Top 10:`, allButtons.slice(0, 10));

          // Try to find the button and get its selector
          const buttonInfo = await page.evaluate(() => {
            const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
            const viewSiteBtn = buttons.find(btn => {
              const text = (btn.textContent || btn.innerText || '').toLowerCase().trim();
              const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
              const isVisible = btn.offsetParent !== null;

              // Check for English and French text
              const matches =
                text.includes('view site') ||
                text.includes('view') ||
                text.includes('voir le site') ||
                text.includes('voir') ||
                ariaLabel.includes('view site') ||
                ariaLabel.includes('view') ||
                ariaLabel.includes('voir le site') ||
                ariaLabel.includes('voir');

              return matches && isVisible;
            });

            if (viewSiteBtn) {
              // Scroll into view
              viewSiteBtn.scrollIntoView({ behavior: 'smooth', block: 'center' });
              return {
                found: true,
                tag: viewSiteBtn.tagName,
                text: (viewSiteBtn.textContent || viewSiteBtn.innerText || '').trim(),
                ariaLabel: viewSiteBtn.getAttribute('aria-label') || '',
                href: viewSiteBtn.getAttribute('href') || ''
              };
            }
            return { found: false };
          });

          if (buttonInfo.found) {
            log('info', `Found "View site" button: ${buttonInfo.text || buttonInfo.ariaLabel || buttonInfo.href}`);
            await wait(500); // Wait for scroll to complete

            // Try clicking by href if it's a link
            if (buttonInfo.href) {
              try {
                await page.goto(buttonInfo.href, { waitUntil: 'networkidle2', timeout: 30000 });
                viewSiteClicked = true;
                navigatedViaHref = true;
                log('info', 'Navigated to public URL via link href');
          } catch (error) {
                log('warn', `Could not navigate via href, trying click: ${error.message}`);
              }
            }

            // If href navigation didn't work, try clicking the button
            if (!viewSiteClicked) {
              // Capture pages BEFORE clicking to detect new tab
              const pagesBeforeClick = await browser.pages();
              log('info', `Pages before click: ${pagesBeforeClick.length}`);
              debugInfo.pagesBeforeClick = pagesBeforeClick.length;

              viewSiteClicked = await page.evaluate(() => {
                const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                const viewSiteBtn = buttons.find(btn => {
                  const text = (btn.textContent || btn.innerText || '').toLowerCase().trim();
                  const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                  const isVisible = btn.offsetParent !== null;

                  const matches =
                    text.includes('view site') ||
                    text.includes('view') ||
                    text.includes('voir le site') ||
                    text.includes('voir') ||
                    ariaLabel.includes('view site') ||
                    ariaLabel.includes('view') ||
                    ariaLabel.includes('voir le site') ||
                    ariaLabel.includes('voir');

                  return matches && isVisible;
                });

                if (viewSiteBtn) {
                  viewSiteBtn.click();
                return true;
              }
              return false;
            });

              if (viewSiteClicked) {
                log('info', '"View site" button clicked using text content search');
                await wait(1000); // Wait for click to register
              }
            }
          }
        }

        if (!viewSiteClicked) {
          // Collect debug information before throwing error
          debugInfo.currentUrl = page.url();
          debugInfo.pageTitle = await page.title();

          // Take screenshot as base64 for inclusion in error response
          try {
            const screenshotBuffer = await page.screenshot({
              fullPage: true,
              encoding: 'base64'
            });
            debugInfo.screenshotBase64 = screenshotBuffer;
            log('error', 'Screenshot captured for debugging');
          } catch (screenshotError) {
            log('warn', `Could not take screenshot: ${screenshotError.message}`);
          }

          // Create detailed error with debug info
          const errorMessage = `Could not find or click "View site" button. Found ${debugInfo.buttonsFound.length} buttons. Current URL: ${debugInfo.currentUrl}`;
          const debugError = new Error(errorMessage);
          debugError.debugInfo = debugInfo;
          throw debugError;
        }

        // Wait for navigation to public URL (only if we clicked, not if we navigated via href)
        if (!navigatedViaHref) {
          log('info', 'Waiting for "View site" to open new tab...');

          // Get pages count before click (from debugInfo if available, otherwise get current)
          const pagesBeforeCount = debugInfo.pagesBeforeClick || (await browser.pages()).length;
          log('info', `Pages before click: ${pagesBeforeCount}`);

          // Wait for new tab to open (View site opens in new tab)
          let newPage = null;
          let attempts = 0;
          const maxAttempts = 15; // Increased attempts

          while (attempts < maxAttempts && !newPage) {
            await wait(500);
            const pagesAfter = await browser.pages();
            log('info', `Checking for new tab... Attempt ${attempts + 1}/${maxAttempts}, current pages: ${pagesAfter.length}`);

            if (pagesAfter.length > pagesBeforeCount) {
              // New tab opened! Find it (usually the last one)
              newPage = pagesAfter[pagesAfter.length - 1];
              log('info', `New tab detected! Total tabs: ${pagesAfter.length}`);
                break;
            }
            attempts++;
          }

          if (newPage) {
            log('info', 'Switching to new tab with public URL...');
            await newPage.bringToFront();
            await wait(3000); // Wait for page to fully load

            // Wait for the page to be ready
            try {
              await newPage.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 }).catch(() => {});
            } catch (e) {
              // Ignore navigation errors, just wait a bit more
              await wait(2000);
            }

            // Close the old page and use the new one
            await page.close();
            page = newPage;
            log('info', 'Switched to new tab');
          } else {
            log('warn', 'No new tab detected, trying to wait for navigation on current page...');
            try {
              await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 10000 });
            } catch (navError) {
              log('warn', `Navigation wait timeout: ${navError.message}`);
            }
          }
        } else {
          log('info', 'Already navigated via href, skipping navigation wait');
        }

        await wait(2000);

        // Extract URL from address bar
        const publicUrl = page.url();
        log('info', 'Public URL extracted from address bar', { publicUrl });

        // Validate URL format
        if (!publicUrl.includes('concrete-edam-02c.notion.site')) {
          // Collect debug information for URL validation error
          debugInfo.currentUrl = publicUrl;
          debugInfo.pageTitle = await page.title();

          // Take screenshot for debugging
          try {
            const screenshotBuffer = await page.screenshot({
              fullPage: true,
              encoding: 'base64'
            });
            debugInfo.screenshotBase64 = screenshotBuffer;
          } catch (screenshotError) {
            log('warn', `Could not take screenshot: ${screenshotError.message}`);
          }

          // Get all buttons again to see what's on the page
          try {
            const allButtons = await page.evaluate(() => {
              const elements = Array.from(document.querySelectorAll('button, a, [role="button"]'));
              return elements.map(el => ({
                tag: el.tagName,
                text: (el.textContent || el.innerText || '').trim(),
                ariaLabel: el.getAttribute('aria-label') || '',
                href: el.getAttribute('href') || '',
                visible: el.offsetParent !== null
              })).filter(el => el.text || el.ariaLabel);
            });
            debugInfo.buttonsFound = allButtons;
          } catch (e) {
            log('warn', `Could not get buttons: ${e.message}`);
          }

          const errorMessage = `Unexpected public URL format. Expected 'concrete-edam-02c.notion.site', got: ${publicUrl}`;
          const debugError = new Error(errorMessage);
          debugError.debugInfo = debugInfo;
          throw debugError;
        }

        await page.close();
        await browser.close();
        browser = null;

        return {
          success: true,
          publicUrl: publicUrl,
          pageId: pageId,
          message: 'Public URL extracted successfully'
        };

      } catch (error) {
        log('warn', `Attempt ${attempt} failed`, { error: error.message });
        lastError = error;
        // Preserve debug info from the error
        if (error.debugInfo) {
          lastError.debugInfo = error.debugInfo;
        }
        if (browser) {
          try {
            await browser.close();
          } catch (e) {}
          browser = null;
        }
        if (attempt < maxRetries) {
          log('info', `Retrying in ${retryDelay}ms...`);
          await wait(retryDelay);
        }
      }
    }

    const finalError = new Error(`Failed to extract public URL after ${maxRetries} attempts: ${lastError?.message}`);
    if (lastError?.debugInfo) {
      finalError.debugInfo = lastError.debugInfo;
    }
    throw finalError;

  } catch (error) {
    if (browser) {
      try {
        await browser.close();
      } catch (e) {}
    }
    throw error;
  }
}

// Execute the function to extract public URL
try {
  const result = await publishNotionPage(pageUrl, pageId, email, password, {
    timeout: 30000,
    maxRetries: 3
  });

  return [{
    json: {
      ...$input.item.json,
      ...result
    }
  }];
} catch (error) {
  const errorResponse = {
      ...$input.item.json,
      success: false,
      error: error.message
  };

  // Include debug information if available
  if (error.debugInfo) {
    errorResponse.debugInfo = {
      currentUrl: error.debugInfo.currentUrl,
      pageTitle: error.debugInfo.pageTitle,
      buttonsFound: error.debugInfo.buttonsFound?.slice(0, 20) || [], // Limit to first 20 buttons
      buttonsCount: error.debugInfo.buttonsFound?.length || 0,
      screenshotBase64: error.debugInfo.screenshotBase64 || null
    };

    // Log summary for console
    log('error', `Debug Info: URL=${error.debugInfo.currentUrl}, Title=${error.debugInfo.pageTitle}, Buttons=${error.debugInfo.buttonsFound?.length || 0}`);
  }

  return [{
    json: errorResponse
  }];
}
