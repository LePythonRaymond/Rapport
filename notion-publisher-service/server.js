require('dotenv').config();
const express = require('express');
const cookieParser = require('cookie-parser');
const NotionPublisher = require('./src/publisher');
const { log, validateNotionUrl } = require('./src/utils');

const app = express();
const PORT = process.env.PORT || 3000;
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

// Middleware
app.use(express.json());
app.use(cookieParser());

// Validate required environment variables
const NOTION_EMAIL = process.env.NOTION_EMAIL;
const NOTION_PASSWORD = process.env.NOTION_PASSWORD;
const COOKIE_FILE_PATH = process.env.COOKIE_FILE_PATH || '.notion-cookies.json';

if (!NOTION_EMAIL || !NOTION_PASSWORD) {
  log('error', 'Missing required environment variables: NOTION_EMAIL and NOTION_PASSWORD');
  process.exit(1);
}

// Initialize publisher instance
let publisher;
try {
  publisher = new NotionPublisher(NOTION_EMAIL, NOTION_PASSWORD, COOKIE_FILE_PATH);
  log('info', 'NotionPublisher initialized');
} catch (error) {
  log('error', 'Failed to initialize NotionPublisher', { error: error.message });
  process.exit(1);
}

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'notion-publisher-service',
    timestamp: new Date().toISOString()
  });
});

// Publish endpoint
app.post('/publish', async (req, res) => {
  const startTime = Date.now();

  try {
    const { pageUrl, pageId } = req.body;

    // Validate input
    if (!pageUrl) {
      return res.status(400).json({
        success: false,
        error: 'Missing required parameter: pageUrl'
      });
    }

    if (!validateNotionUrl(pageUrl)) {
      return res.status(400).json({
        success: false,
        error: `Invalid Notion URL: ${pageUrl}`
      });
    }

    log('info', 'Publish request received', { pageUrl, pageId });

    // Publish the page
    const result = await publisher.publishNotionPage(pageUrl, {
      timeout: 60000,
      maxRetries: 3,
      retryDelay: 5000
    });

    const duration = Date.now() - startTime;
    log('info', 'Publish request completed', {
      success: true,
      duration: `${duration}ms`,
      publicUrl: result.publicUrl
    });

    res.json({
      success: true,
      publicUrl: result.publicUrl,
      pageId: pageId,
      message: result.message,
      duration: duration
    });

  } catch (error) {
    const duration = Date.now() - startTime;
    log('error', 'Publish request failed', {
      error: error.message,
      duration: `${duration}ms`
    });

    // Determine error type and status code
    let statusCode = 500;
    if (error.message.includes('Invalid Notion URL')) {
      statusCode = 400;
    } else if (error.message.includes('2FA') || error.message.includes('authentication')) {
      statusCode = 401;
    } else if (error.message.includes('timeout')) {
      statusCode = 504;
    }

    res.status(statusCode).json({
      success: false,
      error: error.message,
      duration: duration
    });
  }
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  log('info', 'SIGTERM received, shutting down gracefully...');
  if (publisher) {
    await publisher.cleanup();
  }
  process.exit(0);
});

process.on('SIGINT', async () => {
  log('info', 'SIGINT received, shutting down gracefully...');
  if (publisher) {
    await publisher.cleanup();
  }
  process.exit(0);
});

// Start server
app.listen(PORT, () => {
  log('info', `🚀 Notion Publisher Service running on port ${PORT}`);
  log('info', `Health check: http://localhost:${PORT}/health`);
  log('info', `Publish endpoint: http://localhost:${PORT}/publish`);
});
