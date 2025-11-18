# n8n Code Node Integration Guide

This guide shows how to use the Puppeteer publisher directly in n8n using a **Code node** instead of running a separate HTTP service.

## Architecture

```
┌─────────────────────────────────────────┐
│  n8n Workflow                           │
│                                         │
│  [Webhook] → [Set Node] → [Code Node]  │
│              (extract)    (Puppeteer)   │
│                         ↓               │
│                   [Publish Result]      │
│                         ↓               │
│              [Update Status] → [Email]  │
└─────────────────────────────────────────┘
```

**Advantages:**
- ✅ No separate server needed
- ✅ Everything in one workflow
- ✅ Simpler deployment
- ✅ No process management required

## Setup

### 1. Install Dependencies in n8n

If your n8n instance has access to install npm packages, install the required dependencies:

```bash
cd /path/to/n8n/.n8n
npm install puppeteer puppeteer-extra puppeteer-extra-plugin-stealth
```

Or if n8n is running in Docker, you'll need to modify the Dockerfile or use a custom image.

**Alternative:** Copy the `notion-publisher-service` folder to your n8n server and reference it from the Code node.

### 2. Configure Environment Variables in n8n

In n8n settings, add these environment variables:
- `NOTION_EMAIL`: Your Notion email
- `NOTION_PASSWORD`: Your Notion password

Or pass them as workflow variables/credentials.

## Code Node Configuration

### Option A: Using the Standalone Function (Recommended)

**Node Type:** Code

**Language:** JavaScript

**Code:**

```javascript
// Import the publish function
// Adjust the path to match your n8n setup
const { publishNotionPage } = require('/path/to/notion-publisher-service/publish-page.js');

// Or if using n8n's built-in module system:
// const path = require('path');
// const { publishNotionPage } = require(path.join(__dirname, '../../notion-publisher-service/publish-page.js'));

// Get data from previous node
const pageUrl = $input.item.json.pageUrl;
const pageId = $input.item.json.pageId || null;

// Get credentials from environment or workflow variables
const email = $vars.NOTION_EMAIL || process.env.NOTION_EMAIL;
const password = $vars.NOTION_PASSWORD || process.env.NOTION_PASSWORD;

// Publish the page
const result = await publishNotionPage(pageUrl, pageId, email, password, {
  timeout: 60000,
  maxRetries: 3,
  retryDelay: 5000
});

// Return result for next node
return [{
  json: {
    ...$input.item.json,
    ...result
  }
}];
```

### Option B: Inline Code (Self-Contained)

If you can't import external modules, copy the entire code inline:

**Node Type:** Code

**Language:** JavaScript

**Code:**

```javascript
// Copy all code from publish-page.js, src/publisher.js, src/auth.js, and src/utils.js
// Then use:

const result = await publishNotionPage(
  $input.item.json.pageUrl,
  $input.item.json.pageId,
  $vars.NOTION_EMAIL,
  $vars.NOTION_PASSWORD
);

return [{ json: { ...$input.item.json, ...result } }];
```

### Option C: Using n8n's File System (If Available)

If n8n has access to the file system:

```javascript
const path = require('path');
const fs = require('fs');

// Read the publish function
const publishCodePath = path.join(__dirname, '../../../notion-publisher-service/publish-page.js');
const publishCode = fs.readFileSync(publishCodePath, 'utf8');

// Execute it in a sandboxed context
eval(publishCode);

// Use it
const result = await publishNotionPage(
  $input.item.json.pageUrl,
  $input.item.json.pageId,
  $vars.NOTION_EMAIL,
  $vars.NOTION_PASSWORD
);

return [{ json: { ...$input.item.json, ...result } }];
```

## Complete Workflow Example

### 1. Webhook Trigger
```
Path: /report-publish
Method: POST
```

### 2. Set Node - Extract Data
```javascript
{
  "pageId": "={{ $json.body.data.id }}",
  "pageUrl": "={{ $json.body.data.url }}",
  "pageName": "={{ $json.body.data.properties.Nom.title[0].text.content }}",
  "clientId": "={{ $json.body.data.properties.Client.relation[0].id }}"
}
```

### 3. Code Node - Publish Page

**Mode:** Run Once for Each Item

**Code:**
```javascript
const { publishNotionPage } = require('/path/to/notion-publisher-service/publish-page.js');

const pageUrl = $input.item.json.pageUrl;
const pageId = $input.item.json.pageId;

try {
  const result = await publishNotionPage(
    pageUrl,
    pageId,
    $vars.NOTION_EMAIL,
    $vars.NOTION_PASSWORD
  );

  return [{
    json: {
      ...$input.item.json,
      ...result
    }
  }];
} catch (error) {
  return [{
    json: {
      ...$input.item.json,
      success: false,
      error: error.message
    }
  }];
}
```

### 4. IF Node - Check Success
```
Condition: {{ $json.success }} === true
```

### 5. Continue with status updates and email...

## Error Handling

The Code node will catch errors automatically. To handle them gracefully:

```javascript
try {
  const result = await publishNotionPage(...);
  return [{ json: { ...$input.item.json, ...result } }];
} catch (error) {
  // Return error result for error branch
  return [{
    json: {
      ...$input.item.json,
      success: false,
      error: error.message,
      errorCode: error.code
    }
  }];
}
```

## Troubleshooting

### "Cannot find module" Error

**Problem:** n8n can't find the publish-page.js file.

**Solutions:**
1. Use absolute path: `/full/path/to/notion-publisher-service/publish-page.js`
2. Copy the code inline into the Code node
3. Install dependencies in n8n's node_modules

### "Puppeteer not found" Error

**Problem:** Puppeteer dependencies not installed in n8n.

**Solution:**
```bash
cd /path/to/n8n
npm install puppeteer puppeteer-extra puppeteer-extra-plugin-stealth
```

Or if using Docker:
```dockerfile
FROM n8nio/n8n
RUN npm install -g puppeteer puppeteer-extra puppeteer-extra-plugin-stealth
```

### "Timeout" Errors

**Problem:** Publishing takes too long.

**Solution:** Increase timeout in the function call:
```javascript
await publishNotionPage(pageUrl, pageId, email, password, {
  timeout: 120000, // 2 minutes
  maxRetries: 3
});
```

### Memory Issues

**Problem:** Puppeteer uses a lot of memory.

**Solution:**
- Close browsers properly (already handled)
- Increase n8n's memory limit
- Use headless mode (already enabled)

## Performance Considerations

- **Browser Launch:** Each publish launches a new browser (~1-2 seconds)
- **Page Load:** Depends on Notion page complexity (~2-5 seconds)
- **Total Time:** ~10-30 seconds per page

For high-volume scenarios, consider:
- Caching authentication cookies
- Reusing browser instances (advanced)
- Using the HTTP service approach for better resource management

## Security Notes

- ⚠️ Never hardcode credentials in Code node
- ✅ Use n8n environment variables or credentials
- ✅ Store credentials securely in n8n's credential manager
- ✅ Use workflow variables for sensitive data

## Migration from HTTP Service

If you were using the HTTP service approach:

1. **Remove:** HTTP Request node to localhost:3000
2. **Add:** Code node with publish function
3. **Update:** Error handling (no HTTP status codes)
4. **Test:** Verify publishing still works

The rest of the workflow remains the same!
