import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

import taces.data.database as storage
from taces.data.database import Database, StorageError
from tests.workflow_support import staff, course_body, create_course, login_role


def test_admin_can_create_and_reuse_terms_before_creating_courses(staff):
    client, headers = staff['client'], staff['headers']
    assert client.get('/api/admin/terms').json['data']['terms'] == []
    for year, season, label in [(2026, '秋', '2026秋'), (2026, '春', '2026春'), (2027, '春', '2027春')]:
        response = client.post('/api/admin/terms', json={'year': year, 'season': season}, headers=headers)
        assert response.status_code == 201
        assert response.json['data'] == {'term': label, 'created': True}
    duplicate = client.post('/api/admin/terms', json={'year': 2026, 'season': '秋'}, headers=headers)
    assert duplicate.status_code == 200
    assert duplicate.json['data'] == {'term': '2026秋', 'created': False}
    assert client.get('/api/admin/terms').json['data']['terms'] == ['2027春', '2026秋', '2026春']
    assert client.get('/api/admin/courses').json['data']['courses'] == []
    audit = client.get('/api/admin/audit').json['data']['entries']
    assert sum(item['action'] == '创建学期' and item['target'] == '2026秋' for item in audit) == 1


@pytest.mark.parametrize('year,season', [
    (0, '春'), (10000, '春'), (True, '春'), ('2026', '春'), (2026.5, '春'),
    (2026, ''), (2026, '夏'), (2026, '秋季'), (2026, None), (2026, ['春']),
])
def test_new_term_rejects_invalid_year_or_season(staff, year, season):
    response = staff['client'].post('/api/admin/terms', json={'year': year, 'season': season}, headers=staff['headers'])
    assert response.status_code == 400
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == []


@pytest.mark.parametrize('value', ['', '秋', '2026 秋', '2026秋季', '2026夏', '0000春', '２０２６春', None, [], True])
@pytest.mark.parametrize('method', ['post', 'patch'])
def test_course_rejects_noncanonical_new_terms_without_partial_writes(staff, method, value):
    if method == 'patch':
        original = create_course(staff)
        path, body = '/api/admin/courses/c1', {'term': value}
    else:
        original = None
        path, body = '/api/admin/courses', {**course_body(staff), 'term': value}
    response = getattr(staff['client'], method)(path, json=body, headers=staff['headers'])
    assert response.status_code == 400
    courses = staff['client'].get('/api/admin/courses').json['data']['courses']
    assert len(courses) == (1 if original else 0)
    if original:
        assert courses[0]['term'] == original['term']


def test_valid_course_term_is_registered_and_legacy_term_can_stay_until_edited(staff):
    create_course(staff, term='2028春')
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == ['2028春']
    with staff['db'].transaction() as con:
        con.execute("UPDATE main.course SET term='旧版学期' WHERE course_id='c1'")
    updated = staff['client'].patch('/api/admin/courses/c1', json={'name': '课程新名称'}, headers=staff['headers'])
    assert updated.status_code == 200 and updated.json['data']['course']['term'] == '旧版学期'
    updated = staff['client'].patch('/api/admin/courses/c1',
                                    json={'name': '再次修改', 'term': '旧版学期'}, headers=staff['headers'])
    assert updated.status_code == 200 and updated.json['data']['course']['term'] == '旧版学期'
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == ['2028春']
    updated = staff['client'].patch('/api/admin/courses/c1', json={'term': '2029秋'}, headers=staff['headers'])
    assert updated.status_code == 200 and updated.json['data']['course']['term'] == '2029秋'
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == ['2029秋', '2028春']


def test_term_endpoints_require_admin_and_csrf(staff):
    assert staff['app'].test_client().get('/api/admin/terms').status_code == 401
    assert staff['client'].post('/api/admin/terms', json={'year': 2026, 'season': '春'}).status_code == 403
    for role in ('teacher', 'auditor'):
        client, headers = login_role(staff, role, role)
        assert client.get('/api/admin/terms').status_code == 403
        assert client.post('/api/admin/terms', json={'year': 2026, 'season': '春'}, headers=headers).status_code == 403


