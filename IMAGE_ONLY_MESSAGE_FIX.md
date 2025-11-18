# Image-Only Message Fix

## Problem

When gardeners sent images alone (without text) followed by text in a later message, the images were not being captured in the intervention. Only two of three scenarios were working:

❌ **Not Working**: Photo alone → then text later
✅ **Working**: Text with pictures attached
✅ **Working**: Text → then pictures later

## Root Cause

In `src/google_chat/client.py`, the `_process_message()` function had a bug on line 102:

```python
# WRONG: Checking 'attachments' (plural)
if not text.strip() and not message.get('attachments'):
    return None
```

**The Issue**: Google Chat API uses `'attachment'` (singular), not `'attachments'` (plural).

This meant:
1. Messages with images but no text were being evaluated
2. `text.strip()` returned empty string → `False`
3. `message.get('attachments')` returned `None` because the correct field is `'attachment'` → `False`
4. Both conditions False → message was skipped → images lost!

## Solution

Changed line 102 to check the correct field name:

```python
# CORRECT: Checking 'attachment' (singular)
if not text.strip() and not message.get('attachment'):
    return None
```

## Impact

Now all three scenarios work correctly:

✅ **Photo alone → then text later** (FIXED!)
✅ **Text with pictures attached** (still works)
✅ **Text → then pictures later** (still works)

### Examples:

**Scenario 1: Image-only message first**
```
9:00 AM - Edward: [sends 2 photos, no text]
9:30 AM - Edward: "Taille effectuée le 15/01"
```
**Result**: 1 intervention with 2 images + text ✅

**Scenario 2: Text with images**
```
9:00 AM - Edward: "Taille effectuée le 15/01" [with 2 photos]
```
**Result**: 1 intervention with 2 images + text ✅

**Scenario 3: Text first, images later**
```
9:00 AM - Edward: "Taille effectuée le 15/01"
9:30 AM - Edward: [sends 2 photos, no text]
```
**Result**: 1 intervention with 2 images + text ✅

**Scenario 4: Multiple image-only messages**
```
9:00 AM - Edward: [sends photo 1]
9:10 AM - Edward: [sends photo 2]
9:20 AM - Edward: "Voilà les photos"
```
**Result**: 1 intervention with 2 images + text ✅

## Testing

Created comprehensive test suite ([test_image_only_messages.py](test_image_only_messages.py)):

### Test Coverage:
✅ Image extraction from messages
✅ Scenario 1: Image-only → text later
✅ Scenario 2: Text with images
✅ Scenario 3: Text → images later
✅ Scenario 4: Multiple image-only messages

### Test Results:
**All tests passing (100% success rate)**

## Technical Details

### Google Chat API Field Names:
- ✅ `'attachment'` (singular) - Correct field name for raw Google Chat API messages
- ❌ `'attachments'` (plural) - Internal field name used in processed messages

### Message Processing Flow:
```
Raw Google Chat API Message
    ↓
_process_message() [FIXED HERE]
    ↓
Check: text OR 'attachment' field
    ↓
Process if either exists
    ↓
Store as 'attachments' (plural) in processed message
    ↓
Group into interventions
```

## Files Modified

1. **src/google_chat/client.py** (line 102)
   - Changed `message.get('attachments')` to `message.get('attachment')`
   - Added clarifying comment about field name

## Files Created

1. **test_image_only_messages.py** - Comprehensive test suite
2. **IMAGE_ONLY_MESSAGE_FIX.md** - This document

## Backward Compatibility

- ✅ No breaking changes
- ✅ All existing functionality preserved
- ✅ Messages with text + images still work
- ✅ Text-only messages still work
- ✅ Now image-only messages also work

## Related Code

The grouping logic in `src/utils/data_extractor.py` already had the correct handling:
- Images extracted via `extract_images_from_message()` for all messages
- No filtering of messages based on text presence
- Image-only messages grouped with same-day same-author messages

The only bug was in the initial filtering step in the Google Chat client.

## Verification Checklist

✅ Image-only messages are processed (not skipped)
✅ Images are extracted correctly
✅ Images grouped with text messages from same author/day
✅ All three formatting scenarios work
✅ Multiple image-only messages handled correctly
✅ PDF and non-image attachments correctly filtered out
✅ No regression in existing functionality

## Conclusion

Fixed a single-line bug that prevented image-only messages from being processed. The system is now robust to any formatting:
- Photo alone → text later ✅
- Text with photos ✅
- Text → photos later ✅
- Multiple photo-only messages ✅

**Status**: ✅ Production-ready
