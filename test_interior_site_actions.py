#!/usr/bin/env python3
"""
Tests for interior site detection and default actions (INT / intérieur).
"""

from src.notion.page_builder import ReportPageBuilder


def test_is_interior_site():
    """Test that interior site is detected for (INT), (int), INT, and intérieur."""
    assert ReportPageBuilder._is_interior_site("Site (INT)") is True
    assert ReportPageBuilder._is_interior_site("Site (int)") is True
    assert ReportPageBuilder._is_interior_site("Site INT") is True
    assert ReportPageBuilder._is_interior_site("Client INT - 203") is True
    assert ReportPageBuilder._is_interior_site("Intérieur Paris") is True
    assert ReportPageBuilder._is_interior_site("Site intérieur") is True
    # Word boundary: "intervention" should not match
    assert ReportPageBuilder._is_interior_site("Site intervention") is False
    assert ReportPageBuilder._is_interior_site("Extérieur Lyon") is False
    assert ReportPageBuilder._is_interior_site("Site normal") is False
    assert ReportPageBuilder._is_interior_site(None) is False
    assert ReportPageBuilder._is_interior_site("") is False


def test_interior_default_actions_prepended():
    """Test that for interior sites, default actions are prepended and existing content is kept."""
    builder = ReportPageBuilder()
    # Mock: we only test the logic that runs when _is_interior_site is True.
    # Simulate extracted actions (what AI would return)
    actions_list = ["Taille des arbustes", "Désherbage"]
    client_name = "Site (INT)"
    if builder._is_interior_site(client_name):
        existing_lower = {a.strip().lower() for a in actions_list}
        to_prepend = [a for a in builder.DEFAULT_INTERIOR_ACTIONS if a.strip().lower() not in existing_lower]
        actions_list = to_prepend + actions_list
    # Should have: Arrosage, Dépoussiérage, Retrait..., then Taille, Désherbage
    assert "Arrosage" in actions_list
    assert "Dépoussiérage" in actions_list
    assert "Retrait des feuilles mortes/abîmées" in actions_list
    assert "Taille des arbustes" in actions_list
    assert "Désherbage" in actions_list
    assert actions_list[:3] == builder.DEFAULT_INTERIOR_ACTIONS
    assert len(actions_list) == 5


def test_interior_no_duplicate_if_extracted():
    """Test that if AI already extracted 'Arrosage', we don't duplicate it."""
    builder = ReportPageBuilder()
    actions_list = ["Arrosage", "Nettoyage"]
    client_name = "Client INT"
    if builder._is_interior_site(client_name):
        existing_lower = {a.strip().lower() for a in actions_list}
        to_prepend = [a for a in builder.DEFAULT_INTERIOR_ACTIONS if a.strip().lower() not in existing_lower]
        actions_list = to_prepend + actions_list
    # Arrosage already in list, so to_prepend should only have Dépoussiérage and Retrait
    assert actions_list.count("Arrosage") == 1
    assert "Dépoussiérage" in actions_list
    assert "Retrait des feuilles mortes/abîmées" in actions_list
    assert "Nettoyage" in actions_list
