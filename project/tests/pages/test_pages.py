"""页面路由：浏览器拿 HTML，`/api` 前缀拿 JSON。"""

import re

import pytest


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


@pytest.mark.parametrize("path", ["/", "/student"])
def test_student_entry_shows_code_form_and_staff_login(app, path):
    response = app.test_client().get(path)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert 'id="codeForm"' in body
    assert "进入评教" in body
    assert re.search(
        r'<button\b[^>]*type="submit"[^>]*>\s*继续\s*</button>\s*'
        r'<a\b[^>]*href="/login"[^>]*>\s*教职工登录\s*</a>', body
    )
    assert "js/pages/entry.js" not in body


def test_staff_workspace_still_hands_off_to_the_browser(app):
    response = app.test_client().get("/workspace")
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    body = response.get_data(as_text=True)
    assert "正在进入" in body
    assert "js/pages/entry.js" in body


def test_login_page_links_back_to_student_entry(app):
    body = app.test_client().get("/login").get_data(as_text=True)
    assert re.search(
        r'<button\b[^>]*type="submit"[^>]*>\s*登录\s*</button>\s*'
        r'<a\b[^>]*href="/"[^>]*>\s*返回学生评教\s*</a>', body
    )


def test_board_renders_its_blocks(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "联合均分" in body
    assert "评分分布" in body
    assert "开放题高频词" in body


def test_board_promises_that_text_and_scores_stay_unlinked(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "不关联" in body
    assert "原文不进接口" in body


def test_code_page_states_the_three_failures(app):
    body = app.test_client().get("/student").get_data(as_text=True)
    assert "进入评教" in body
    assert "已经用过了" in body
    assert "没有这个码" in body
    assert "窗口已关闭" in body


def test_evaluate_page_renders_scale_and_receipt(app):
    body = app.test_client().get("/student/evaluate").get_data(as_text=True)
    assert "请给这门课打分" in body
    assert "开放题" in body
    assert "500" in body
    assert "不能再改" in body


def test_config_page_names_three_parameters_and_their_scope(app):
    body = app.test_client().get("/admin/config").get_data(as_text=True)
    assert "每次发布 ε" in body
    assert "出数门槛 k" in body
    assert "每门课预算总量" in body


def test_audit_page_is_read_only(app):
    body = app.test_client().get("/admin/audit").get_data(as_text=True)
    assert "查询留痕" in body
    assert "操作者" in body
    assert "消耗 ε" in body
    assert "只增不改" in body
    # 「没有删除入口」这句话本身含「删除」，所以断的是控件，不是字面
    assert not re.search(r"<(?:button|a)\b[^>]*>\s*删除", body)
