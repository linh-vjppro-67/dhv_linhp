"""Meeting report date filters, totals and CSV export."""
import tempfile,io,zipfile
import unittest
from datetime import date,datetime
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import backend.app as api


class MeetingReportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.engine=create_engine('sqlite:///'+str(Path(self.tmp.name)/'test.db'),connect_args={'check_same_thread':False});api.Base.metadata.create_all(self.engine);self.session=Session(self.engine,expire_on_commit=False)
  self.session.add(api.Department(id=1,name='Văn phòng',code='VP'));self.user=api.User(id=1,username='clerk',full_name='Văn thư',password_hash='unused',role='CLERK',department_id=1,active=True);self.session.add(self.user)
  self.session.add_all([
   api.Document(id=1,direction='IN',doc_type='CÔNG VĂN',title='Trong tháng đến',received_date=date(2026,8,15),status='ARCHIVED',owner_id=1,created_at=datetime(2026,8,15,8)),
   api.Document(id=2,direction='OUT',doc_type='QUYẾT ĐỊNH',title='Trong tháng đi',issued_date=date(2026,8,20),status='SEALED',owner_id=1,created_at=datetime(2026,8,20,8)),
   api.Document(id=3,direction='ARCHIVE',doc_type='BÁO CÁO',title='Báo cáo trực tiếp',issued_date=date(2026,8,31),status='ARCHIVED',owner_id=1,created_at=datetime(2026,8,31,8)),
   api.Document(id=4,direction='INTERNAL',doc_type='THÔNG BÁO',title='Ngoài kỳ',issued_date=date(2026,7,31),status='ARCHIVED',owner_id=1,created_at=datetime(2026,7,31,8)),
   api.Document(id=5,direction='IN',doc_type='CÔNG VĂN',title='Đã xóa',received_date=date(2026,8,10),status='DELETED',owner_id=1,created_at=datetime(2026,8,10,8)),
  ]);self.session.commit();api.app.dependency_overrides[api.db]=lambda:self.session;api.app.dependency_overrides[api.current]=lambda:self.user;self.client=TestClient(api.app)
 def tearDown(self):
  self.client.close();api.app.dependency_overrides.clear();self.session.close();self.engine.dispose();self.tmp.cleanup()
 def test_month_totals_types_and_csv(self):
  response=self.client.get('/api/dashboard/meeting-report?start=2026-08-01&end=2026-08-31');self.assertEqual(response.status_code,200,response.text);report=response.json()
  self.assertEqual((report['total'],report['incoming'],report['outgoing'],report['direct_archive']),(3,1,1,1));self.assertEqual({item['name']:item['count'] for item in report['by_type']},{'CÔNG VĂN':1,'QUYẾT ĐỊNH':1,'BÁO CÁO':1})
  export=self.client.get('/api/dashboard/meeting-report/export/xlsx?start=2026-08-01&end=2026-08-31');self.assertEqual(export.status_code,200)
  with zipfile.ZipFile(io.BytesIO(export.content)) as book:
   sheet=book.read('xl/worksheets/sheet1.xml').decode();self.assertIn('BÁO CÁO GIAO BAN',sheet);self.assertIn('Trong tháng đến',sheet);self.assertNotIn('Ngoài kỳ',sheet);self.assertIn('autoFilter',sheet)
  exported_pdf=self.client.get('/api/dashboard/meeting-report/export/pdf?start=2026-08-01&end=2026-08-31');self.assertEqual(exported_pdf.status_code,200)
  with api.pymupdf.open(stream=exported_pdf.content,filetype='pdf') as pdf:self.assertGreaterEqual(len(pdf),1);self.assertIn('BÁO CÁO GIAO BAN',pdf[0].get_text())
 def test_invalid_range_is_rejected(self):
  self.assertEqual(self.client.get('/api/dashboard/meeting-report?start=2026-09-01&end=2026-08-01').status_code,422)


if __name__=='__main__':unittest.main()
