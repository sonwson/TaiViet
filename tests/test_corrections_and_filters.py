import json
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
import server
from scripts.migrate import build, load_sqlite, ROOT

class CorrectionsAndFiltersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.orig_backend = server.DB_BACKEND
        self.orig_pool = server.pg_pool
        self.original_path = server.DB_PATH

        server.DB_BACKEND = 'sqlite'
        server.pg_pool = None
        server.DB_PATH = Path(self.temp.name) / 'test.db'
        server.sessions.clear()
        server.limits.clear()
        server.login_failures.clear()
        server.login_lockouts.clear()

        records = json.loads((ROOT / 'data/taiviet_dictionary_dataset.json').read_text(encoding='utf-8'))[:5]
        load_sqlite(server.DB_PATH, build(records)[0])
        server.upgrade(server.DB_PATH, server.engine)
        server.accounts.initialize()
        self.client = TestClient(server.app)
        self.client.get('/api/session')

    def tearDown(self):
        self.client.close()
        server.DB_PATH = self.original_path
        server.DB_BACKEND = self.orig_backend
        server.pg_pool = self.orig_pool
        self.temp.cleanup()

    def consent(self, client=None):
        (client or self.client).get('/api/session')
        return {}

    def post(self, path, p, client=None):
        c = client or self.client
        return c.post('/api/' + path, json={**p, **self.consent(c)})

    def login(self):
        r = self.client.post('/api/admin/login', json={'token': server.ADMIN_TOKEN})
        self.assertEqual(r.status_code, 200)

    def test_sentence_correction_requires_all_fields(self):
        with server.database() as db:
            sid = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ', romanization='ka', status='approved'))

        r = self.post('sentence-corrections', {'sentence_id': sid, 'suggested_tai_text': 'ꪄ꫁ꪱ', 'suggested_romanization': ''})
        self.assertEqual(r.status_code, 422)

        r = self.post('sentence-corrections', {'sentence_id': sid, 'suggested_tai_text': 'ꪄ꫁ꪱ', 'suggested_romanization': 'khaa'})
        self.assertEqual(r.status_code, 422)

        r = self.post('sentence-corrections', {'sentence_id': sid, 'suggested_tai_text': 'ꪄ꫁ꪱ', 'suggested_romanization': 'khaa', 'suggested_meaning': '  '})
        self.assertEqual(r.status_code, 422)

    def test_user_sentence_correction_pending(self):
        with server.database() as db:
            sid = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ', romanization='ka', status='approved'))
            server.insert(db, 'translations', dict(sentence_id=sid, vietnamese_text='nghĩa cũ', status='approved'))

        r = self.post('sentence-corrections', {
            'sentence_id': sid,
            'suggested_tai_text': 'ꪄ꫁ꪱ',
            'suggested_romanization': 'khaa',
            'suggested_meaning': 'nghĩa mới đề xuất'
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'pending')

        with server.database() as db:
            sent = db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone()
            self.assertEqual(sent['tai_text_original'], 'ꪀꪱ')
            tr = db.execute('SELECT * FROM translations WHERE sentence_id=? AND status=? LIMIT 1', (sid, 'approved')).fetchone()
            self.assertEqual(tr['vietnamese_text'], 'nghĩa cũ')

            corr = db.execute('SELECT * FROM sentence_corrections WHERE sentence_id=?', (sid,)).fetchone()
            self.assertEqual(corr['suggested_tai_text'], 'ꪄ꫁ꪱ')
            self.assertEqual(corr['suggested_romanization'], 'khaa')
            self.assertEqual(corr['suggested_meaning'], 'nghĩa mới đề xuất')
            self.assertEqual(corr['status'], 'pending')

    def test_admin_sentence_correction_direct_overwrite(self):
        with server.database() as db:
            sid = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ', romanization='ka', status='approved'))
            server.insert(db, 'translations', dict(sentence_id=sid, vietnamese_text='nghĩa cũ', status='approved'))

        self.login()
        r = self.post('sentence-corrections', {
            'sentence_id': sid,
            'suggested_tai_text': 'ꪀꪱ_admin',
            'suggested_romanization': 'ka_admin',
            'suggested_meaning': 'nghĩa do admin sửa'
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'approved')

        with server.database() as db:
            sent = db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone()
            self.assertEqual(sent['tai_text_original'], 'ꪀꪱ_admin')
            self.assertEqual(sent['romanization'], 'ka_admin')
            tr = db.execute('SELECT * FROM translations WHERE sentence_id=? AND status=? LIMIT 1', (sid, 'approved')).fetchone()
            self.assertEqual(tr['vietnamese_text'], 'nghĩa do admin sửa')

    def test_admin_moderate_sentence_correction_overwrites(self):
        with server.database() as db:
            sid = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_pending', romanization='ka', status='approved'))
            cid = server.insert(db, 'sentence_corrections', dict(
                sentence_id=sid, suggested_tai_text='ꪄ꫁ꪱ_approved',
                suggested_romanization='khaa_approved', suggested_meaning='nghĩa sau duyệt',
                contributor_id='tester', status='pending'
            ))

        self.login()
        r = self.client.post('/api/admin/moderate', json={'table': 'sentence_corrections', 'id': cid, 'status': 'approved'})
        self.assertEqual(r.status_code, 200)

        with server.database() as db:
            sent = db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone()
            self.assertEqual(sent['tai_text_original'], 'ꪄ꫁ꪱ_approved')
            self.assertEqual(sent['romanization'], 'khaa_approved')
            tr = db.execute('SELECT * FROM translations WHERE sentence_id=? AND status=?', (sid, 'approved')).fetchone()
            self.assertEqual(tr['vietnamese_text'], 'nghĩa sau duyệt')

    def test_sentence_filtering_api(self):
        with server.database() as db:
            s_app = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_1', romanization='ka1', source_type='community', status='approved'))
            server.insert(db, 'translations', dict(sentence_id=s_app, vietnamese_text='nghĩa 1', status='approved'))

            s_pen = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_2', romanization='', source_type='dictionary', status='pending'))

        r = self.client.get('/api/sentences?status=pending&source=all&meaning=all&roman=all')
        self.assertEqual(r.status_code, 200)
        ids = [x['id'] for x in r.json()['items']]
        self.assertIn(s_pen, ids)
        self.assertNotIn(s_app, ids)

        r = self.client.get('/api/sentences?status=all&source=all&meaning=no_meaning&roman=all')
        self.assertEqual(r.status_code, 200)
        ids = [x['id'] for x in r.json()['items']]
        self.assertIn(s_pen, ids)
        self.assertNotIn(s_app, ids)

        r = self.client.get('/api/sentences?status=all&source=all&meaning=has_meaning&roman=all')
        self.assertEqual(r.status_code, 200)
        ids = [x['id'] for x in r.json()['items']]
        self.assertIn(s_app, ids)

        r = self.client.get('/api/sentences?status=all&source=all&meaning=all&roman=no_roman')
        self.assertEqual(r.status_code, 200)
        ids = [x['id'] for x in r.json()['items']]
        self.assertIn(s_pen, ids)
        self.assertNotIn(s_app, ids)

        r = self.client.get('/api/sentences?status=all&source=community&meaning=all&roman=all')
        self.assertEqual(r.status_code, 200)
        ids = [x['id'] for x in r.json()['items']]
        self.assertIn(s_app, ids)
        self.assertNotIn(s_pen, ids)

    def test_review_queue_filtering_api(self):
        with server.database() as db:
            s1 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_r1', romanization='ka', source_type='community', status='pending'))
            t1 = server.insert(db, 'translations', dict(sentence_id=s1, vietnamese_text='dịch r1', status='pending'))

            s2 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_r2', romanization='', source_type='dictionary', status='approved'))

        r = self.client.get('/api/review-queue?status=all&sentence_status=pending&source=all&meaning=all&roman=all')
        self.assertEqual(r.status_code, 200)
        items = r.json()['items']
        self.assertTrue(any(x.get('sentence_id') == s1 or x.get('id') == s1 for x in items))

        r = self.client.get('/api/review-queue?sentence_status=all&source=all&meaning=no_meaning&roman=all')
        self.assertEqual(r.status_code, 200)
        items = r.json()['items']
        self.assertTrue(any(x.get('id') == s2 for x in items))
    def test_admin_word_edit_overwrites_in_place(self):
        r_create = self.post('words', {
            'tai_text_original': 'ꪀꪱ',
            'romanization_original': 'ka',
            'vietnamese_meaning': 'nghĩa gốc'
        })
        self.assertEqual(r_create.status_code, 200)
        wid = r_create.json()['id']

        with server.database() as db:
            initial_count = db.execute('SELECT count(*) FROM word_contributions').fetchone()[0]

        self.login()
        r = self.client.post('/api/admin/words/edit', json={
            'id': wid,
            'tai_text': 'ꪀꪱ_sua',
            'romanization': 'ka_sua',
            'vietnamese_meaning': 'nghĩa đã sửa',
            'status': 'approved'
        })
        self.assertEqual(r.status_code, 200)
        self.assertIn('ghi đè', r.json()['message'])

        with server.database() as db:
            new_count = db.execute('SELECT count(*) FROM word_contributions').fetchone()[0]
            self.assertEqual(new_count, initial_count)

            updated_wc = db.execute('SELECT * FROM word_contributions WHERE id=?', (wid,)).fetchone()
            self.assertEqual(updated_wc['tai_text_final'], 'ꪀꪱ_sua')
            self.assertEqual(updated_wc['romanization_final'], 'ka_sua')
            self.assertEqual(updated_wc['vietnamese_meaning'], 'nghĩa đã sửa')
            self.assertEqual(updated_wc['status'], 'approved')

            lex = db.execute('SELECT * FROM lexemes WHERE tai_text_original=?', ('ꪀꪱ_sua',)).fetchone()
            self.assertIsNotNone(lex)
            sense = db.execute('SELECT * FROM word_senses WHERE lexeme_id=? AND vietnamese_meaning=?', (lex['id'], 'nghĩa đã sửa')).fetchone()
            self.assertIsNotNone(sense)

    def test_review_queue_prioritizes_unreviewed_sentences(self):
        with server.database() as db:
            # Sentence 1 has a translation that has been reviewed
            s_reviewed = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_rev', romanization='ka', status='approved'))
            t_reviewed = server.insert(db, 'translations', dict(sentence_id=s_reviewed, vietnamese_text='dịch cũ đã đánh giá', status='approved'))
            server.insert(db, 'translation_validations', dict(
                translation_id=t_reviewed, validation_status='correct', contributor_id='other_user', consent_version=server.CONSENT
            ))

            # Sentence 2 has a translation that has NEVER been reviewed
            s_unreviewed = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_unrev', romanization='ka', status='approved'))
            t_unreviewed = server.insert(db, 'translations', dict(sentence_id=s_unreviewed, vietnamese_text='dịch mới chưa đánh giá', status='approved'))

        r = self.client.get('/api/review-queue?limit=10')
        self.assertEqual(r.status_code, 200)
        items = r.json()['items']
        ids = [x['id'] for x in items]
        self.assertIn(t_unreviewed, ids)
        self.assertIn(t_reviewed, ids)
        # Unreviewed translation MUST come before reviewed translation
        self.assertLess(ids.index(t_unreviewed), ids.index(t_reviewed))

        # Test for sentences without translation (meaning='no_meaning')
        with server.database() as db:
            s_no_mean_rev = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_nm_rev', romanization='ka', status='approved'))
            server.insert(db, 'sentence_reviews', dict(
                sentence_id=s_no_mean_rev, naturalness='natural', contributor_id='other_user', consent_version=server.CONSENT
            ))

            s_no_mean_unrev = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_nm_unrev', romanization='ka', status='approved'))

        r2 = self.client.get('/api/review-queue?meaning=no_meaning&limit=10')
        self.assertEqual(r2.status_code, 200)
        items2 = r2.json()['items']
        ids2 = [x['id'] for x in items2]
        self.assertIn(s_no_mean_unrev, ids2)
        self.assertIn(s_no_mean_rev, ids2)
        self.assertLess(ids2.index(s_no_mean_unrev), ids2.index(s_no_mean_rev))

    def test_after_submitting_validation_switch_to_next_sentence(self):
        with server.database() as db:
            s1 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_1', romanization='ka1', status='approved', contributor_id='u1'))
            t1 = server.insert(db, 'translations', dict(sentence_id=s1, vietnamese_text='dịch 1', status='approved', contributor_id='u1'))

            s2 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_2', romanization='ka2', status='approved', contributor_id='u2'))
            t2 = server.insert(db, 'translations', dict(sentence_id=s2, vietnamese_text='dịch 2', status='approved', contributor_id='u2'))

        # Fetch first review item
        r1 = self.client.get('/api/review-queue?limit=1')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(len(r1.json()['items']), 1)
        first_item = r1.json()['items'][0]
        first_sentence_id = first_item['sentence_id']
        first_trans_id = first_item['id']

        # Submit evaluation for first item
        r_val = self.post('validations', {
            'translation_id': first_trans_id,
            'validation_status': 'correct'
        })
        self.assertEqual(r_val.status_code, 200)

        # Fetch next review item: MUST be a different sentence!
        r2 = self.client.get('/api/review-queue?limit=1')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.json()['items']), 1)
        second_item = r2.json()['items'][0]
        self.assertNotEqual(second_item['sentence_id'], first_sentence_id)
        self.assertNotEqual(second_item['id'], first_trans_id)

    def test_password_change_limit_three_times_in_24_hours(self):
        # Register a test account
        email = 'pwdtest@example.com'
        r_reg = self.client.post('/api/auth/register', json={
            'email': email,
            'password': 'Password123!',
            'display_name': 'PasswordTester'
        })
        self.assertEqual(r_reg.status_code, 200)

        # 1st change: success
        r1 = self.client.post('/api/me/change-password', json={
            'current_password': 'Password123!',
            'new_password': 'Password456!',
            'confirm_password': 'Password456!'
        })
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()['password_changes_count'], 1)

        # 2nd change: success
        r2 = self.client.post('/api/me/change-password', json={
            'current_password': 'Password456!',
            'new_password': 'Password789!',
            'confirm_password': 'Password789!'
        })
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()['password_changes_count'], 2)

        # 3rd change: success
        r3 = self.client.post('/api/me/change-password', json={
            'current_password': 'Password789!',
            'new_password': 'Password321!',
            'confirm_password': 'Password321!'
        })
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()['password_changes_count'], 3)

        # 4th change: MUST be blocked with 429
        r4 = self.client.post('/api/me/change-password', json={
            'current_password': 'Password321!',
            'new_password': 'Password999!',
            'confirm_password': 'Password999!'
        })
        self.assertEqual(r4.status_code, 429)
        err_msg = r4.json().get('detail') or r4.json().get('message', '')
        self.assertIn('3 lần trong 24 giờ qua', err_msg)

        # Check session user returns count and lock_until
        r_me = self.client.get('/api/session')
        self.assertEqual(r_me.status_code, 200)
        user = r_me.json()['user']
        self.assertEqual(user['password_changes_count'], 3)
        self.assertGreater(user['password_lock_until'], 0)

    def test_admin_delete_entire_word(self):
        # Contribute a word and approve it into lexemes/word_senses
        r_create = self.post('words', {
            'tai_text_original': 'ꪹꪄꪱ꫁_del',
            'romanization_original': 'khao_del',
            'vietnamese_meaning': 'gạo xóa toàn bộ'
        })
        self.assertEqual(r_create.status_code, 200)
        wid = r_create.json()['id']

        self.login()
        r_app = self.client.post('/api/admin/moderate', json={'table': 'word_contributions', 'id': wid, 'status': 'approved'})
        self.assertEqual(r_app.status_code, 200)

        with server.database() as db:
            lex = db.execute('SELECT * FROM lexemes WHERE tai_text_original=?', ('ꪹꪄꪱ꫁_del',)).fetchone()
            self.assertIsNotNone(lex)
            lid = lex['id']
            senses = db.execute('SELECT * FROM word_senses WHERE lexeme_id=?', (lid,)).fetchall()
            self.assertTrue(len(senses) > 0)
            wc = db.execute('SELECT * FROM word_contributions WHERE id=?', (wid,)).fetchone()
            self.assertIsNotNone(wc)

        # Call delete-entire
        r_del = self.client.post('/api/admin/words/delete-entire', json={'id': wid})
        self.assertEqual(r_del.status_code, 200)
        self.assertIn('Đã xóa hoàn toàn', r_del.json()['message'])

        # Verify everything is gone
        with server.database() as db:
            self.assertIsNone(db.execute('SELECT * FROM lexemes WHERE id=?', (lid,)).fetchone())
            self.assertEqual(len(db.execute('SELECT * FROM word_senses WHERE lexeme_id=?', (lid,)).fetchall()), 0)
            self.assertEqual(len(db.execute('SELECT * FROM lexeme_search_keys WHERE lexeme_id=?', (lid,)).fetchall()), 0)
            self.assertEqual(len(db.execute('SELECT * FROM word_contributions WHERE tai_text_original=?', ('ꪹꪄꪱ꫁_del',)).fetchall()), 0)
            # Moderation event recorded
            mod = db.execute("SELECT * FROM moderation_events WHERE entity_table='word_contributions' AND new_status='deleted' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(mod)

    def test_admin_cascade_delete_word_contribution_removes_sense(self):
        # Contribute a word and approve it
        r_create = self.post('words', {
            'tai_text_original': 'ꪹꪄꪱ꫁_casc',
            'romanization_original': 'khao_casc',
            'vietnamese_meaning': 'nghĩa đơn cascade'
        })
        self.assertEqual(r_create.status_code, 200)
        wid = r_create.json()['id']

        self.login()
        r_app = self.client.post('/api/admin/moderate', json={'table': 'word_contributions', 'id': wid, 'status': 'approved'})
        self.assertEqual(r_app.status_code, 200)

        with server.database() as db:
            lex = db.execute('SELECT * FROM lexemes WHERE tai_text_original=?', ('ꪹꪄꪱ꫁_casc',)).fetchone()
            self.assertIsNotNone(lex)
            lid = lex['id']

        # Delete the contribution using /api/admin/delete
        r_del = self.client.post('/api/admin/delete', json={
            'table': 'word_contributions',
            'scope': 'selected',
            'ids': [wid],
            'expected_count': 1
        })
        self.assertEqual(r_del.status_code, 200)

        # Verify lexeme and sense were cleaned up since no senses remain
        with server.database() as db:
            self.assertIsNone(db.execute('SELECT * FROM lexemes WHERE id=?', (lid,)).fetchone())
            self.assertEqual(len(db.execute('SELECT * FROM word_senses WHERE lexeme_id=?', (lid,)).fetchall()), 0)

    def test_admin_delete_translation_validation_cascades_to_sentence_and_translation(self):
        with server.database() as db:
            sid = server.insert(db, 'sentences', dict(tai_text_original='ꪹꪚ꪿ꪱ ꪁꪱꪙ ꪎꪷ', romanization='bau kan so', status='approved'))
            tid = server.insert(db, 'translations', dict(sentence_id=sid, vietnamese_text='ai hỏi (Thử nghiệm)', status='approved'))
            vid = server.insert(db, 'translation_validations', dict(translation_id=tid, validation_status='incorrect', contributor_id='tester', consent_version=server.CONSENT))

        self.login()
        r_del = self.client.post('/api/admin/delete', json={
            'table': 'translation_validations',
            'scope': 'selected',
            'ids': [vid],
            'expected_count': 1
        })
        self.assertEqual(r_del.status_code, 200)

        with server.database() as db:
            self.assertIsNone(db.execute('SELECT * FROM translation_validations WHERE id=?', (vid,)).fetchone())
            self.assertIsNone(db.execute('SELECT * FROM translations WHERE id=?', (tid,)).fetchone())
            self.assertIsNone(db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone())

    def test_admin_delete_sentence_only_translations_vs_permanent(self):
        with server.database() as db:
            s1 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_test_s1', romanization='ka1', status='approved'))
            t1 = server.insert(db, 'translations', dict(sentence_id=s1, vietnamese_text='nghĩa s1', status='approved'))

            s2 = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_test_s2', romanization='ka2', status='approved'))
            t2 = server.insert(db, 'translations', dict(sentence_id=s2, vietnamese_text='nghĩa s2', status='approved'))

        self.login()
        # 1. Delete only translations for s1
        r1 = self.client.post('/api/admin/delete', json={
            'table': 'sentences',
            'target': 'only_translations',
            'scope': 'selected',
            'ids': [s1],
            'expected_count': 1
        })
        self.assertEqual(r1.status_code, 200)
        with server.database() as db:
            # Translation t1 is deleted
            self.assertIsNone(db.execute('SELECT * FROM translations WHERE id=?', (t1,)).fetchone())
            # Sentence s1 is preserved!
            self.assertIsNotNone(db.execute('SELECT * FROM sentences WHERE id=?', (s1,)).fetchone())

        # 2. Delete permanent for s2
        r2 = self.client.post('/api/admin/delete', json={
            'table': 'sentences',
            'target': 'permanent',
            'scope': 'selected',
            'ids': [s2],
            'expected_count': 1
        })
        self.assertEqual(r2.status_code, 200)
        with server.database() as db:
            # Both translation and sentence are completely deleted
            self.assertIsNone(db.execute('SELECT * FROM translations WHERE id=?', (t2,)).fetchone())
            self.assertIsNone(db.execute('SELECT * FROM sentences WHERE id=?', (s2,)).fetchone())

    def test_admin_delete_sentence_review_only_translations(self):
        with server.database() as db:
            s = server.insert(db, 'sentences', dict(tai_text_original='ꪀꪱ_test_sr', romanization='ka_sr', status='approved'))
            t = server.insert(db, 'translations', dict(sentence_id=s, vietnamese_text='nghĩa sr', status='approved'))
            r_id = server.insert(db, 'sentence_reviews', dict(sentence_id=s, naturalness='natural', contributor_id='tester', consent_version=server.CONSENT))

        self.login()
        res = self.client.post('/api/admin/delete', json={
            'table': 'sentence_reviews',
            'target': 'only_translations',
            'scope': 'selected',
            'ids': [r_id],
            'expected_count': 1
        })
        self.assertEqual(res.status_code, 200)
        with server.database() as db:
            # Translation is deleted
            self.assertIsNone(db.execute('SELECT * FROM translations WHERE id=?', (t,)).fetchone())
            # Sentence s is preserved
            self.assertIsNotNone(db.execute('SELECT * FROM sentences WHERE id=?', (s,)).fetchone())

if __name__ == '__main__':
    unittest.main()
