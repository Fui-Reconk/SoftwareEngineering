"""Every password field exposes an independently labelled visibility control."""

from html.parser import HTMLParser

import pytest


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.buttons = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "password":
            self.inputs.append(attrs)
        if tag == "button" and "data-password-toggle" in attrs:
            self.buttons.append(attrs)
        if tag == "script":
            self.scripts.append(attrs.get("src", ""))


@pytest.mark.parametrize(("path", "fields"), [
    ("/login", {"loginPassword"}),
    ("/account/password", {"currentPassword", "newPassword", "confirmPassword"}),
    ("/admin/accounts", {"accountPassword"}),
])
def test_each_password_input_has_a_masked_accessible_toggle(app, path, fields):
    page = Controls()
    page.feed(app.test_client().get(path).get_data(as_text=True))
    assert {item.get("id") for item in page.inputs} == fields
    assert {item.get("aria-controls") for item in page.buttons} == fields
    assert len(page.buttons) == len(fields)
    for button in page.buttons:
        assert button.get("type") == "button"
        assert button.get("aria-pressed") == "false"
        assert button.get("aria-label", "").startswith("显示")
    assert any(src.endswith("/js/password-toggle.js") for src in page.scripts)
