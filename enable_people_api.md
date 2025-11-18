# Enable People API in Google Cloud Console

## Current Status

✅ **OAuth scopes configured** - The app now has the People API scope
✅ **Re-authentication completed** - Token has been updated with new permissions

⚠️ **People API needs to be enabled** - One more step required

## How to Enable People API

### Option 1: Direct Link (Easiest)
Click this link to enable the People API for your project:
👉 **https://console.developers.google.com/apis/api/people.googleapis.com/overview?project=216344709373**

Then click the **"Enable"** button.

### Option 2: Manual Steps

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (ID: `216344709373`)
3. Click on **"APIs & Services"** → **"Library"**
4. Search for **"People API"**
5. Click on it and press **"Enable"**

### Option 3: Using gcloud CLI (if installed)

```bash
gcloud services enable people.googleapis.com --project=216344709373
```

## After Enabling

Once enabled, wait 1-2 minutes for the change to propagate, then run:

```bash
python test_people_api.py
```

You should see:
- ✅ People API scope is present
- ✅ User resolution works (or fails gracefully if the test user doesn't exist)
- ✅ All tests pass

## What This Enables

Once the People API is enabled, the app will:
- ✅ Resolve `users/{id}` to real names like "Edward Carey"
- ✅ Display actual gardener names in reports instead of "User 11553432"
- ✅ Still exclude office team members correctly
- ✅ Cache results to minimize API calls

## Troubleshooting

If you get permission errors after enabling:
1. Wait 2-3 minutes for changes to propagate
2. Try running the test again
3. If still failing, the account may need additional Google Workspace admin permissions
