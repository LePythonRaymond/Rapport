# Office Team and AVANT/APRÈS Fixes

## Summary
Fixed three critical issues with the report generation system:
1. Office team members' messages were being counted as interventions
2. AVANT/APRÈS image categorization had ordering issues causing regular images to appear in AVANT columns
3. The word "avant" in regular sentences (e.g., "avant de les arroser") was incorrectly triggering AVANT sections

## Issue 1: Office Team Member Interventions

### Problem
Office team messages were creating unwanted interventions in reports, while those same people should still be excludable from the INTERVENANTS list.

### Solution (current behavior — supersedes older notes)
Office traffic is governed by **`apply_on_off_filtering()`** in `src/utils/data_extractor.py`, not by a separate block inside `group_messages_by_intervention()`.

- **Per author and Paris calendar day**, state starts **OFF** for names in `config.OFFICE_TEAM_MEMBERS` (matched via `config.is_office_team_display_name()`, with normalized spelling/whitespace and known aliases such as `Vincent Da Silva` vs `Vincent Dasilva`).
- Office content is **dropped until** a valid **ON** marker appears (see `config.ON_MARKERS_PATTERN`: parenthesized `(on)` / `(ON)` or bare **`ON`** in capitals — French pronoun *on* is ignored).
- After **(OFF)**, subsequent messages that day are excluded again until the next ON.
- **INTERVENANTS** / gardener lists still use the same office name list (`extract_team_members()`, `page_builder`).

There is **no duplicate “drop all office” step in grouping**: messages that reach `group_messages_by_intervention()` are those that already passed ON/OFF rules (including deliberate office posts after `(ON)`).

### Auditing same-day behavior
Pass `trace_out=[]` into `apply_on_off_filtering(messages, trace_out=...)` to record per-message `state_before`, `state_after`, `included`, and `is_office_display_name` for a full-day replay.

## Issue 2: AVANT/APRÈS Image Ordering

### Problem
When an intervention had:
1. Regular text + images
2. "Avant" marker + images
3. "Après" marker + images

The regular images were incorrectly appearing in the AVANT columns in the Notion report. This was because the image categorization was based on position slicing rather than actual content matching.

### Root Cause
The previous implementation:
1. `detect_avant_apres_sections()` created three lists: `regular_images`, `avant_images`, `apres_images` (containing attachment objects)
2. `image_handler.process_intervention_images()` processed ALL images in order, creating `notion_images` list
3. `page_builder` tried to slice `notion_images` based on the counts: `notion_images[0:num_regular]`, `notion_images[num_regular:num_regular+num_avant]`, etc.

This approach assumed the images were in a specific order (regular → avant → après), but the actual image order in the intervention could be different based on message timestamps.

### Solution
Created proper image categorization during the Notion upload process:

**File: `src/utils/image_handler.py`**
- Modified `process_intervention_images()` to:
  1. Get the categorized image lists (`regular_images`, `avant_images`, `apres_images`)
  2. Create lookup sets by image name for each category
  3. As each image is uploaded to Notion, categorize it by matching the name
  4. Store three separate lists: `notion_regular_images`, `notion_avant_images`, `notion_apres_images`
  5. These categorized Notion URLs are stored directly in the intervention dictionary

**File: `src/notion/page_builder.py`**
- Updated `_create_intervention_blocks_with_images()` to:
  1. Use the pre-categorized lists (`notion_regular_images`, `notion_avant_images`, `notion_apres_images`)
  2. Display regular images first (if any)
  3. Then create the AVANT/APRÈS section with the correctly categorized images
  4. No more slicing or position assumptions

### Test Results
✅ Regular images are shown in the main section
✅ AVANT images are shown only in the AVANT column
✅ APRÈS images are shown only in the APRÈS column
✅ Works correctly even when there are no regular images (only AVANT/APRÈS)

## Issue 3: AVANT/APRÈS Marker Detection

### Problem
The word "avant" or "après" appearing in regular text (e.g., "Attendre 1/2 semaines avant de les arroser") was being detected as an AVANT/APRÈS section marker. This caused:
- Regular images to be incorrectly categorized as AVANT images
- The intervention text to be split inappropriately
- Confusing report layouts where normal text triggered before/after sections

