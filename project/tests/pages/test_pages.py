"""页面路由：浏览器拿 HTML，`/api` 前缀拿 JSON。"""


def test_unknown_page_returns_html_for_browser(app):
    response = app.test_client().get("/not-a-route")
    assert response.status_code == 404
    assert response.mimetype == "text/html"
    assert "没有这个页面" in response.get_data(as_text=True)


def test_unknown_api_route_still_returns_json(app):
    response = app.test_client().get("/api/not-a-route")
    assert response.status_code == 404
    assert response.mimetype == "application/json"
    assert response.json["error"]["code"] == "NOT_FOUND"


def test_login_page_is_html_with_its_copy(app):
    response = app.test_client().get("/login")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "<h1" in body
    assert "TACES" in body
    assert "学生不用登录" in body