def test_term_creation_rolls_back_if_audit_write_fails(staff, monkeypatch):
    import taces.business.courses.service as module

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('injected audit failure')

    monkeypatch.setattr(module, 'write_audit', fail)
    response = staff['client'].post('/api/admin/terms', json={'year': 2026, 'season': '春'}, headers=staff['headers'])
    assert response.status_code == 503
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == []


def test_failed_course_creation_does_not_leave_a_new_term(staff):
    with staff['db'].transaction() as con:
        con.execute("CREATE TRIGGER main.fail_course BEFORE INSERT ON course BEGIN SELECT RAISE(ABORT, 'test'); END")
    response = staff['client'].post('/api/admin/courses', json={**course_body(staff), 'term': '2030秋'},
                                    headers=staff['headers'])
    assert response.status_code == 503
    assert staff['client'].get('/api/admin/terms').json['data']['terms'] == []
    with staff['db'].read_current() as con:
        assert con.execute("SELECT count(*) FROM main.audit_log WHERE action='term.create:2030秋'").fetchone()[0] == 0


def test_concurrent_creation_of_the_same_term_creates_one_entry_and_audit(staff):
    from taces.business.courses.service import CourseService

    barrier = Barrier(4)
    def create():
        barrier.wait(timeout=5)
        return CourseService(staff['db'], staff['auth']).create_term(staff['token'], {'year': 2026, 'season': '秋'})

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: create(), range(4)))
    assert sum(result['created'] for result in results) == 1
    assert all(result['term'] == '2026秋' for result in results)
    with staff['db'].read_current() as con:
        assert con.execute("SELECT count(*) FROM main.academic_term WHERE term='2026秋'").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM main.audit_log WHERE action='term.create:2026秋'").fetchone()[0] == 1


def legacy_v4(path):
    database = Database(path)
    with database._connect(create=True) as con:
        for filename in ('metadata.sql', 'identity.sql', 'evaluation.sql', 'auth.sql', 'workflow.sql', 'account_names.sql'):
            con.executescript((storage.SCHEMA_DIR / filename).read_text(encoding='utf-8'))
        for schema in ('main', 'identity', 'evaluation'):
            con.execute(f'PRAGMA {schema}.user_version=4')
        for course_id, term in [('a', '2026秋'), ('b', '2026秋'), ('c', '旧版学期'), ('d', '0000春')]:
            con.execute('INSERT INTO main.course VALUES (?, ?, ?, ?)', (course_id, '旧课程', 'teacher', term))
    return database


def test_v4_migration_preserves_legacy_terms_and_registers_only_canonical_ones(tmp_path):
    database = legacy_v4(tmp_path / 'v4')
    with pytest.raises(StorageError, match='upgrade'):
        database.initialize()
    database.upgrade()
    database.upgrade()
    with database.read_current() as con:
        assert [row[0] for row in con.execute('SELECT term FROM main.course ORDER BY course_id')] == [
            '2026秋', '2026秋', '旧版学期', '0000春']
        assert [row[0] for row in con.execute('SELECT term FROM main.academic_term')] == ['2026秋']
        assert [con.execute(f'PRAGMA {schema}.user_version').fetchone()[0]
                for schema in ('main', 'identity', 'evaluation')] == [5, 5, 5]


def test_failed_term_migration_rolls_back_table_and_version(tmp_path, monkeypatch):
    database = legacy_v4(tmp_path / 'v4')
    schema = tmp_path / 'schema'
    schema.mkdir()
    for source in storage.SCHEMA_DIR.glob('*.sql'):
        text = source.read_text(encoding='utf-8')
        if source.name == 'terms.sql':
            text += '\nINVALID SQL;\n'
        (schema / source.name).write_text(text, encoding='utf-8')
    monkeypatch.setattr(storage, 'SCHEMA_DIR', schema)
    with pytest.raises(sqlite3.OperationalError):
        database.upgrade()
    with database.read() as con:
        assert con.execute("SELECT name FROM main.sqlite_master WHERE name='academic_term'").fetchone() is None
        assert con.execute('SELECT count(*) FROM main.course').fetchone()[0] == 4
        assert [con.execute(f'PRAGMA {schema}.user_version').fetchone()[0]
                for schema in ('main', 'identity', 'evaluation')] == [4, 4, 4]
