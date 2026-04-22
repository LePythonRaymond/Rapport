#!/usr/bin/env python3
"""
Test script for new intervention grouping and filtering features.
Tests OFF rule filtering, AVANT/APRÈS detection, date extraction, and same-day grouping.
"""

import sys
from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import List, Dict, Any
import pytz
from PIL import Image

# Import the functions we want to test
from src.utils.data_extractor import (
    split_message_text_at_off,
    split_message_text_at_on,
    apply_on_off_filtering,
    apply_off_rule_filtering,
    process_message_text_with_toggles,
    extract_date_from_text,
    detect_avant_apres_sections,
    group_messages_by_intervention,
    extract_date_from_message,
)
from src.utils.image_handler import ImageHandler
import config

def create_test_message(text: str, author_email: str, author_name: str,
                       create_time: datetime, attachments: List[Dict] = None) -> Dict[str, Any]:
    """Helper to create a test message."""
    return {
        'text': text,
        'author': {
            'email': author_email,
            'name': author_name
        },
        'createTime': create_time.isoformat(),
        'attachments': attachments or []
    }

def test_off_rule_splitting():
    """Test the split_message_text_at_off function."""
    print("\n=== Testing OFF Rule Text Splitting ===")

    test_cases = [
        ("Normal text with no marker", "Normal text with no marker", False),
        ("Some text (OFF) private stuff", "Some text", True),
        ("Text with off in middle", "Text with", True),
        ("(off) everything is private", "", True),
        ("OFF at the start", "", True),
    ]

    for input_text, expected_text, expected_has_off in test_cases:
        result_text, has_off = split_message_text_at_off(input_text)
        success = result_text == expected_text and has_off == expected_has_off
        status = "✅" if success else "❌"
        print(f"{status} Input: '{input_text[:50]}...'")
        print(f"   Expected: ('{expected_text}', {expected_has_off})")
        print(f"   Got:      ('{result_text}', {has_off})")
        if not success:
            print("   FAILED!")

def test_date_extraction():
    """Test the extract_date_from_text function."""
    print("\n=== Testing Date Extraction ===")

    test_cases = [
        ("Intervention du 06/12 effectuée", 6, 12, True),
        ("Le 1/3 nous avons fait le désherbage", 1, 3, True),
        ("Taille effectuée le 25/11", 25, 11, True),
        ("No date in this text", None, None, False),
        ("Invalid date 45/99", None, None, False),
    ]

    for text, expected_day, expected_month, expected_found in test_cases:
        day, month, found = extract_date_from_text(text)
        success = day == expected_day and month == expected_month and found == expected_found
        status = "✅" if success else "❌"
        print(f"{status} Text: '{text[:50]}...'")
        print(f"   Expected: ({expected_day}, {expected_month}, {expected_found})")
        print(f"   Got:      ({day}, {month}, {found})")
        if not success:
            print("   FAILED!")

def test_avant_apres_detection():
    """Test the detect_avant_apres_sections function."""
    print("\n=== Testing AVANT/APRÈS Detection ===")

    # Test case 1: Messages with AVANT and APRÈS markers
    messages = [
        {
            'text': 'Voici le travail effectué',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'regular1.jpg'}
            ]
        },
        {
            'text': 'Avant',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'avant1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant2.jpg'}
            ]
        },
        {
            'text': 'Après',
            'attachments': [
                {'contentType': 'image/jpeg', 'name': 'apres1.jpg'}
            ]
        }
    ]

    result = detect_avant_apres_sections(messages)
    print(f"Has avant/après: {result['has_avant_apres']}")
    print(f"Regular images: {len(result['regular_images'])} (expected 1)")
    print(f"Avant images: {len(result['avant_images'])} (expected 2)")
    print(f"Après images: {len(result['apres_images'])} (expected 1)")

    success = (result['has_avant_apres'] and
              len(result['regular_images']) == 1 and
              len(result['avant_images']) == 2 and
              len(result['apres_images']) == 1 and
              len(result.get('composite_split_image_names', [])) == 0)

    status = "✅" if success else "❌"
    print(f"{status} AVANT/APRÈS detection test")

