import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dateutil import parser
import pytz
import config
from src.google_chat.people_resolver import format_name

def extract_date_from_message(message: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse timestamp from Google Chat message.

    Args:
        message: Message dictionary with 'createTime' field

    Returns:
        Parsed datetime object or None if parsing fails
    """
    try:
        create_time = message.get('createTime', '')
        if not create_time:
            return None

        # Parse ISO format timestamp
        parsed_date = parser.parse(create_time)
        return parsed_date
    except Exception as e:
        print(f"Error parsing date from message: {e}")
        return None

def filter_messages_by_date(messages: List[Dict[str, Any]], start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Filter messages within the specified date range.

    Args:
        messages: List of message dictionaries
        start_date: Start date for filtering
        end_date: End date for filtering

    Returns:
        Filtered list of messages within date range
    """
    filtered_messages = []

    for message in messages:
        message_date = extract_date_from_message(message)
        if message_date is None:
            continue

        # Ensure timezone awareness
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        if start_date <= message_date <= end_date:
            filtered_messages.append(message)

    return filtered_messages

def extract_images_from_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract attachment information from a message.

    Args:
        message: Message dictionary with attachments

    Returns:
        List of attachment dictionaries with download info
    """
    images = []
    attachments = message.get('attachments', [])

    # Debug logging
    if attachments:
        print(f"📎 Found {len(attachments)} attachments in message")

    for attachment in attachments:
        # Check if it's an image
        content_type = attachment.get('contentType', '').lower()
        if content_type.startswith('image/'):
            image_info = {
                'name': attachment.get('name', ''),
                'contentType': content_type,
                'downloadUri': attachment.get('downloadUri', ''),  # Fixed: use correct key
                'size': attachment.get('attachmentDataRef', {}).get('size', 0),
                'attachmentDataRef': attachment.get('attachmentDataRef', {})  # Preserve for download
            }
            images.append(image_info)
            print(f"🖼️ Extracted image: {image_info['name']} ({content_type})")

    return images

def split_message_text_at_off(text: str) -> Tuple[str, bool]:
    """
    Split message text at (OFF) marker and return text before it.

    Args:
        text: Message text that may contain (OFF) marker

    Returns:
        Tuple of (text_before_off, has_off_marker)
    """
    if not text:
        return "", False

    # Case-insensitive search for OFF marker
    pattern = re.compile(config.OFF_MARKERS_PATTERN, re.IGNORECASE)
    match = pattern.search(text)

    if match:
        # Return text before OFF marker
        text_before = text[:match.start()].strip()
        return text_before, True

    return text, False


def split_message_text_at_on(text: str) -> Tuple[str, bool]:
    """
    Split message text at (ON) marker and return text after it.

    Args:
        text: Message text that may contain (ON) marker

    Returns:
        Tuple of (text_after_on, has_on_marker)
    """
    if not text:
        return "", False

    pattern = re.compile(config.ON_MARKERS_PATTERN, re.IGNORECASE)
    match = pattern.search(text)

    if match:
        text_after = text[match.end():].strip()
        return text_after, True

    return text, False


def _is_office_team_author(author_name: str) -> bool:
    """True if author display name matches an office team member (case-insensitive)."""
    if not author_name:
        return False
    name_lower = author_name.lower()
    return any(office_name.lower() == name_lower for office_name in config.OFFICE_TEAM_MEMBERS)


def _message_has_image_attachments(message: Dict[str, Any]) -> bool:
    for a in message.get("attachments") or []:
        if (a.get("contentType") or "").lower().startswith("image/"):
            return True
    return False


def process_message_text_with_toggles(text: str, state_in: str) -> Tuple[str, str]:
    """
    Walk message text left-to-right, applying ON/OFF markers as toggles.
    Appends segments that fall while state is ON.

    Args:
        text: Raw message text (may be empty)
        state_in: 'on' or 'off' — inclusion state at start of this message

    Returns:
        Tuple of (output_text, state_out)
    """
    if state_in not in ("on", "off"):
        state_in = "on"

    if not text:
        return "", state_in

    off_p = re.compile(config.OFF_MARKERS_PATTERN, re.IGNORECASE)
    on_p = re.compile(config.ON_MARKERS_PATTERN, re.IGNORECASE)
    parts: List[str] = []
    i = 0
    state = state_in
    n = len(text)

    while i <= n:
        m_off = off_p.search(text, i)
        m_on = on_p.search(text, i)

        if m_off is None and m_on is None:
            if state == "on" and i < n:
                tail = text[i:].strip()
                if tail:
                    parts.append(tail)
            break

        if m_off is not None and m_on is not None:
            use_off = m_off.start() <= m_on.start()
        elif m_off is not None:
            use_off = True
        else:
            use_off = False

        if use_off:
            if state == "on":
                seg = text[i : m_off.start()].strip()
                if seg:
                    parts.append(seg)
                state = "off"
            # OFF while already OFF: no-op (skip marker only)
            i = m_off.end()
        else:
            assert m_on is not None
            if state == "off":
                state = "on"
                i = m_on.end()
            else:
                # ON while already ON: skip marker only
                i = m_on.end()

    out = "\n".join(parts) if parts else ""
    return out.strip(), state


def apply_on_off_filtering(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply ON/OFF toggle filtering before grouping.

    Default state each Paris calendar day per author:
    - Field / non-office: ON (messages included until OFF)
    - Office team: OFF (excluded until ON)

    Markers in text toggle state; text after OFF while ON is dropped from that segment;
    text before ON while OFF is dropped. Multiple toggles per day are allowed.
    State resets at each new day.

    Image-only messages: included when the inclusion state after processing is ON
    (and same rules as text for markers).

    Args:
        messages: List of message dictionaries (any order; sorted internally by time)

    Returns:
        Filtered list of messages in chronological order
    """
    if not messages:
        return []

    paris_tz = pytz.timezone(config.PARIS_TIMEZONE)

    def _sort_key(m: Dict[str, Any]):
        d = extract_date_from_message(m)
        return d or datetime.min.replace(tzinfo=timezone.utc)

    sorted_msgs = sorted(messages, key=_sort_key)
    # (author_email, date) -> 'on' | 'off'
    state: Dict[Tuple[str, Any], str] = {}
    filtered_messages: List[Dict[str, Any]] = []

    for message in sorted_msgs:
        message_date = extract_date_from_message(message)
        if message_date is None:
            filtered_messages.append(message)
            continue

        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        message_date_paris = message_date.astimezone(paris_tz)
        date_key = message_date_paris.date()

        author_email = message.get("author", {}).get("email", "")
        author_name = message.get("author", {}).get("name", "")
        if not author_email:
            filtered_messages.append(message)
            continue

        key = (author_email, date_key)
        if key not in state:
            state[key] = "off" if _is_office_team_author(author_name) else "on"

        text = message.get("text", "") or ""
        before = state[key]
        out_text, after = process_message_text_with_toggles(text, before)
        state[key] = after

        has_image = _message_has_image_attachments(message)
        include = bool(out_text.strip()) or (has_image and after == "on")

        if include:
            filtered_message = message.copy()
            filtered_message["text"] = out_text
            filtered_messages.append(filtered_message)
            if before != after or (out_text and out_text != text.strip()):
                if len(out_text) > 50:
                    print(
                        f"✂️ ON/OFF toggle for {author_email} on {date_key}: "
                        f"state {before!r}→{after!r}, kept text: {out_text[:50]!r}..."
                    )
                else:
                    print(
                        f"✂️ ON/OFF toggle for {author_email} on {date_key}: "
                        f"state {before!r}→{after!r}, kept: {out_text!r}"
                    )
        else:
            print(
                f"🚫 Excluded message (state {before!r}→{after!r}) for {author_email} on {date_key}"
            )

    print(f"📊 ON/OFF filtering: {len(messages)} messages → {len(filtered_messages)} messages")
    return filtered_messages


# Backward-compatible alias
apply_off_rule_filtering = apply_on_off_filtering

def extract_date_from_text(text: str) -> Tuple[Optional[int], Optional[int], bool]:
    """
    Extract date in DD/MM format from text.

    Args:
        text: Message text that may contain date

    Returns:
        Tuple of (day, month, found_date)
        If no date found: (None, None, False)
    """
    if not text:
        return None, None, False

    # Search for DD/MM pattern
    pattern = re.compile(config.DATE_PATTERN)
    match = pattern.search(text)

    if match:
        try:
            day = int(match.group(1))
            month = int(match.group(2))

            # Validate day and month ranges
            if 1 <= day <= 31 and 1 <= month <= 12:
                print(f"📅 Extracted date from text: {day:02d}/{month:02d}")
                return day, month, True
            else:
                print(f"⚠️ Invalid date values in text: {day}/{month}")
                return None, None, False
        except (ValueError, IndexError):
            return None, None, False

    return None, None, False

def detect_avant_apres_sections(messages_in_intervention: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect AVANT/APRÈS sections in intervention messages and categorize images.
    Only treats "avant/après" as markers when they appear as standalone section markers,
    not when used in regular sentences.

    Args:
        messages_in_intervention: List of messages belonging to one intervention

    Returns:
        Dictionary with categorized images and text:
        {
            'has_avant_apres': bool,
            'avant_images': [...],
            'apres_images': [...],
            'regular_images': [...],
            'regular_text': str
        }
    """
    result = {
        'has_avant_apres': False,
        'avant_images': [],
        'apres_images': [],
        'regular_images': [],
        'regular_text': ''
    }

    if not messages_in_intervention:
        return result

    # Track state: 'before_avant', 'in_avant', 'in_apres'
    state = 'before_avant'
    text_parts = []

    def is_marker_message(text: str, marker_pattern: re.Pattern) -> bool:
        """
        Check if text is a section marker (not just containing the word in regular text).
        A marker message is one where the marker word appears with minimal other content.
        """
        if not text:
            return False

        # Clean up the text
        text_clean = text.strip().lower()

        # Check if the entire message is just the marker (possibly with punctuation)
        # e.g., "Avant", "avant", "AVANT", "Avant:", "Avant !", "Before", "After", etc.
        # Handles any capitalization, spacing, and common punctuation
        if re.match(r'^(avant|après|apres|before|after)\s*[:\-!.\s]*$', text_clean):
            return True

        # Check if text is very short (< 15 chars) and contains the marker
        # This catches cases like "Avant" or "Avant photo"
        if len(text_clean) < 15 and marker_pattern.search(text):
            return True

        return False

    avant_pattern = re.compile(config.AVANT_MARKERS_PATTERN, re.IGNORECASE)
    apres_pattern = re.compile(config.APRES_MARKERS_PATTERN, re.IGNORECASE)

    for message in messages_in_intervention:
        text = message.get('text', '')
        images = message.get('attachments', [])

        # Check if this message is an AVANT or APRÈS marker (not just containing the word)
        is_avant_marker = is_marker_message(text, avant_pattern)
        is_apres_marker = is_marker_message(text, apres_pattern)

        # Update state based on markers
        if is_avant_marker and state == 'before_avant':
            state = 'in_avant'
            result['has_avant_apres'] = True
            print(f"🖼️ AVANT section detected (marker text: '{text.strip()}')")
        elif is_apres_marker and state in ['before_avant', 'in_avant']:
            state = 'in_apres'
            result['has_avant_apres'] = True
            print(f"🖼️ APRÈS section detected (marker text: '{text.strip()}')")

        # Categorize images based on current state
        for attachment in images:
            content_type = attachment.get('contentType', '').lower()
            if content_type.startswith('image/'):
                if state == 'before_avant':
                    result['regular_images'].append(attachment)
                elif state == 'in_avant':
                    result['avant_images'].append(attachment)
                elif state == 'in_apres':
                    result['apres_images'].append(attachment)

        # Collect text for regular_text
        # Only exclude text if it's a pure marker message
        if text and not (is_avant_marker or is_apres_marker):
            text_parts.append(text)
        # If it's a marker with some additional text, include the non-marker part
        # (though typically markers should be standalone)

    result['regular_text'] = '\n'.join(text_parts)

    if result['has_avant_apres']:
        print(f"📊 AVANT/APRÈS detection: {len(result['avant_images'])} avant, {len(result['apres_images'])} après, {len(result['regular_images'])} regular images")

    return result

def group_messages_by_intervention(messages: List[Dict[str, Any]], time_threshold_minutes: int = None) -> List[Dict[str, Any]]:
    """
    Group related messages (text + images) as single interventions.
    Messages from the same author on the same day (Paris timezone) are grouped together.

    Office team messages are filtered upstream by apply_on_off_filtering() (default OFF until ON).

    Args:
        messages: List of message dictionaries
        time_threshold_minutes: Deprecated parameter, kept for backward compatibility but ignored

    Returns:
        List of intervention dictionaries, each containing grouped messages
    """
    if not messages:
        return []

    # Get Paris timezone
    paris_tz = pytz.timezone(config.PARIS_TIMEZONE)

    # Sort messages by time
    sorted_messages = sorted(messages, key=lambda x: extract_date_from_message(x) or datetime.min.replace(tzinfo=timezone.utc))

    interventions = []
    current_intervention = None

    for message in sorted_messages:
        message_date = extract_date_from_message(message)
        if message_date is None:
            continue

        # Convert to Paris timezone
        if message_date.tzinfo is None:
            message_date = message_date.replace(tzinfo=timezone.utc)
        message_date_paris = message_date.astimezone(paris_tz)
        message_day = message_date_paris.date()

        author_email = message.get('author', {}).get('email', '')
        text = message.get('text', '').strip()

        # Don't skip messages with only images - they should be included
        # (This was already handled correctly, but making it explicit)

        # Check if this message should start a new intervention
        # New intervention if: no current intervention, different author, or different day
        should_start_new = (
            current_intervention is None or
            author_email != current_intervention['author_email'] or
            message_day != current_intervention['intervention_day']
        )

        if should_start_new:
            # Save previous intervention if it exists
            if current_intervention is not None:
                # Process avant/après sections and extract date before saving
                _finalize_intervention(current_intervention)
                interventions.append(current_intervention)

            # Before creating a new intervention, check if there's already
            # a finalized intervention for this author on this day
            existing_intervention = None
            for intervention in interventions:
                if (intervention.get('author_email') == author_email and
                    intervention.get('intervention_day') == message_day):
                    existing_intervention = intervention
                    break

            if existing_intervention is not None:
                # Merge message into existing intervention
                # Insert message in chronological order within the messages list
                existing_messages = existing_intervention['messages']
                insert_position = len(existing_messages)
                for i, existing_msg in enumerate(existing_messages):
                    existing_msg_date = extract_date_from_message(existing_msg)
                    if existing_msg_date and message_date < existing_msg_date:
                        insert_position = i
                        break
                existing_messages.insert(insert_position, message)

                # Append text to all_text with newline separator
                if text:
                    if existing_intervention.get('all_text'):
                        existing_intervention['all_text'] += f"\n{text}"
                    else:
                        existing_intervention['all_text'] = text

                # Update last_message_time if this message is later
                if message_date > existing_intervention.get('last_message_time', datetime.min.replace(tzinfo=timezone.utc)):
                    existing_intervention['last_message_time'] = message_date

                # Update start_time if this message is earlier
                if message_date < existing_intervention.get('start_time', datetime.max.replace(tzinfo=timezone.utc)):
                    existing_intervention['start_time'] = message_date

                # Extend images list with new images
                existing_intervention['images'].extend(extract_images_from_message(message))

                # Re-finalize intervention to update metadata (date extraction, avant/après detection)
                _finalize_intervention(existing_intervention)

                # Don't create a new intervention, continue to next message
                current_intervention = None
                continue

            # Start new intervention (no existing intervention found)
            current_intervention = {
                'author_email': author_email,
                'author_name': message.get('author', {}).get('name', 'Unknown'),
                'start_time': message_date,
                'intervention_day': message_day,
                'last_message_time': message_date,
                'messages': [message],
                'all_text': text if text else '',
                'images': extract_images_from_message(message)
            }
        else:
            # Add to current intervention
            current_intervention['messages'].append(message)
            if text:
                if current_intervention['all_text']:
                    current_intervention['all_text'] += f"\n{text}"
                else:
                    current_intervention['all_text'] = text
            current_intervention['last_message_time'] = message_date

            # Add images from this message
            current_intervention['images'].extend(extract_images_from_message(message))

    # Add the last intervention
    if current_intervention is not None:
        _finalize_intervention(current_intervention)
        interventions.append(current_intervention)

    # Debug logging
    total_images = sum(len(intervention.get('images', [])) for intervention in interventions)
    print(f"📊 Grouped {len(messages)} messages into {len(interventions)} interventions with {total_images} total images")

    # Log author names found in interventions
    author_names_found = set()
    for intervention in interventions:
        author_name = intervention.get('author_name', 'Unknown')
        if author_name:
            author_names_found.add(author_name)
    print(f"👤 Author names found in interventions: {sorted(list(author_names_found))}")

    return interventions

def _finalize_intervention(intervention: Dict[str, Any]) -> None:
    """
    Finalize an intervention by extracting date from text and detecting avant/après sections.

    Args:
        intervention: Intervention dictionary to finalize (modified in place)
    """
    # Extract date from text
    all_text = intervention.get('all_text', '')
    day, month, found_date = extract_date_from_text(all_text)

    if found_date and day and month:
        # Use current year (or year from start_time if available)
        start_time = intervention.get('start_time')
        year = start_time.year if start_time else datetime.now().year

        try:
            intervention_date = datetime(year, month, day)
            intervention['intervention_date'] = intervention_date
            intervention['date_source'] = 'extracted'
        except ValueError:
            # Invalid date - fall back to timestamp
            intervention['intervention_date'] = intervention.get('start_time')
            intervention['date_source'] = 'timestamp'
    else:
        # No date found in text - use timestamp
        intervention['intervention_date'] = intervention.get('start_time')
        intervention['date_source'] = 'timestamp'

    # Detect avant/après sections
    messages_list = intervention.get('messages', [])
    avant_apres_data = detect_avant_apres_sections(messages_list)

    # Add avant/après data to intervention
    intervention['has_avant_apres'] = avant_apres_data['has_avant_apres']
    intervention['avant_images'] = avant_apres_data['avant_images']
    intervention['apres_images'] = avant_apres_data['apres_images']
    intervention['regular_images'] = avant_apres_data['regular_images']

    # If there's specific text from avant/après parsing, use it
    if avant_apres_data['regular_text']:
        intervention['all_text'] = avant_apres_data['regular_text']

def _time_gap_too_large(current_time: datetime, last_time: datetime, threshold_minutes: int) -> bool:
    """
    Check if the time gap between two messages is too large to group them.

    Args:
        current_time: Current message timestamp
        last_time: Last message timestamp
        threshold_minutes: Maximum gap in minutes

    Returns:
        True if gap is too large, False otherwise
    """
    time_diff = current_time - last_time
    return time_diff.total_seconds() > (threshold_minutes * 60)

def extract_mentions_from_text(text: str) -> List[str]:
    """
    Extract @mentions from message text.

    Handles formats like:
    - @Alice MARTIN
    - @ALICE MARTIN
    - @Jean-Pierre DUPONT
    - @Marie Louise BERNARD

    Args:
        text: Message text that may contain @mentions

    Returns:
        List of mentioned names (without @ symbol)
    """
    if not text:
        return []

    # Pattern to match @Name Name (2+ words, stopping at lowercase words or punctuation)
    # Matches names in any case (UPPERCASE, lowercase, Mixed)
    # Stops at common lowercase conjunctions (et, a, ont, etc.) or non-letter characters
    # Each name part must start with a letter and can contain letters and hyphens
    mention_pattern = r'@([A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\-]+(?:[ \t]+[A-ZÀ-Ÿ][A-ZÀ-Ÿa-zà-ÿ\-]+)*)'

    mentions = re.findall(mention_pattern, text)

    if mentions:
        print(f"👥 Found {len(mentions)} mention(s) in text: {mentions}")

    return mentions

def extract_team_members(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Extract unique team members from messages, including authors and @mentioned people.
    Excludes office team members.

    Args:
        messages: List of message dictionaries

    Returns:
        List of team member dictionaries with name and email (excluding office team)
    """
    team_members = {}
    office_team_members = [name.lower() for name in config.OFFICE_TEAM_MEMBERS]  # Case-insensitive comparison

    for message in messages:
        # Extract message author
        author = message.get('author', {})
        email = author.get('email', '')
        name = author.get('name', 'Unknown')

        # Skip office team members (case-insensitive check)
        name_lower = name.lower()
        is_office_team = any(office_name.lower() == name_lower for office_name in config.OFFICE_TEAM_MEMBERS)

        if not is_office_team:
            # Only add if we have an email and it's not already in the list
            if email and email not in team_members:
                formatted_name = format_name(name)
                team_members[email] = {
                    'name': formatted_name,
                    'email': email
                }
                print(f"✅ Added team member (author): {formatted_name} ({email})")
        else:
            print(f"🚫 Excluded office team member from team_info: {name}")

        # Extract @mentions from message text
        text = message.get('text', '')
        if text:
            mentioned_names = extract_mentions_from_text(text)

            for mentioned_name in mentioned_names:
                # Format the name properly
                formatted_mentioned_name = format_name(mentioned_name)

                # Check if mentioned person is office team member
                mentioned_name_lower = formatted_mentioned_name.lower()
                is_mentioned_office_team = any(
                    office_name.lower() == mentioned_name_lower
                    for office_name in config.OFFICE_TEAM_MEMBERS
                )

                if is_mentioned_office_team:
                    print(f"🚫 Excluded mentioned office team member: {formatted_mentioned_name}")
                    continue

                # Use name as key (since we don't have email for mentioned people)
                # Use a synthetic key to avoid conflicts
                mention_key = f"mention_{formatted_mentioned_name.lower().replace(' ', '_')}"

                if mention_key not in team_members:
                    team_members[mention_key] = {
                        'name': formatted_mentioned_name,
                        'email': ''  # No email available for mentioned people
                    }
                    print(f"✅ Added team member (mentioned): {formatted_mentioned_name}")

    return list(team_members.values())

def clean_text(text: str) -> str:
    """
    Clean and normalize text from messages.

    Args:
        text: Raw text from message

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove common chat artifacts
    text = re.sub(r'^[:\-\s]+', '', text)  # Remove leading colons, dashes
    text = re.sub(r'[:\-\s]+$', '', text)  # Remove trailing colons, dashes

    return text.strip()

def categorize_intervention_type(text: str) -> str:
    """
    Categorize intervention type based on text content.

    Args:
        text: Intervention text

    Returns:
        Category string (e.g., "Taille", "Désherbage", "Arrosage", etc.)
    """
    text_lower = text.lower()

    # Define keyword mappings
    categories = {
        'Taille': ['taille', 'taillé', 'coupe', 'élagage', 'élagué'],
        'Désherbage': ['désherbage', 'désherbé', 'mauvaises herbes', 'herbes'],
        'Arrosage': ['arrosage', 'arrosé', 'eau', 'irrigation'],
        'Nettoyage': ['nettoyage', 'nettoyé', 'propre', 'ramassage'],
        'Plantation': ['plantation', 'planté', 'semis', 'repiquage'],
        'Fertilisation': ['engrais', 'fertilisation', 'nutriments'],
        'Palissage': ['palissage', 'palissé', 'tuteur', 'support'],
        'Entretien général': ['entretien', 'maintenance', 'ras', 'rien à signaler']
    }

    # Find matching category
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword in text_lower:
                return category

    return 'Autre'

def extract_key_phrases(text: str) -> List[str]:
    """
    Extract key phrases from intervention text.

    Args:
        text: Intervention text

    Returns:
        List of key phrases
    """
    # Common gardening terms to look for
    key_terms = [
        'taille', 'désherbage', 'arrosage', 'nettoyage', 'plantation',
        'fertilisation', 'palissage', 'élagage', 'coupe', 'semis',
        'repiquage', 'tuteur', 'support', 'engrais', 'irrigation'
    ]

    found_phrases = []
    text_lower = text.lower()

    for term in key_terms:
        if term in text_lower:
            found_phrases.append(term)

    return found_phrases

def validate_intervention_data(intervention: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate intervention data for completeness and quality.

    Args:
        intervention: Intervention dictionary

    Returns:
        Tuple of (is_valid, list_of_issues)
    """
    issues = []

    # Check required fields
    if not intervention.get('all_text', '').strip():
        issues.append("No text content")

    if not intervention.get('author_name'):
        issues.append("No author information")

    if not intervention.get('start_time'):
        issues.append("No timestamp")

    # Check text quality
    text = intervention.get('all_text', '')
    if len(text.strip()) < 3:
        issues.append("Text too short")

    # Check for meaningful content
    if text.lower().strip() in ['ok', 'okay', 'rien', '']:
        issues.append("Minimal content")

    is_valid = len(issues) == 0
    return is_valid, issues

def format_intervention_summary(intervention: Dict[str, Any]) -> str:
    """
    Create a summary string for an intervention.

    Args:
        intervention: Intervention dictionary

    Returns:
        Formatted summary string
    """
    author = intervention.get('author_name', 'Unknown')
    start_time = intervention.get('start_time')
    text = intervention.get('all_text', '')

    if start_time:
        time_str = start_time.strftime('%d/%m/%Y %H:%M')
    else:
        time_str = 'Unknown time'

    # Truncate text if too long
    if len(text) > 100:
        text = text[:97] + '...'

    return f"{author} - {time_str}: {text}"
