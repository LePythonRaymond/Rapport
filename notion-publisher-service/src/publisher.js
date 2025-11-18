const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const NotionAuth = require('./auth');
const { SelectorUtils, validateNotionUrl, log } = require('./utils');

// Use stealth plugin to avoid detection
puppeteer.use(StealthPlugin());

/**
 * Publish a Notion page to web
 */
class NotionPublisher {
  constructor(email, password, cookieFilePath) {
    this.auth = new NotionAuth(email, password, cookieFilePath);
    this.browser = null;
  }

  /**
   * Launch browser with appropriate configuration
   */
  async launchBrowser() {
    if (this.browser) {
      return this.browser;
    }

    log('info', 'Launching browser...');
    this.browser = await puppeteer.launch({
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

    log('info', '✅ Browser launched');
    return this.browser;
  }

  /**
   * Close browser
   */
  async closeBrowser() {
    if (this.browser) {
      await this.browser.close();
      this.browser = null;
      log('info', 'Browser closed');
    }
  }

  /**
   * Publish a Notion page
   */
  async publishNotionPage(pageUrl, options = {}) {
    const {
      timeout = 60000,
      maxRetries = 3,
      retryDelay = 5000
    } = options;

    // Validate URL
    if (!validateNotionUrl(pageUrl)) {
      throw new Error(`Invalid Notion URL: ${pageUrl}`);
    }

    let attempt = 0;
    let lastError = null;

    while (attempt < maxRetries) {
      attempt++;
      log('info', `Publishing attempt ${attempt}/${maxRetries} for ${pageUrl}`);

      try {
        const result = await this._publishPage(pageUrl, timeout);
        log('info', '✅ Page published successfully', { publicUrl: result.publicUrl });
        return result;
      } catch (error) {
        lastError = error;
        log('warn', `Attempt ${attempt} failed`, { error: error.message });

        if (attempt < maxRetries) {
          log('info', `Retrying in ${retryDelay}ms...`);
          await new Promise(resolve => setTimeout(resolve, retryDelay));
        }
      }
    }

    throw new Error(`Failed to publish page after ${maxRetries} attempts: ${lastError?.message}`);
  }

  /**
   * Internal method to publish a page (single attempt)
   */
  async _publishPage(pageUrl, timeout) {
    const browser = await this.launchBrowser();
    const page = await browser.newPage();

    try {
      // Set longer timeout for page operations
      page.setDefaultTimeout(timeout);
      page.setDefaultNavigationTimeout(timeout);

      // Ensure authentication
      await this.auth.ensureAuthenticated(page);

      // Navigate to the page
      log('info', `Navigating to page: ${pageUrl}`);
      await page.goto(pageUrl, {
        waitUntil: 'networkidle2',
        timeout: timeout
      });

      // Wait for page to fully load
      await page.waitForTimeout(2000);
      log('debug', 'Page loaded');

      // Click Share button
      log('info', 'Looking for Share button...');
      const shareSelectors = SelectorUtils.getShareButtonSelectors();
      const shareSelector = await SelectorUtils.waitForAnySelector(page, shareSelectors, 10000);
      await page.click(shareSelector);
      log('info', '✅ Share button clicked');
      await page.waitForTimeout(1500);

      // Wait for share modal to appear and click publish toggle
      log('info', 'Looking for Publish toggle...');
      const publishToggleSelectors = SelectorUtils.getPublishToggleSelectors();

      // Try to find and click the publish toggle/checkbox
      let toggleClicked = false;
      for (const selector of publishToggleSelectors) {
        try {
          await page.waitForSelector(selector, { timeout: 5000 });
          const element = await page.$(selector);

          if (element) {
            // Check if it's already enabled
            const isChecked = await page.evaluate((el) => {
              return el.checked || el.getAttribute('aria-checked') === 'true';
            }, element);

            if (!isChecked) {
              await element.click();
              toggleClicked = true;
              log('info', '✅ Publish toggle clicked');
              break;
            } else {
              log('info', 'Publish toggle already enabled');
              toggleClicked = true;
              break;
            }
          }
        } catch (error) {
          // Try next selector
          continue;
        }
      }

      if (!toggleClicked) {
        // Try clicking button with "Publish" text
        try {
          await page.click('button:has-text("Publish")', { timeout: 5000 });
          toggleClicked = true;
          log('info', '✅ Publish button clicked (alternative method)');
        } catch (error) {
          throw new Error('Could not find or click publish toggle');
        }
      }

      await page.waitForTimeout(1500);

      // Click final "Publish to web" button if it appears
      log('info', 'Looking for final Publish button...');
      const publishButtonSelectors = SelectorUtils.getPublishButtonSelectors();

      try {
        const publishButton = await SelectorUtils.waitForAnySelector(
          page,
          publishButtonSelectors,
          5000
        );
        await page.click(publishButton);
        log('info', '✅ Final publish button clicked');
        await page.waitForTimeout(2000);
      } catch (error) {
        // Button might not appear if already published or toggle is sufficient
        log('debug', 'Final publish button not found (may already be published)');
      }

      // Extract public URL
      log('info', 'Extracting public URL...');
      const publicUrlSelectors = SelectorUtils.getPublicUrlSelectors();

      let publicUrl = null;
      for (const selector of publicUrlSelectors) {
        try {
          const urlInput = await page.$(selector);
          if (urlInput) {
            publicUrl = await page.evaluate((el) => el.value, urlInput);
            if (publicUrl && publicUrl.includes('notion.so')) {
              break;
            }
          }
        } catch (error) {
          continue;
        }
      }

      // If URL not found in input, try to get it from page
      if (!publicUrl) {
        publicUrl = await page.evaluate(() => {
          // Look for any link containing notion.so
          const links = Array.from(document.querySelectorAll('a[href*="notion.so"]'));
          for (const link of links) {
            const href = link.getAttribute('href');
            if (href && href.includes('notion.so') && !href.includes('/login')) {
              return href;
            }
          }
          return null;
        });
      }

      // If still not found, construct from page URL
      if (!publicUrl) {
        // Try to get from page metadata or construct from current URL
        const currentUrl = page.url();
        // Notion public URLs typically have a different format
        // We'll use the page URL as fallback
        publicUrl = currentUrl;
        log('warn', 'Could not extract public URL, using page URL as fallback');
      }

      if (!publicUrl) {
        throw new Error('Could not extract public URL from page');
      }

      log('info', '✅ Public URL extracted', { publicUrl });

      return {
        success: true,
        publicUrl: publicUrl,
        message: 'Page published successfully'
      };

    } catch (error) {
      log('error', 'Error during publishing', { error: error.message });
      throw error;
    } finally {
      await page.close();
    }
  }

  /**
   * Cleanup resources
   */
  async cleanup() {
    await this.closeBrowser();
  }
}

module.exports = NotionPublisher;