def test_combined_avant_apres_marker_detection():
    """Single message 'Avant/après' + one image → split list, not stuck in après only."""
    print("\n=== Testing Combined AVANT/APRÈS Marker (collage) ===")

    collage_att = {'contentType': 'image/jpeg', 'name': 'collage.jpg'}
    cases = [
        ('Avant/après', ['collage.jpg']),
        ('Avant/arpès', ['collage.jpg']),
        ('before|after', ['collage.jpg']),
        ('AVANT / APRÈS ', ['collage.jpg']),
    ]
    all_ok = True
    for text, expected_names in cases:
        messages = [{'text': text, 'attachments': [collage_att]}]
        r = detect_avant_apres_sections(messages)
        ok = (
            r['has_avant_apres'] and
            r.get('composite_split_image_names') == expected_names and
            len(r['avant_images']) == 0 and
            len(r['apres_images']) == 0 and
            len(r['regular_images']) == 0
        )
        st = '✅' if ok else '❌'
        print(f"   {st} {text!r} → split names {r.get('composite_split_image_names')}")
        all_ok = all_ok and ok

    # Combined + two images in same message → 1st = avant, 2nd = après (left/right split)
    two = [
        {'contentType': 'image/jpeg', 'name': 'a.jpg'},
        {'contentType': 'image/jpeg', 'name': 'b.jpg'},
    ]
    r2 = detect_avant_apres_sections([{'text': 'Avant/après', 'attachments': two}])
    ok2 = (
        r2['has_avant_apres'] and
        len(r2['composite_split_image_names']) == 0 and
        [img.get('name') for img in r2['avant_images']] == ['a.jpg'] and
        [img.get('name') for img in r2['apres_images']] == ['b.jpg']
    )
    print(f"   {'✅' if ok2 else '❌'} Two images with combined marker → 1st avant, 2nd après")
    all_ok = all_ok and ok2

    # Combined + four images in same message → first two = avant, last two = après
    four = [
        {'contentType': 'image/jpeg', 'name': f'img_{i}.jpg'} for i in range(4)
    ]
    r2b = detect_avant_apres_sections([{'text': 'Avant/après', 'attachments': four}])
    ok2b = (
        r2b['has_avant_apres'] and
        [img.get('name') for img in r2b['avant_images']] == ['img_0.jpg', 'img_1.jpg'] and
        [img.get('name') for img in r2b['apres_images']] == ['img_2.jpg', 'img_3.jpg']
    )
    print(f"   {'✅' if ok2b else '❌'} Four images with combined marker → 2/2 split")
    all_ok = all_ok and ok2b

    # Combined text-only marker, then two image-only messages → 1st avant, 2nd après
    r2c = detect_avant_apres_sections([
        {'text': 'Avant/après', 'attachments': []},
        {'text': '', 'attachments': [{'contentType': 'image/jpeg', 'name': 'left.jpg'}]},
        {'text': '', 'attachments': [{'contentType': 'image/jpeg', 'name': 'right.jpg'}]},
    ])
    ok2c = (
        r2c['has_avant_apres'] and
        [img.get('name') for img in r2c['avant_images']] == ['left.jpg'] and
        [img.get('name') for img in r2c['apres_images']] == ['right.jpg'] and
        len(r2c['regular_images']) == 0
    )
    print(f"   {'✅' if ok2c else '❌'} Combined marker then two image-only messages → 50/50 split")
    all_ok = all_ok and ok2c

    # After a self-contained combined marker, regular images in later messages stay regular.
    r2d = detect_avant_apres_sections([
        {'text': 'Avant/après', 'attachments': two},
        {'text': 'Photo annexe', 'attachments': [{'contentType': 'image/jpeg', 'name': 'c.jpg'}]},
    ])
    ok2d = (
        r2d['has_avant_apres'] and
        [img.get('name') for img in r2d['avant_images']] == ['a.jpg'] and
        [img.get('name') for img in r2d['apres_images']] == ['b.jpg'] and
        [img.get('name') for img in r2d['regular_images']] == ['c.jpg']
    )
    print(f"   {'✅' if ok2d else '❌'} Self-contained combined marker does not leak state to next message")
    all_ok = all_ok and ok2d

    # Not a combined marker (sentence)
    r3 = detect_avant_apres_sections([{
        'text': 'Photos avant et après la taille',
        'attachments': [collage_att],
    }])
    ok3 = not r3['has_avant_apres'] and len(r3['composite_split_image_names']) == 0
    print(f"   {'✅' if ok3 else '❌'} Long sentence not treated as combined marker")
    all_ok = all_ok and ok3

    print(f"\n   {'✅ ALL PASSED' if all_ok else '❌ SOME FAILED'}: combined marker detection\n")
    return all_ok

