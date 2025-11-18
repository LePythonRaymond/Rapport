/**
 * EXAMPLE: n8n Code Node Configuration
 *
 * Copy this code into your n8n Code node
 *
 * Prerequisites:
 * 1. Install dependencies in n8n: npm install puppeteer puppeteer-extra puppeteer-extra-plugin-stealth
 * 2. Copy publish-page.js and src/ folder to n8n server
 * 3. Set NOTION_EMAIL and NOTION_PASSWORD in n8n environment variables
 */

// ============================================
// OPTION 1: Import from file (if accessible)
// ============================================
const { publishNotionPage } = require('/path/to/notion-publisher-service/publish-page.js');

// Get data from previous node (Set Node)
const pageUrl = $input.item.json.pageUrl;
const pageId = $input.item.json.pageId || null;

// Get credentials from n8n environment variables or workflow variables
const email = $vars.NOTION_EMAIL || process.env.NOTION_EMAIL;
const password = $vars.NOTION_PASSWORD || process.env.NOTION_PASSWORD;

if (!email || !password) {
  throw new Error('Notion credentials not found. Set NOTION_EMAIL and NOTION_PASSWORD in n8n environment variables.');
}

// Publish the page
try {
  const result = await publishNotionPage(pageUrl, pageId, email, password, {
    timeout: 60000,
    maxRetries: 3,
    retryDelay: 5000
  });

  // Return result for next node (IF Node)
  return [{
    json: {
      ...$input.item.json,  // Keep all previous data
      ...result              // Add publish result (success, publicUrl, message)
    }
  }];

} catch (error) {
  // Return error result for error handling branch
  return [{
    json: {
      ...$input.item.json,
      success: false,
      error: error.message,
      publicUrl: null
    }
  }];
}

// ============================================
// OPTION 2: If you can't import from file,
// copy the entire code from publish-page.js,
// src/publisher.js, src/auth.js, and src/utils.js
// directly into this Code node
// ============================================
