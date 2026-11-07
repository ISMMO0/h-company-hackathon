from brain import knowledge
from brain.agent import not_target


def test_site_of_browser_tab():
    assert knowledge.site_of("Google Chrome", "Untitled spreadsheet - Google Sheets") == "Google Sheets"
    assert knowledge.site_of("Google Chrome", "Eiffel Tower - Wikipedia") == "Wikipedia"
    assert knowledge.site_of("rekordbox", "rekordbox 7") == "rekordbox"
    assert knowledge.site_of("Google Chrome", "Sheet - Google Sheets - Google Chrome") == "Google Sheets"
    assert knowledge.site_of("Google Chrome", "404 - Google Chrome") == "Google Chrome"


def test_never_act_in_our_own_tools():
    assert not_target("Claude", "Chat session")
    assert not_target("Google Chrome", "Shadow Cursor")
    assert not not_target("Google Chrome", "Untitled spreadsheet - Google Sheets")