def test_composite_split_image_halves():
    """Wide JPEG → left/right halves match crop geometry after JPEG round-trip."""
    print("\n=== Testing Composite Image Halves (PIL) ===")

    handler = ImageHandler()
    wide = Image.new('RGB', (400, 100), (200, 30, 40))
    buf = BytesIO()
    wide.save(buf, format='JPEG', quality=95)
    raw = buf.getvalue()

    im = Image.open(BytesIO(raw))
    w, h = im.size
    mid = w // 2
    left = im.crop((0, 0, mid, h))
    right = im.crop((mid, 0, w, h))
    lb = handler._pil_to_jpeg_bytes(left)
    rb = handler._pil_to_jpeg_bytes(right)

    li = Image.open(BytesIO(lb))
    ri = Image.open(BytesIO(rb))
    ratio = w / h if h else 0
    ok = (
        ratio >= config.COMPOSITE_MIN_ASPECT_RATIO and
        li.size[0] == mid and ri.size[0] == (w - mid) and
        li.size[1] == h and ri.size[1] == h and
        len(lb) > 100 and len(rb) > 100
    )
    print(f"   Wide ratio {ratio:.2f} (min {config.COMPOSITE_MIN_ASPECT_RATIO})")
    print(f"   {'✅' if ok else '❌'} Left {li.size}, right {ri.size}")
    print(f"\n   {'✅ PASSED' if ok else '❌ FAILED'}: composite split geometry\n")
    return ok

