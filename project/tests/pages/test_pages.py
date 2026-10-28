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
    assert "<h1>教职工登录</h1>" in body
    assert "TACES" in body
    assert 'id="loginForm"' in body
    assert 'name="username"' in body
    assert 'name="password"' in body


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
    assert 'id="entryRetry"' in body
    assert 'id="entryLogout"' in body
    assert "page-workspace" in body


def test_login_page_links_back_to_student_entry(app):
    body = app.test_client().get("/login").get_data(as_text=True)
    assert re.search(
        r'<button\b[^>]*type="submit"[^>]*>\s*登录\s*</button>\s*'
        r'<a\b[^>]*href="/"[^>]*>\s*返回学生评教\s*</a>', body
    )


@pytest.mark.parametrize("path", ["/", "/student", "/student/evaluate", "/login"])
def test_public_pages_display_taces_footer(app, path):
    body = app.test_client().get(path).get_data(as_text=True)
    assert body.count("© 2026 TACES. All rights reserved.") == 1


def test_board_renders_its_blocks(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "联合均分" in body
    assert "评分分布" in body
    assert "开放题高频词" in body


def test_board_explains_that_comment_text_is_not_shown_to_teachers(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert "教师页面和导出文件不展示评语原文" in body
    assert "分数和文字不关联" not in body


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
    assert "评分与评语保存在同一份匿名评价中" in body
    assert "请勿填写姓名、学号等个人信息" in body
    assert "分数和文字不关联" not in body
    assert "5 秒后自动返回首页" in body
    assert re.search(r'<a\b[^>]*href="/"[^>]*>\s*返回首页\s*</a>', body)


def test_config_page_names_three_parameters_and_their_scope(app):
    body = app.test_client().get("/admin/config").get_data(as_text=True)
    assert "每次发布 ε" in body
    assert "出数门槛 k" in body
    assert "每门课预算总量" in body
    assert "有效评价少于门槛时不发布新的统计结果" in body
    assert "每门课程用于发布统计的 ε 总量" in body


def test_admin_account_page_provides_management_form_and_list(app):
    response = app.test_client().get("/admin/accounts")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "账号管理" in body
    assert 'id="accountForm"' in body
    assert re.search(r'<dialog\b[^>]*id="accountDialog"', body)
    assert 'id="accountCreate"' in body
    assert 'id="accountRows"' in body
    assert 'js/pages/accounts.js' in body


def test_audit_page_is_read_only(app):
    body = app.test_client().get("/admin/audit").get_data(as_text=True)
    assert "查询留痕" in body
    assert "操作者" in body
    assert "消耗 ε" in body
    # 工作区账号区允许用户修改自己的密码；审计正文仍不可编辑。
    audit_content = body.split('<main class="sheet"', 1)[1].split('</main>', 1)[0]
    assert not re.search(r"<(?:button|a)\b[^>]*>\s*(?:编辑|修改|删除)", audit_content)


def test_admin_course_page_provides_list_and_teacher_assignment(app):
    response = app.test_client().get("/admin/courses")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "课程管理" in body
    assert 'id="courseRows"' in body
    assert 'id="courseTeacher"' in body
    assert re.search(r'<dialog\b[^>]*id="courseDialog"', body)
    assert 'js/pages/courses.js' in body


def test_board_offers_both_snapshot_export_formats(app):
    body = app.test_client().get("/teacher/SE201-03").get_data(as_text=True)
    assert 'id="exportPdf"' in body
    assert 'id="exportCsv"' in body
    assert 'id="exportError"' in body


def test_staff_password_page_and_workspace_link(app):
    client = app.test_client()
    response = client.get("/account/password")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert 'id="passwordForm"' in body
    assert 'id="currentPassword"' in body
    assert 'id="newPassword"' in body
    assert 'id="confirmPassword"' in body
    assert 'href="/account/password"' in client.get("/workspace").get_data(as_text=True)
    assert 'href="/account/password"' in client.get("/admin/courses").get_data(as_text=True)


def test_course_page_exposes_deadline_dimensions_and_code_issuance(app):
    body = app.test_client().get("/admin/courses").get_data(as_text=True)
    for control in ("courseClosesAt", "courseUseCustom", "courseDimensionRows",
                    "codeDialog", "codeForm", "codeCount", "codeValues", "codeCopy", "codeDownload"):
        assert f'id="{control}"' in body


def test_snapshot_export_page_does_not_shadow_course_named_exports(app):
    client = app.test_client()
    response = client.get("/teacher/exports/history")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for control in ("exportCourse", "exportPublication", "exportLatestPdf", "exportLatestCsv"):
        assert f'id="{control}"' in body
    assert "js/pages/exports.js" in body
    assert 'id="board"' in client.get("/teacher/exports").get_data(as_text=True)
