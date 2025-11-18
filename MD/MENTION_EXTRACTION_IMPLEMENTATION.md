# @Mention Extraction Implementation

## Overview
Added functionality to extract @mentions from intervention messages so that all team members (including those mentioned but not authoring messages) appear in reports.

## What Was Changed

### 1. New Function: `extract_mentions_from_text()` ([src/utils/data_extractor.py](src/utils/data_extractor.py))

**Purpose**: Extract @mentions from message text

**Pattern**: `r'@([A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\-]+(?:\s+[A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\-]+)*)'`

**Handles**:
- Simple mentions: `@Alice MARTIN`
- ALL CAPS: `@ALICE MARTIN`
- Hyphenated names: `@Jean-Pierre DUPONT`
- Multiple first/last names: `@Marie Louise BERNARD`
- Multiple mentions in one message: `@Alice MARTIN et @Paul LECLERC`

**Stops at**:
- Lowercase conjunctions (et, a, ont, etc.)
- Punctuation
- Non-letter characters
- Email addresses (e.g., `test@example.com` is NOT captured)

### 2. Updated Function: `extract_team_members()` ([src/utils/data_extractor.py](src/utils/data_extractor.py))

**Before**:
- Only extracted message authors
- Used author email as unique key

**After**:
- Extracts both message authors AND @mentioned people
- Authors use email as key
- Mentioned people use synthetic key: `mention_{name_lowercase}`
- Both are formatted with proper capitalization
- Both are checked against office team exclusion list

**Return Structure**:
```python
[
    {
        'name': 'Edward Carey',
        'email': 'edward@example.com'  # Author - has email
    },
    {
        'name': 'Alice Martin',
        'email': ''  # Mentioned - no email available
    }
]
```

### 3. Imported Existing Function

**Reused**: `format_name()` from `src/google_chat/people_resolver.py`
- Ensures consistent name capitalization
- Handles hyphenated names properly
- Applied to both authors and mentioned people

## Use Cases

### Scenario 1: Duo Work
```
Message from Edward: "En binôme avec @Alice MARTIN"
```
**Result**: Report shows both Edward Carey and Alice Martin in INTERVENANTS section

### Scenario 2: Multiple Mentions
```
Message: "@Marie DUPONT et @Paul LECLERC ont fait la taille"
```
**Result**: All three team members appear (message author + 2 mentioned)

### Scenario 3: Office Team Exclusion
```
Message: "En binôme avec @Salomé Cremona"
```
**Result**: Salomé is excluded (office team), only message author appears

## Testing

Created comprehensive test suite ([test_mention_extraction.py](test_mention_extraction.py)):

### Test Coverage:
✅ Simple @mention extraction
✅ Hyphenated names
✅ Multiple mentions in one message
✅ No false positives (email addresses ignored)
✅ ALL CAPS names
✅ Team member extraction with mentions
✅ Author + mentioned person both appear

### Test Results:
**All tests passing (100% success rate)**

## Integration Points

### Where It's Used:

1. **main.py** (line 279):
   ```python
   team_members = extract_team_members(messages)
   team_info = {
       'jardiniers': [member['name'] for member in team_members],
       ...
   }
   ```

2. **Report Page Builder** (src/notion/page_builder.py):
   - INTERVENANTS section displays all team members
   - Office team members are filtered out
   - Both authors and mentioned people appear in the list

### Data Flow:
```
Google Chat Messages
    ↓
extract_team_members()
    ↓
extract_mentions_from_text() (for each message)
    ↓
format_name() (for consistency)
    ↓
Office team filtering
    ↓
INTERVENANTS section in Notion report
```

## Edge Cases Handled

1. **Duplicate mentions**: Only added once (using synthetic key)
2. **Same person as author and mentioned**: Handled correctly (author entry used)
3. **Office team members mentioned**: Excluded from gardener list
4. **Email addresses in text**: Not captured as mentions
5. **Lowercase words after mention**: Stop pattern matching (e.g., "et", "ont")
6. **No mentions in message**: Returns empty list, no errors

## Backward Compatibility

- ✅ Existing functionality preserved (authors still extracted)
- ✅ Return structure extended but compatible
- ✅ Office team exclusion still works
- ✅ Name formatting consistent with existing code

## Performance

- O(n*m) where n = number of messages, m = average message length
- Regex compilation happens once per call
- Negligible impact on overall processing time

## Files Modified

1. **src/utils/data_extractor.py**
   - Added `extract_mentions_from_text()` function
   - Updated `extract_team_members()` to extract mentions
   - Imported `format_name()` from people_resolver

## Files Created

1. **test_mention_extraction.py** - Test suite for mention extraction
2. **MENTION_EXTRACTION_IMPLEMENTATION.md** - This document

## Example Output

### Before:
```
INTERVENANTS:
- Edward Carey
```

### After (with @Alice MARTIN mentioned):
```
INTERVENANTS:
- Edward Carey
- Alice Martin
```

## Future Enhancements (Optional)

1. Support for first name only mentions (e.g., `@Alice`)
2. Fuzzy matching to resolve mentioned names to actual users
3. Link mentioned people to their user profiles if available
4. Statistics on most frequently mentioned team members

## Conclusion

The @mention extraction feature is fully implemented and tested. It seamlessly integrates with the existing team member extraction logic and ensures that all gardeners involved in an intervention (whether authoring messages or being mentioned) appear in the final reports.

**Status**: ✅ Production-ready