def test_group_intervention_split_flag_for_composite():
    """End-to-end: grouped intervention marks image dict with split_for_avant_apres."""
    print("\n=== Testing split_for_avant_apres on intervention images ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)
    messages = [
        create_test_message(
            'Avant/après',
            'gardener@example.com',
            'Gardener',
            base_date,
            [{'contentType': 'image/jpeg', 'name': 'one_collage.jpg'}],
        ),
    ]
    interventions = group_messages_by_intervention(messages)
    if not interventions:
        print("   ❌ No intervention")
        return False
    inv = interventions[0]
    imgs = inv.get('images', [])
    ok = (
        inv.get('has_avant_apres') and
        inv.get('composite_split_image_names') == ['one_collage.jpg'] and
        len(imgs) == 1 and
        imgs[0].get('split_for_avant_apres') is True
    )
    print(f"   {'✅' if ok else '❌'} split flag on image: {imgs[0] if imgs else {}}")
    print(f"\n   {'✅ PASSED' if ok else '❌ FAILED'}: finalize composite flag\n")
    return ok

def test_on_rule_splitting():
    """Test split_message_text_at_on (text after first ON marker)."""
    print("\n=== Testing ON Rule Text Splitting ===")

    test_cases = [
        ("Normal text with no marker", "Normal text with no marker", False),
        ("Some text (ON) include this", "include this", True),
        # Bare mixed/lowercase "on" is not a marker (French pronoun); caps ON is
        ("oN at the start", "oN at the start", False),
        ("on est passés ce matin", "on est passés ce matin", False),
        ("ON fin de journée OK", "fin de journée OK", True),
        ("(on) Hello team", "Hello team", True),
        ("public (ON) after", "after", True),
    ]

    for input_text, expected_text, expected_has_on in test_cases:
        result_text, has_on = split_message_text_at_on(input_text)
        success = result_text == expected_text and has_on == expected_has_on
        status = "✅" if success else "❌"
        print(f"{status} Input: {input_text!r}")
        print(f"   Expected: ({expected_text!r}, {expected_has_on}), Got: ({result_text!r}, {has_on})")
        if not success:
            print("   FAILED!")


def test_off_then_on_reincludes():
    """Regular author: included, OFF cuts, ON brings back inclusion."""
    print("\n=== Testing OFF then ON same day ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    messages = [
        create_test_message(
            "Morning work done", "edward@example.com", "Edward Carey", base_date
        ),
        create_test_message(
            "(OFF)", "edward@example.com", "Edward Carey", base_date + timedelta(hours=1)
        ),
        create_test_message(
            "Private chat only", "edward@example.com", "Edward Carey", base_date + timedelta(hours=2)
        ),
        create_test_message(
            "(ON) End of day photos and note", "edward@example.com", "Edward Carey", base_date + timedelta(hours=3)
        ),
    ]

    filtered = apply_on_off_filtering(messages)
    print(f"   Filtered count: {len(filtered)} (expected 2)")
    texts = [m["text"] for m in filtered]
    print(f"   Kept texts: {texts}")

    success = len(filtered) == 2
    success = success and texts[0] == "Morning work done"
    success = success and "End of day photos and note" in texts[1]

    print(f"   {'✅' if success else '❌'} OFF then ON reincludes")
    return success


def test_toggle_multiple_times():
    """Several OFF/ON switches in one day."""
    print("\n=== Testing multiple OFF/ON toggles ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 8, 0, 0, tzinfo=paris_tz)

    messages = [
        create_test_message("A", "edward@example.com", "Edward Carey", base_date),
        create_test_message("(OFF)", "edward@example.com", "Edward Carey", base_date + timedelta(hours=1)),
        create_test_message("B", "edward@example.com", "Edward Carey", base_date + timedelta(hours=2)),
        create_test_message("(ON) C", "edward@example.com", "Edward Carey", base_date + timedelta(hours=3)),
        create_test_message("(OFF) D", "edward@example.com", "Edward Carey", base_date + timedelta(hours=4)),
        create_test_message("(ON) E", "edward@example.com", "Edward Carey", base_date + timedelta(hours=5)),
    ]

    filtered = apply_on_off_filtering(messages)
    texts = [m["text"].strip() for m in filtered]
    print(f"   Kept: {texts}")
    # A, C, E only
    success = texts == ["A", "C", "E"]
    print(f"   {'✅' if success else '❌'} Multiple toggles")
    return success


def test_office_default_off_until_on():
    """Office team: excluded by default; (ON) includes content."""
    print("\n=== Testing office default OFF until ON ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=paris_tz)

    messages = [
        create_test_message(
            "Note admin hors périmètre terrain",
            "salome@example.com", "Salomé Cremona",
            base_date,
        ),
        create_test_message(
            "(ON) Visible for report",
            "salome@example.com", "Salomé Cremona",
            base_date + timedelta(hours=1),
        ),
        create_test_message(
            "(OFF) Stop again",
            "salome@example.com", "Salomé Cremona",
            base_date + timedelta(hours=2),
        ),
        create_test_message(
            "Hidden after OFF",
            "salome@example.com", "Salomé Cremona",
            base_date + timedelta(hours=3),
        ),
    ]

    filtered = apply_on_off_filtering(messages)
    texts = [m["text"].strip() for m in filtered]
    print(f"   Kept: {texts}")
    success = len(filtered) == 1 and texts[0] == "Visible for report"
    print(f"   {'✅' if success else '❌'} Office ON/OFF")
    return success


def test_day_reset_default_state():
    """New Paris day resets default (ON for gardener)."""
    print("\n=== Testing day reset for ON/OFF defaults ===")

    paris_tz = pytz.timezone('Europe/Paris')
    day1 = datetime(2025, 1, 15, 22, 0, 0, tzinfo=paris_tz)
    day2 = datetime(2025, 1, 16, 9, 0, 0, tzinfo=paris_tz)

    messages = [
        create_test_message("(OFF)", "edward@example.com", "Edward Carey", day1),
        create_test_message(
            "Next day included again",
            "edward@example.com", "Edward Carey",
            day2,
        ),
    ]

    filtered = apply_on_off_filtering(messages)
    texts = [m["text"].strip() for m in filtered]
    success = len(filtered) == 1 and texts[0] == "Next day included again"
    print(f"   Kept: {texts} — {'✅' if success else '❌'}")
    return success


def test_on_french_pronoun_not_a_marker():
    """Bare French 'on' must not toggle when state is OFF (ON caveat)."""
    print("\n=== Testing ON: French pronoun 'on' ignored ===")
    out, st = process_message_text_with_toggles("on a taillé la haie", "off")
    success = out == "" and st == "off"
    print(f"   state=off + 'on a taillé…' → out={out!r} state={st!r} {'✅' if success else '❌'}")
    assert success
    out2, st2 = process_message_text_with_toggles("(on) Synthèse pour le rapport", "off")
    assert out2 == "Synthèse pour le rapport" and st2 == "on"
    print("   (on) … still toggles from OFF → ON ✅")
    return True


def test_process_message_text_both_markers():
    """OFF then ON in same message restores tail."""
    print("\n=== Testing OFF then ON in same message ===")

    out, st = process_message_text_with_toggles("before (OFF) mid (ON) after", "on")
    print(f"   out={out!r} state={st}")
    success = "before" in out and "after" in out and st == "on"
    print(f"   {'✅' if success else '❌'}")
    return success


def test_sample_base_off_on_excludes_only_middle():
    """
    Sample day for one gardener: public base → (OFF) → private block → (on) recap.
    Asserts only the OFF window is dropped; first and last public blocks stay.
    """
    print("\n=== Sample: base message → OFF → private → ON (exclude middle only) ===")

    paris_tz = pytz.timezone("Europe/Paris")
    base_date = datetime(2025, 3, 10, 8, 30, 0, tzinfo=paris_tz)

    public_morning = "Rapport : taille haie faite ce matin."
    private_chat = "Discussion perso avec le client — hors rapport"
    public_evening = "Fin de journée : haie terminée, déchets évacués."

    messages = [
        create_test_message(
            public_morning,
            "jardin@example.com",
            "Jean Dupont",
            base_date,
        ),
        create_test_message(
            "(OFF)",
            "jardin@example.com",
            "Jean Dupont",
            base_date + timedelta(hours=1),
        ),
        create_test_message(
            private_chat,
            "jardin@example.com",
            "Jean Dupont",
            base_date + timedelta(hours=2),
        ),
        create_test_message(
            f"(on) {public_evening}",
            "jardin@example.com",
            "Jean Dupont",
            base_date + timedelta(hours=7),
        ),
    ]

    filtered = apply_on_off_filtering(messages)
    kept = [m["text"].strip() for m in filtered]

    print("   Timeline (same author, same Paris day):")
    print("     ① Intervention publique")
    print("     ② (OFF) → zone privée")
    print("     ③ Texte privé (hors rapport)")
    print("     ④ (on) … → retour public (casse flexible)")
    print(f"   Messages conservés ({len(kept)}): {kept!r}")

    assert len(kept) == 2, f"attendu 2 messages conservés, obtenu {len(kept)}: {kept!r}"
    assert kept[0] == public_morning, f"premier bloc: {kept[0]!r}"
    assert kept[1] == public_evening, f"second bloc (après ON): {kept[1]!r}"

    blob = "\n".join(kept)
    assert private_chat not in blob
    assert "Discussion perso" not in blob

    interventions = group_messages_by_intervention(filtered)
    assert len(interventions) == 1, "même jour + même auteur → une intervention"
    all_text = interventions[0].get("all_text", "")
    assert public_morning in all_text
    assert public_evening in all_text
    assert private_chat not in all_text

    print("   ✅ Seule la section entre OFF et ON est exclue du filtre")
    return True


def test_sample_split_at_off_then_on_new_message():
    """
    Première phrase publique avant (OFF) sur la même ligne ; messages suivants privés ;
    puis (ON) sur un nouveau message. Vérifie que seul le milieu disparaît.
    """
    print("\n=== Sample: texte avant (OFF) sur ligne 1, puis ON sur message suivant ===")

    paris_tz = pytz.timezone("Europe/Paris")
    base_date = datetime(2025, 3, 11, 9, 0, 0, tzinfo=paris_tz)

    kept_prefix = "Côté client : haie réduite."
    leaked_secret = "prix et négociation internes"
    middle_only = "Suite discussion interne budget"
    kept_suffix = "Côté client : finitions et nettoyage OK."

    messages = [
        create_test_message(
            f"{kept_prefix} (OFF) {leaked_secret}",
            "marie@example.com",
            "Marie Martin",
            base_date,
        ),
        create_test_message(
            middle_only,
            "marie@example.com",
            "Marie Martin",
            base_date + timedelta(minutes=30),
        ),
        create_test_message(
            f"(ON) {kept_suffix}",
            "marie@example.com",
            "Marie Martin",
            base_date + timedelta(hours=6),
            [{"contentType": "image/jpeg", "name": "finition.jpg"}],
        ),
    ]

    filtered = apply_on_off_filtering(messages)
    kept_texts = [m["text"].strip() for m in filtered]

    print(f"   Conservés ({len(kept_texts)}): {kept_texts!r}")

    assert len(kept_texts) == 2
    assert kept_texts[0] == kept_prefix
    assert kept_texts[1] == kept_suffix
    assert any(
        (a.get("contentType") or "").lower().startswith("image/")
        for a in (filtered[1].get("attachments") or [])
    ), "la photo du message ON doit rester attachée au message conservé"

    joined = "\n".join(kept_texts)
    assert leaked_secret not in joined
    assert middle_only not in joined

    interventions = group_messages_by_intervention(filtered)
    assert len(interventions) == 1
    all_text = interventions[0].get("all_text", "")
    assert kept_prefix in all_text
    assert kept_suffix in all_text
    assert leaked_secret not in all_text
    assert middle_only not in all_text

    print("   ✅ Milieu exclus ; préfixe avant OFF + bloc après ON (avec image) conservés")
    return True


def test_same_day_grouping():
    """Test same-day + same-author grouping with interrupted messages."""
    print("\n=== Testing Same-Day Grouping (with interruptions) ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create messages from same author on same day at different times
    # with another author's message in between
    messages = [
        create_test_message(
            "Message at 9am", "edward@example.com", "Edward Carey",
            base_date
        ),
        create_test_message(
            "Nicolas message", "nicolas@example.com", "Nicolas Dupont",
            base_date + timedelta(hours=1)
        ),
        create_test_message(
            "Message at 2pm", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=5)
        ),
        create_test_message(
            "Message at 5pm", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=8)
        ),
        # Same author, next day
        create_test_message(
            "Edward next day", "edward@example.com", "Edward Carey",
            base_date + timedelta(days=1)
        ),
    ]

    interventions = group_messages_by_intervention(messages)

    print(f"Total messages: {len(messages)}")
    print(f"Grouped into {len(interventions)} interventions (expected 3)")

    for i, intervention in enumerate(interventions):
        print(f"  Intervention {i+1}: {intervention['author_name']} - {len(intervention['messages'])} messages")
        for j, msg in enumerate(intervention['messages']):
            msg_time = extract_date_from_message(msg)
            print(f"    Message {j+1}: {msg_time.strftime('%H:%M') if msg_time else 'unknown'} - '{msg.get('text', '')[:50]}'")

    # Should have 3 interventions:
    # 1. Edward (all 3 messages on day 1: 9am, 2pm, 5pm) - merged together despite Nicolas's interruption
    # 2. Nicolas (1 message on day 1)
    # 3. Edward (1 message on day 2)
    success = len(interventions) == 3
    if success:
        # Verify Edward's day 1 intervention has all 3 messages
        edward_day1 = None
        for intervention in interventions:
            if (intervention['author_name'] == 'Edward Carey' and
                intervention['intervention_day'] == base_date.date()):
                edward_day1 = intervention
                break
        if edward_day1:
            success = len(edward_day1['messages']) == 3
            print(f"  ✅ Edward's day 1 intervention correctly has 3 messages")
        else:
            success = False
            print(f"  ❌ Could not find Edward's day 1 intervention")

    status = "✅" if success else "❌"
    print(f"{status} Same-day grouping test (with interruptions)")

def test_off_rule_filtering():
    """Test OFF rule filtering across messages."""
    print("\n=== Testing OFF Rule Filtering ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create messages with OFF markers
    messages = [
        create_test_message(
            "First message is fine", "edward@example.com", "Edward Carey",
            base_date
        ),
        create_test_message(
            "Second message also fine", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=1)
        ),
        create_test_message(
            "This message has (OFF) in it and more text after",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=2)
        ),
        create_test_message(
            "This should be excluded", "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=3)
        ),
        # Different author, same day - should not be affected
        create_test_message(
            "Nicolas message", "nicolas@example.com", "Nicolas Dupont",
            base_date + timedelta(hours=2, minutes=30)
        ),
    ]

    filtered = apply_on_off_filtering(messages)

    print(f"Original messages: {len(messages)}")
    print(f"After filtering: {len(filtered)} (expected 4)")

    for msg in filtered:
        print(f"  - {msg['author']['name']}: '{msg['text'][:50]}...'")

    # Should have 4 messages:
    # 1. Edward's first message
    # 2. Edward's second message
    # 3. Edward's third message (split at OFF to keep only "This message has")
    # 4. Nicolas's message (not affected)
    # Edward's 4th message should be excluded
    expected_count = 4
    success = len(filtered) == expected_count
    status = "✅" if success else "❌"
    print(f"{status} OFF rule filtering test")

def test_full_pipeline():
    """Test the full pipeline integration."""
    print("\n=== Testing Full Pipeline Integration ===")

    paris_tz = pytz.timezone('Europe/Paris')
    base_date = datetime(2025, 1, 15, 9, 0, 0, tzinfo=paris_tz)

    # Create realistic test messages
    messages = [
        create_test_message(
            "Taille effectuée le 15/01",
            "edward@example.com", "Edward Carey",
            base_date,
            [{'contentType': 'image/jpeg', 'name': 'before.jpg'}]
        ),
        create_test_message(
            "Avant",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(minutes=30),
            [
                {'contentType': 'image/jpeg', 'name': 'avant1.jpg'},
                {'contentType': 'image/jpeg', 'name': 'avant2.jpg'}
            ]
        ),
        create_test_message(
            "Après",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=1),
            [
                {'contentType': 'image/jpeg', 'name': 'apres1.jpg'}
            ]
        ),
        create_test_message(
            "Tout est terminé (OFF) informations privées",
            "edward@example.com", "Edward Carey",
            base_date + timedelta(hours=2)
        ),
    ]

    # Apply full pipeline
    filtered = apply_on_off_filtering(messages)
    interventions = group_messages_by_intervention(filtered)

    print(f"Original messages: {len(messages)}")
    print(f"After OFF filtering: {len(filtered)}")
    print(f"Interventions: {len(interventions)}")

    if interventions:
        intervention = interventions[0]
        print(f"\nIntervention details:")
        print(f"  Author: {intervention['author_name']}")
        print(f"  Messages: {len(intervention['messages'])}")
        print(f"  Has AVANT/APRÈS: {intervention.get('has_avant_apres', False)}")
        print(f"  Intervention date: {intervention.get('intervention_date')}")
        print(f"  Date source: {intervention.get('date_source')}")

        if intervention.get('has_avant_apres'):
            print(f"  Regular images: {len(intervention.get('regular_images', []))}")
            print(f"  AVANT images: {len(intervention.get('avant_images', []))}")
            print(f"  APRÈS images: {len(intervention.get('apres_images', []))}")

    success = (len(interventions) == 1 and
              interventions[0].get('has_avant_apres') == True and
              interventions[0].get('date_source') == 'extracted')

    status = "✅" if success else "❌"
    print(f"\n{status} Full pipeline test")


