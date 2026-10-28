"""Date fields provide a Chinese calendar and a usable native fallback."""

from html.parser import HTMLParser

import pytest


class DateControls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs = []
        self.buttons = []
        self.scripts = []
        self.dialogs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            self.inputs.append(attrs)
        if tag == "button" and "data-date-for" in attrs:
            self.buttons.append(attrs)
        if tag == "script":
            self.scripts.append(attrs.get("src", ""))
        if tag == "dialog":
            self.dialogs.append(attrs)


@pytest.mark.parametrize(("path", "fields", "input_type"), [
    ("/admin/courses", {"courseClosesAt", "codeExpiresAt"}, "datetime-local"),
    ("/admin/audit", {"fromDate", "toDate"}, "date"),
])
def test_date_fields_use_chinese_picker_and_keep_native_fallback(app, path, fields, input_type):
    page = DateControls()
    response = app.test_client().get(path)
    assert response.status_code == 200
    page.feed(response.get_data(as_text=True))
    inputs = {item.get("id"): item for item in page.inputs}
    assert all(inputs[field]["type"] == input_type and "hidden" not in inputs[field] for field in fields)
    assert {button.get("data-date-for") for button in page.buttons} == fields
    assert all(button.get("type") == "button" and button.get("aria-haspopup") == "dialog" and "hidden" in button
               for button in page.buttons)
    assert any(item.get("id") == "datePickerDialog" for item in page.dialogs)
    assert any(src.endswith("/js/date-picker.js") for src in page.scripts)
