const fs = require('fs').promises;
const path = require('path');

/**
 * Cookie management helpers
 */
class CookieManager {
  constructor(cookieFilePath = '.notion-cookies.json') {
    this.cookieFilePath = cookieFilePath;
  }

  /**
   * Save cookies to file
   */
  async saveCookies(cookies) {
    try {
      await fs.writeFile(
        this.cookieFilePath,
        JSON.stringify(cookies, null, 2),
        'utf8'
      );
      console.log(`✅ Cookies saved to ${this.cookieFilePath}`);
    } catch (error) {
      console.error(`❌ Error saving cookies: ${error.message}`);
    }
  }

  /**
   * Load cookies from file
   */
  async loadCookies() {
    try {
      const data = await fs.readFile(this.cookieFilePath, 'utf8');
      const cookies = JSON.parse(data);
      console.log(`✅ Cookies loaded from ${this.cookieFilePath}`);
      return cookies;
    } catch (error) {
      if (error.code === 'ENOENT') {
        console.log(`ℹ️  No existing cookies file found`);
      } else {
        console.error(`❌ Error loading cookies: ${error.message}`);
      }
      return null;
    }
  }

  /**
   * Check if cookies are expired (older than 7 days)
   */
  isCookiesExpired(cookies) {
    if (!cookies || cookies.length === 0) return true;

    const now = Date.now();
    const sevenDays = 7 * 24 * 60 * 60 * 1000;

    // Check if any cookie has expired or is older than 7 days
    return cookies.some(cookie => {
      if (cookie.expires) {
        const expires = typeof cookie.expires === 'number'
          ? cookie.expires * 1000
          : new Date(cookie.expires).getTime();
        return expires < now || (now - expires) > sevenDays;
      }
      return false;
    });
  }
}

/**
 * Selector utilities for Notion UI
 */
class SelectorUtils {
  /**
   * Try multiple selectors until one is found
   */
  static async waitForAnySelector(page, selectors, timeout = 5000) {
    for (const selector of selectors) {
      try {
        await page.waitForSelector(selector, { timeout });
        return selector;
      } catch (error) {
        // Try next selector
        continue;
      }
    }
    throw new Error(`None of the selectors found: ${selectors.join(', ')}`);
  }

  /**
   * Get Notion share button selectors
   */
  static getShareButtonSelectors() {
    return [
      '[aria-label="Share"]',
      'button[aria-label*="Share"]',
      '.notion-topbar-share-menu',
      'button:has-text("Share")',
      '[data-testid="share-button"]'
    ];
  }

  /**
   * Get publish toggle selectors
   */
  static getPublishToggleSelectors() {
    return [
      'input[type="checkbox"]',
      'button:has-text("Publish")',
      '[aria-label*="Publish"]',
      '.notion-share-menu-publish-toggle'
    ];
  }

  /**
   * Get publish button selectors
   */
  static getPublishButtonSelectors() {
    return [
      'button:has-text("Publish to web")',
      'button:has-text("Publish")',
      'button[type="submit"]',
      '[aria-label*="Publish to web"]'
    ];
  }

  /**
   * Get public URL input selectors
   */
  static getPublicUrlSelectors() {
    return [
      'input[readonly]',
      'input[value*="notion.so"]',
      '.notion-share-menu-public-url input',
      '[data-testid="public-url-input"]'
    ];
  }
}

/**
 * URL validation
 */
function validateNotionUrl(url) {
  if (!url || typeof url !== 'string') {
    return false;
  }

  const notionUrlPattern = /^https:\/\/(www\.)?notion\.so\/.+$/;
  return notionUrlPattern.test(url);
}

/**
 * Logging utilities
 */
function log(level, message, data = null) {
  const timestamp = new Date().toISOString();
  const logLevel = process.env.LOG_LEVEL || 'info';
  const levels = { error: 0, warn: 1, info: 2, debug: 3 };

  if (levels[level] <= levels[logLevel]) {
    const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
    console.log(logMessage);
    if (data) {
      console.log(JSON.stringify(data, null, 2));
    }
  }
}

module.exports = {
  CookieManager,
  SelectorUtils,
  validateNotionUrl,
  log
};