### Root Cause
The previous implementation used a simple word boundary regex (`\b(avant|après)\b`) that matched ANY occurrence of these words, whether they were standalone section markers or part of regular sentences.

### Solution
Implemented intelligent marker detection in `detect_avant_apres_sections()`:

**File: `src/utils/data_extractor.py`**
- Added `is_marker_message()` helper function that checks if text is truly a section marker
- A message is considered a marker only if:
  1. It's just the marker word with optional punctuation (e.g., "Avant", "Avant:", "Avant !")
  2. It's very short (< 15 characters) and contains the marker
- Regular sentences containing "avant" or "après" are no longer treated as markers

### Detection Rules
**Treated as markers:**
- "Avant" or "AVANT" or "avant"
- "Avant:" or "Avant !"
- "Après" or "APRÈS" or "apres"
- "Après:" or "Après !"

**NOT treated as markers:**
- "Attendre avant de continuer" (in middle of sentence)
- "Il faut le faire avant" (at end of sentence)
- "Avant de faire X" (start of longer sentence)

### Test Results
✅ Pure markers correctly trigger AVANT/APRÈS sections
✅ "avant" in regular sentences does NOT trigger sections
✅ Regular text containing "avant de les arroser" is preserved in intervention text
✅ Images from messages with "avant" in regular text stay in regular category

## Testing

Created comprehensive test suite:

### Test Suite 1: Office Team and Image Categorization
**File:** `test_office_team_and_avant_apres.py` (run and removed)

#### Test 1: Office Team Exclusion
- Sends messages from Edward, Salomé, Luana, and Nicolas
- Verifies only Edward and Nicolas create interventions
- ✅ PASSED

#### Test 2: AVANT/APRÈS Categorization
- Regular images → AVANT images → APRÈS images
- Verifies correct counts: 2 regular, 3 avant, 3 après
- ✅ PASSED

#### Test 3: AVANT/APRÈS Without Regular Images
- Only AVANT and APRÈS, no regular images
- Verifies: 0 regular, 1 avant, 1 après
- ✅ PASSED

### Test Suite 2: Marker Detection
**File:** `test_avant_apres_fix.py` (run and removed)

#### Test 1: "avant" in Regular Text
- Message: "3 mini sujet remplacé! Attendre 1/2 semaines avant de les arroser" with 2 images
- Then "Avant" marker with 3 images
- Then "Après" marker with 3 images
- Verifies: 2 regular, 3 avant, 3 après (NOT 0 regular, 5 avant, 3 après)
- ✅ PASSED

#### Test 2: Pure Marker Detection
- Tests 8 different marker formats:
  - ✅ "Avant" (bare marker) - detected
  - ✅ "AVANT" (uppercase) - detected
  - ✅ "Avant:" (with colon) - detected
  - ✅ "Avant !" (with exclamation) - detected
  - ✅ "avant" (lowercase) - detected
  - ✅ "Avant de faire X" (in sentence) - NOT detected
  - ✅ "Il faut le faire avant" (at end) - NOT detected
  - ✅ "Attendre avant de continuer" (middle) - NOT detected
- ✅ ALL PASSED

## Impact
- **Office Team**: Their messages no longer create spurious interventions or interfere with gardener reports
- **AVANT/APRÈS Positioning**: Images are now correctly positioned in Notion reports, showing proper before/after comparisons in dedicated columns
- **Text Accuracy**: Regular text containing "avant" or "après" is preserved correctly without triggering unwanted sections
- **Data Integrity**: Improved accuracy and reliability of report generation

## Files Modified
1. `src/utils/data_extractor.py` - Added office team filtering AND intelligent AVANT/APRÈS marker detection
2. `src/utils/image_handler.py` - Added image categorization during upload (maps images to regular/avant/apres)
3. `src/notion/page_builder.py` - Updated to use pre-categorized images

## Related Documentation
- See `OFF RULES ETC_IMPLEMENTATION.md` for the overall intervention grouping rules
- See `CONTEXT.md` for the full system architecture
