from brain import knowledge
from brain.agent import not_target


def test_site_of_browser_tab():
    assert knowledge.site_of("Google Chrome", "Untitled spreadsheet - Google Sheets") == "Google Sheets"
    assert knowledge.site_of("Google Chrome", "Eiffel Tower - Wikipedia") == "Wikipedia"
    assert knowledge.site_of("rekordbox", "rekordbox 7") == "rekordbox"
    assert knowledge.site_of("Google Chrome", "Sheet - Google Sheets - Google Chrome") == "Google Sheets"
    assert knowledge.site_of("Google Chrome", "404 - Google Chrome") == "Google Chrome"
    assert knowledge.site_of("Google Chrome", "Me at the zoo - YouTube - Audio playing - Google Chrome") == "YouTube"


def test_never_act_in_our_own_tools():
    assert not_target("Claude", "Chat session")
    assert not_target("Google Chrome", "Shadow Cursor")
    assert not not_target("Google Chrome", "Untitled spreadsheet - Google Sheets")


def test_do_it_never_wanders_or_destroys():
    from brain.agent import risky
    assert risky("press", {"keys": "cmd+tab"}, "make a shopping list")
    assert risky("press", {"keys": "command+q"}, "anything")
    assert risky("click", {"element": "Delete button in the save dialog"}, "make a shopping list")
    assert risky("click", {"element": "Pages icon in the Dock"}, "make a shopping list")
    assert not risky("click", {"element": "Delete row button"}, "delete the second row")
    assert not risky("press", {"keys": "cmd+a"}, "anything")


def test_system_settings_guard():
    from brain.agent import system_blocked
    assert not system_blocked("System Settings", "Light option in Appearance", "Appearance")
    assert not system_blocked("System Settings", "Appearance in the sidebar", "Accessibility")
    assert system_blocked("System Settings", "Shadow Cursor toggle", "Accessibility")
    assert system_blocked("System Settings", "Privacy & Security in the sidebar", "Appearance")
    assert system_blocked("SecurityAgent", "Allow button", "")
