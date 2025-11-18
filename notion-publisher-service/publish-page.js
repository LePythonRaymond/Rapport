/**
 * Standalone Puppeteer function for n8n Code node
 *
 * Usage in n8n Code node:
 * const result = await publishNotionPage(pageUrl, pageId, email, password);
 * return [{ json: result }];
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const NotionAuth = require('./src/auth');
const { SelectorUtils, validateNotionUrl, log } = require('./src/utils');

// Use stealth plugin to avoid detection
puppeteer.use(StealthPlugin());

/**
 * Publish a Notion page to web
 *
 * @param {string} pageUrl - Full URL of the Notion page to publish
 * @param {string} pageId - Optional page ID (for logging)
 * @param {string} email - Notion email address
 * @param {string} password - Notion password
 * @param {Object} options - Optional configuration
 * @returns {Promise<Object>} Result object with success, publicUrl, and message
 */
async function publishNotionPage(pageUrl, pageId = null, email = null, password = null, options = {}) {
  const {
    timeout = 60000,
    maxRetries = 3,
    retryDelay = 5000,
    cookieFilePath = '.notion-cookies.json'
  } = options;

  // Get credentials from environment or parameters
  const notionEmail = email || process.env.NOTION_EMAIL;
  const notionPassword = password || process.env.NOTION_PASSWORD;

  if (!notionEmail || !notionPassword) {
    throw new Error('Notion credentials required. Provide email/password or set NOTION_EMAIL and NOTION_PASSWORD environment variables.');
  }

  // Validate URL
  if (!validateNotionUrl(pageUrl)) {
    throw new Error(`Invalid Notion URL: ${pageUrl}`);
  }

  let browser = null;
  let attempt = 0;
  let lastError = null;

  try {
    while (attempt < maxRetries) {
      attempt++;
      log('info', `Publishing attempt ${attempt}/${maxRetries} for ${pageUrl}`);

      try {
        // Launch browser
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

        const page = await browser.newPage();
        page.setDefaultTimeout(timeout);
        page.setDefaultNavigationTimeout(timeout);

        // Authenticate
        const auth = new NotionAuth(notionEmail, notionPassword, cookieFilePath);
        await auth.ensureAuthenticated(page);

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

        // Wait for share modal and click publish toggle
        log('info', 'Looking for Publish toggle...');
        const publishToggleSelectors = SelectorUtils.getPublishToggleSelectors();

        let toggleClicked = false;
        for (const selector of publishToggleSelectors) {
          try {
            await page.waitForSelector(selector, { timeout: 5000 });
            const element = await page.$(selector);

            if (element) {
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
            continue;
          }
        }

        if (!toggleClicked) {
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

        // If still not found, use page URL as fallback
        if (!publicUrl) {
          publicUrl = page.url();
          log('warn', 'Could not extract public URL, using page URL as fallback');
        }

        if (!publicUrl) {
          throw new Error('Could not extract public URL from page');
        }

        log('info', '✅ Public URL extracted', { publicUrl });

        await page.close();
        await browser.close();
        browser = null;

        return {
          success: true,
          publicUrl: publicUrl,
          pageId: pageId,
          message: 'Page published successfully'
        };

      } catch (error) {
        log('warn', `Attempt ${attempt} failed`, { error: error.message });
        lastError = error;

        if (browser) {
          try {
            await browser.close();
          } catch (e) {
            // Ignore cleanup errors
          }
          browser = null;
        }

        if (attempt < maxRetries) {
          log('info', `Retrying in ${retryDelay}ms...`);
          await new Promise(resolve => setTimeout(resolve, retryDelay));
        }
      }
    }

    throw new Error(`Failed to publish page after ${maxRetries} attempts: ${lastError?.message}`);

  } catch (error) {
    if (browser) {
      try {
        await browser.close();
      } catch (e) {
        // Ignore cleanup errors
      }
    }
    throw error;
  }
}

// Export for use in n8n Code node
module.exports = { publishNotionPage };

// If running directly (for testing)
if (require.main === module) {
  const pageUrl = process.argv[2];
  const email = process.argv[3] || process.env.NOTION_EMAIL;
  const password = process.argv[4] || process.env.NOTION_PASSWORD;

  if (!pageUrl) {
    console.error('Usage: node publish-page.js <pageUrl> [email] [password]');
    process.exit(1);
  }

  publishNotionPage(pageUrl, null, email, password)
    .then(result => {
      console.log(JSON.stringify(result, null, 2));
      process.exit(0);
    })
    .catch(error => {
      console.error('Error:', error.message);
      process.exit(1);
    });
}