def test_office_display_name_aliases():
    """Google may return alternate spellings; all must match OFFICE_TEAM_MEMBERS."""
    assert config.is_office_team_display_name("Vincent Da Silva")
    assert config.is_office_team_display_name("vincent da silva")
    assert config.is_office_team_display_name("Vincent Dasilva")
    assert config.is_office_team_display_name("  Diane   De   Magnitot ")
    assert config.is_office_team_display_name("Salome Cremona")
    assert config.is_office_team_display_name("Salomé Cremona")
    assert not config.is_office_team_display_name("Random Gardener")
    print("   ✅ Office display name aliases / normalization")


def test_office_followup_included_after_on_without_second_marker():
    """Same Paris day: after (ON), a later message with no marker stays included until (OFF)."""
    paris_tz = pytz.timezone("Europe/Paris")
    base_date = datetime(2025, 1, 15, 10, 0, 0, tzinfo=paris_tz)
    messages = [
        create_test_message(
            "Hidden admin",
            "vincent@example.com",
            "Vincent Da Silva",
            base_date,
        ),
        create_test_message(
            "(ON) First public",
            "vincent@example.com",
            "Vincent Da Silva",
            base_date + timedelta(hours=1),
        ),
        create_test_message(
            "Second public, sans marqueur dans ce message",
            "vincent@example.com",
            "Vincent Da Silva",
            base_date + timedelta(hours=2),
        ),
        create_test_message(
            "(OFF)",
            "vincent@example.com",
            "Vincent Da Silva",
            base_date + timedelta(hours=3),
        ),
        create_test_message(
            "Hidden again",
            "vincent@example.com",
            "Vincent Da Silva",
            base_date + timedelta(hours=4),
        ),
    ]
    filtered = apply_on_off_filtering(messages)
    texts = [m["text"].strip() for m in filtered]
    assert texts == ["First public", "Second public, sans marqueur dans ce message"], texts
    print("   ✅ Office follow-up after ON without second marker")


