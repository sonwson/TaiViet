import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import server


class AdminDeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=(server.DB_PATH,server.DB_BACKEND,server.pg_pool)
        server.DB_PATH=Path(self.temp.name)/'test.db'
        server.DB_BACKEND='sqlite'; server.pg_pool=None
        with server.database() as db:
            db.executescript((server.ROOT/'database/local.sql').read_text(encoding='utf-8'))
            db.executescript((server.ROOT/'database/extensions.sql').read_text(encoding='utf-8'))
            self.ids=[server.insert(db,'sentences',dict(tai_text_original='ꪀꪱ',romanization='delete-test',status='rejected')) for _ in range(35)]
            self.keep=server.insert(db,'sentences',dict(tai_text_original='ꪀꪱ',romanization='delete-test',status='approved'))
            self.translation=server.insert(db,'translations',dict(sentence_id=self.ids[0],vietnamese_text='test'))
            server.insert(db,'translation_validations',dict(translation_id=self.translation,contributor_id='user',validation_status='correct',consent_version='test'))
            server.insert(db,'sentence_reviews',dict(sentence_id=self.ids[0],contributor_id='user',naturalness='natural',consent_version='test'))
        self.client=TestClient(server.app)
        self.headers={'Authorization':'Bearer '+server.create_admin_jwt()}

    def tearDown(self):
        self.client.close()
        server.DB_PATH,server.DB_BACKEND,server.pg_pool=self.original
        self.temp.cleanup()

    def delete(self,**extra):
        return self.client.post('/api/admin/delete',headers=self.headers,json=dict(table='sentences',status='rejected',q='delete-test',scope='filtered',expected_count=35,**extra))

    def test_filtered_across_pages_and_dependencies(self):
        result=self.client.get('/api/admin/records?table=sentences&status=rejected&q=delete-test',headers=self.headers).json()
        self.assertEqual(result['total'],35)
        self.assertEqual(len(result['items']),30)
        response=self.delete()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['deleted'],35)
        with server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sentences').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM translation_validations').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM sentence_reviews').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT count(*) FROM moderation_events WHERE new_status='deleted'").fetchone()[0],35)

    def test_selected_and_filter_protection(self):
        body=dict(table='sentences',status='rejected',scope='selected',ids=[self.keep],expected_count=1)
        self.assertEqual(self.client.post('/api/admin/delete',headers=self.headers,json=body).status_code,409)
        body['ids']=[self.ids[0]]
        response=self.client.post('/api/admin/delete',headers=self.headers,json=body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['deleted'],1)

    def test_auth_validation_and_stale_count(self):
        self.assertIn(self.client.post('/api/admin/delete',json={}).status_code,(401,403))
        for table in ['moderation_events','user_accounts','sentences; DROP TABLE sentences',[]]:
            self.assertEqual(self.client.post('/api/admin/delete',headers=self.headers,json={'table':table}).status_code,422)
        with server.database() as db:
            db.execute('UPDATE sentences SET status=? WHERE id=?',('approved',self.ids[0]))
        self.assertEqual(self.delete().status_code,409)
        with server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sentences').fetchone()[0],36)

    def test_transaction_rollback(self):
        with server.database() as db:
            db.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON sentences BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(Exception): self.delete()
        with server.database() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM translations').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM translation_validations').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM moderation_events').fetchone()[0],0)