def test_on_off_excludes_message_without_create_time():
    """Messages with no parseable date must not bypass the filter (previously they did)."""
    paris_tz = pytz.timezone("Europe/Paris")
    ok_msg = create_test_message(
        "ok",
        "a@example.com",
        "Alice",
        datetime(2025, 2, 1, 12, 0, 0, tzinfo=paris_tz),
    )
    bad = {
        "text": "should not leak",
        "author": {"email": "b@example.com", "name": "Bob"},
        "createTime": "",
        "attachments": [],
    }
    filtered = apply_on_off_filtering([bad, ok_msg])
    assert len(filtered) == 1
    assert filtered[0]["author"]["email"] == "a@example.com"
    print("   ✅ No createTime → excluded from filter output")


def test_on_off_name_only_author_key_still_applies_office_rules():
    """No email: stable name-based key still defaults office to OFF until ON."""
    paris_tz = pytz.timezone("Europe/Paris")
    base_date = datetime(2025, 3, 1, 9, 0, 0, tzinfo=paris_tz)
    messages = [
        {
            "text": "admin note",
            "author": {"email": "", "name": "Luana Debusschere"},
            "createTime": base_date.isoformat(),
            "attachments": [],
        },
        {
            "text": "(ON) visible",
            "author": {"email": "", "name": "Luana Debusschere"},
            "createTime": (base_date + timedelta(hours=1)).isoformat(),
            "attachments": [],
        },
    ]
    filtered = apply_on_off_filtering(messages)
    assert len(filtered) == 1
    assert filtered[0]["text"].strip() == "visible"
    print("   ✅ Name-only author key + office OFF until ON")


def test_trace_out_matches_message_count():
    paris_tz = pytz.timezone("Europe/Paris")
    base_date = datetime(2025, 4, 1, 8, 0, 0, tzinfo=paris_tz)
    messages = [
        create_test_message("a", "e@e.com", "Edward Carey", base_date),
        create_test_message("b", "e@e.com", "Edward Carey", base_date + timedelta(hours=1)),
    ]
    trace: List[Dict[str, Any]] = []
    apply_on_off_filtering(messages, trace_out=trace)
    assert len(trace) == 2
    assert trace[0]["included"] and trace[1]["included"]
    assert not trace[0]["is_office_display_name"]
    print("   ✅ trace_out populated per message")


def main():
    """Run all tests."""
    print("=" * 60)
    print("TESTING NEW INTERVENTION GROUPING FEATURES")
    print("=" * 60)

    try:
        assert apply_off_rule_filtering is apply_on_off_filtering, "Backward-compat alias missing"

        test_off_rule_splitting()
        test_on_rule_splitting()
        test_date_extraction()
        test_avant_apres_detection()
        if not test_combined_avant_apres_marker_detection():
            raise AssertionError("test_combined_avant_apres_marker_detection failed")
        if not test_composite_split_image_halves():
            raise AssertionError("test_composite_split_image_halves failed")
        if not test_group_intervention_split_flag_for_composite():
            raise AssertionError("test_group_intervention_split_flag_for_composite failed")
        test_same_day_grouping()
        test_off_rule_filtering()
        test_off_then_on_reincludes()
        test_toggle_multiple_times()
        test_office_default_off_until_on()
        test_office_display_name_aliases()
        test_office_followup_included_after_on_without_second_marker()
        test_on_off_excludes_message_without_create_time()
        test_on_off_name_only_author_key_still_applies_office_rules()
        test_trace_out_matches_message_count()
        test_day_reset_default_state()
        test_process_message_text_both_markers()
        test_on_french_pronoun_not_a_marker()
        test_sample_base_off_on_excludes_only_middle()
        test_sample_split_at_off_then_on_new_message()
        test_full_pipeline()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
