"""Direct archive approval and report deadline tracking."""
import json
import io
import tempfile
import unittest
import zipfile
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import backend.app as api


class ArchiveWorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.engine=create_engine('sqlite:///'+str(self.root/'test.db'),connect_args={'check_same_thread':False});api.Base.metadata.create_all(self.engine)
  self.store=patch.object(api,'STORE',self.root/'store');self.archive=patch.object(api,'ARCHIVE_ROOT',self.root/'archive');self.store.start();self.archive.start();api.STORE.mkdir();api.ARCHIVE_ROOT.mkdir()
  self.session=Session(self.engine,expire_on_commit=False)
  self.session.add_all([api.Department(id=1,name='Văn phòng',code='VP',email='vp@example.com'),api.Department(id=2,name='Phòng Đào tạo',code='PDT',email='dt@example.com'),api.Department(id=3,name='Phòng Khác',code='PK',email='pk@example.com')])
  self.users={}
  for uid,role,dep in [(1,'CLERK',2),(2,'DEPARTMENT',3),(3,'CLERK',1)]:
   user=api.User(id=uid,username=str(uid),full_name=f'User {uid}',password_hash='unused',role=role,department_id=dep,active=True);self.session.add(user);self.users[uid]=user
  original_permission=api.has_permission
  self.requester_permissions=patch.object(api,'has_permission',side_effect=lambda session,user,permission: False if user.id==1 and permission=='ARCHIVE' else original_permission(session,user,permission));self.requester_permissions.start()
  self.session.commit();self.uid=1;api.app.dependency_overrides[api.db]=lambda:self.session;api.app.dependency_overrides[api.current]=lambda:self.users[self.uid];self.client=TestClient(api.app)
  pdf=api.pymupdf.open();pdf.new_page().insert_text((40,40),'Archive report content');self.pdf=pdf.tobytes();pdf.close()
 def tearDown(self):
  self.requester_permissions.stop();self.client.close();api.app.dependency_overrides.clear();self.session.close();self.engine.dispose();self.store.stop();self.archive.stop();self.tmp.cleanup()
 def test_docx_archive_upload_and_resubmit(self):
  with patch('backend.document_upload.convert_docx',return_value=self.pdf):
   files={'file':('report.docx',b'word','application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
   response=self.client.post('/api/archive/uploads',data={'doc_type':'BÁO CÁO','title':'Word report'},files=files)
   self.assertEqual(response.status_code,200,response.text)
   item=response.json()
   self.assertEqual(item['file_name'],'report.pdf')
   self.assertEqual(Path(item['file_path']).read_bytes(),self.pdf)
   self.uid=3
   returned=self.client.post(f"/api/archive/uploads/{item['id']}/review",json={'decision':'RETURN','note':'Update'})
   self.assertEqual(returned.status_code,200,returned.text)
   self.uid=1
   response=self.client.post(f"/api/archive/uploads/{item['id']}/resubmit",files=files)
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['file_name'],'report.pdf')

 def test_archive_and_workflow_share_number_sequence(self):
  self.uid=3
  year=date.today().year
  for direction,category in [('IN','CÔNG VĂN ĐẾN'),('OUT','CÔNG VĂN ĐI')]:
   existing=api.Document(direction=direction,doc_type='CÔNG VĂN',title='Existing',owner_id=3,number=7,archive_year=year,status='NUMBERED')
   self.session.add(existing);self.session.commit()
   with patch.object(api,'ocr_pdf',return_value='Text'):
    response=self.client.post('/api/archive/uploads',data={'folder':category,'archive_year':year,'title':'Archive'},files={'file':('archive.pdf',self.pdf,'application/pdf')})
   self.assertEqual(response.status_code,200,response.text)
   self.assertEqual(response.json()['number'],8)
   self.assertEqual(api.allocate_archive_number(self.session,year,category),9)
   self.session.commit()
  # A subsequent incoming document must continue after archive uploads.
  incoming=self.client.post('/api/documents',data={'direction':'IN','title':'Next','issuing_agency':'External','issued_date':date.today().isoformat()},files={'file':('next.pdf',self.pdf,'application/pdf')})
  self.assertEqual(incoming.status_code,200,incoming.text)
  numbered=self.client.post(f"/api/documents/{incoming.json()['id']}/incoming-number",data={'year':year})
  self.assertEqual(numbered.status_code,200,numbered.text)
  self.assertEqual(numbered.json()['number'],10)
  self.assertEqual(api.allocate_archive_number(self.session,year+1,'CÔNG VĂN ĐẾN'),1)

 def upload(self,title='Báo cáo tháng'):
  return self.client.post('/api/archive/uploads',data={'doc_type':'BÁO CÁO','title':title,'issued_date':date.today().isoformat()},files={'file':('report.pdf',self.pdf,'application/pdf')})
 def test_direct_upload_return_resubmit_approve_and_auto_number(self):
  response=self.upload();self.assertEqual(response.status_code,200,response.text);did=response.json()['id'];self.assertIsNone(response.json()['number'])
  self.uid=2;self.assertEqual(self.client.get('/api/documents?archive_workspace=true').status_code,403)
  self.uid=3;self.assertEqual([row['id'] for row in self.client.get('/api/documents?archive_workspace=true').json()],[did])
  returned=self.client.post(f'/api/archive/uploads/{did}/review',json={'decision':'RETURN','note':'Bổ sung chữ ký'});self.assertEqual(returned.status_code,200,returned.text)
  self.uid=1;resubmitted=self.client.post(f'/api/archive/uploads/{did}/resubmit',data={'title':'Báo cáo đã ký'},files={'file':('signed.pdf',self.pdf,'application/pdf')});self.assertEqual(resubmitted.status_code,200,resubmitted.text);self.assertEqual(resubmitted.json()['revision'],2)
  self.uid=3
  with patch.object(api,'ocr_pdf',return_value='archive report content'):
   approved=self.client.post(f'/api/archive/uploads/{did}/review',json={'decision':'APPROVE','note':'Đủ điều kiện lưu'});self.assertEqual(approved.status_code,200,approved.text)
  item=approved.json();self.assertEqual(item['status'],'ARCHIVED');self.assertEqual(item['number'],1);self.assertEqual(Path(item['file_path']).parent.name,'BÁO CÁO')
  self.uid=1;second=self.upload('Báo cáo tiếp theo');self.uid=3
  with patch.object(api,'ocr_pdf',return_value='next'):
   second=self.client.post(f"/api/archive/uploads/{second.json()['id']}/review",json={'decision':'APPROVE','note':'Đồng ý'})
  self.assertEqual(second.json()['number'],2)

 def test_clerk_selects_historical_year_and_folder_without_review(self):
  self.uid=3
  with patch.object(api,'ocr_pdf',return_value='quyet dinh cu'):
   response=self.client.post('/api/archive/uploads',data={'folder':'QUYẾT ĐỊNH','archive_year':2022},files={'file':('quyet-dinh-2022.pdf',self.pdf,'application/pdf')})
  self.assertEqual(response.status_code,200,response.text);item=response.json();self.assertEqual(item['status'],'ARCHIVED');self.assertEqual(item['archive_year'],2022);self.assertEqual(item['number'],1);self.assertEqual(Path(item['file_path']).parts[-3:-1],('2022','QUYẾT ĐỊNH'))
  self.assertFalse(any(row['status']=='PENDING_ARCHIVE_REVIEW' for row in self.client.get('/api/documents?archive_workspace=true').json()))
  report=self.client.get('/api/dashboard/meeting-report?start=2022-01-01&end=2022-12-31').json();self.assertEqual(report['direct_archive'],1)
  sequence=self.session.query(api.Sequence).filter_by(year=2022,doc_type='QUYẾT ĐỊNH').one();sequence.current=0
  self.session.add(api.Document(direction='ARCHIVE',doc_type='QUYẾT ĐỊNH',title='Số cũ',number=7,archive_year=2022,status='ARCHIVED',owner_id=3));self.session.commit()
  with patch.object(api,'ocr_pdf',return_value='quyet dinh tiep theo'):
   next_file=self.client.post('/api/archive/uploads',data={'folder':'QUYẾT ĐỊNH','archive_year':2022},files={'file':('quyet-dinh-tiep.pdf',self.pdf,'application/pdf')})
  self.assertEqual(next_file.json()['number'],8)

 def test_register_preserves_sample_sheet_and_uses_named_sheets(self):
  year=date.today().year
  for kind in ['HỒ SƠ KHÁC','HỢP ĐỒNG','THƯ MỜI','NGHỊ QUYẾT HỘI ĐỒNG TRƯỜNG']:
   self.session.add(api.Document(direction='OUT',doc_type=kind,title='Test '+kind,number=1,archive_year=year,status='ARCHIVED',owner_id=3))
  self.session.commit()
  data=api.document_register_data(year,self.users[3],self.session)
  self.assertNotIn('Mẫu',data)
  self.assertEqual(len(data['Thư mời']),1)
  self.assertEqual(len(data['NQ-HĐT']),1)
  data['Mẫu']=[['Do not write this']]
  output=api.render_document_register_xlsx(year,data)
  with zipfile.ZipFile(api.REGISTER_TEMPLATE) as original,zipfile.ZipFile(io.BytesIO(output)) as exported:
   self.assertEqual(original.read('xl/worksheets/sheet1.xml'),exported.read('xl/worksheets/sheet1.xml'))
   self.assertEqual(original.read('xl/workbook.xml'),exported.read('xl/workbook.xml'))

 def test_document_number_register_exports_the_supplied_excel_template(self):
  year=date.today().year
  self.session.add(api.Document(direction='OUT',doc_type='CÔNG VĂN',title='Thông báo lịch họp',number=12,symbol=f'CV 12-{year%100:02d}',issued_date=date(year,9,14),status='ARCHIVED',owner_id=3,department_id=1,file_name='lich-hop.pdf'))
  self.session.commit();self.uid=3
  response=self.client.get(f'/api/register/export?year={year}');self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.headers['content-type'],'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
  with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
   workbook.testzip();sheet=ET.fromstring(workbook.read('xl/worksheets/sheet5.xml'));namespace={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
   def cell(ref):
    node=sheet.find(f".//m:c[@r='{ref}']",namespace);return ''.join(text.text or '' for text in node.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'))
   self.assertIn(str(year),cell('A5'));self.assertEqual(cell('B8'),f'CV 12-{year%100:02d}');self.assertIn('Thông báo lịch họp',cell('D8'))
  self.uid=1;self.assertEqual(self.client.get(f'/api/register/export?year={year}').status_code,403)

 def test_report_tracking_warning_does_not_send_automatically(self):
  deadline=(date.today()+timedelta(days=1)).isoformat();document=api.Document(direction='IN',doc_type='CÔNG VĂN',title='Báo cáo tuyển sinh',owner_id=3,department_id=1,assignee_ids='[2,3]',status='DEPARTMENT_REVIEW',file_name='source.pdf',file_path=str(self.root/'source.pdf'));(self.root/'source.pdf').write_bytes(self.pdf);self.session.add(document);self.session.flush()
  assignments=[{'department_id':2,'name':'Phòng Đào tạo','email':'dt@example.com','deadline':deadline},{'department_id':3,'name':'Phòng Khác','email':'pk@example.com','deadline':deadline}]
  decisions={'BGH':{'decision':'APPROVE'},'2':{'decision':'REPORT','at':'2026-01-01T08:00:00'}}
  self.session.add(api.IncomingReview(document_id=document.id,revision=1,note='Nộp báo cáo',assignments=json.dumps(assignments),decisions=json.dumps(decisions),pdf_path=str(self.root/'source.pdf'),created_by=3));self.session.add(api.EmailSetting(enabled=True,smtp_host='smtp.example.com',sender_email='vp@example.com',signature_html='<p>VP</p>'));self.session.commit()
  self.uid=3
  with patch.object(api,'send_document_email') as send:
   tracking=self.client.get('/api/reports/tracking').json();self.assertEqual(tracking[0]['received_count'],1);self.assertEqual(tracking[0]['missing'][0]['name'],'Phòng Khác')
   notes=self.client.get('/api/notifications').json();warning=next(item for item in notes if 'Đã nhận 1/2' in item['message']);self.assertEqual(warning['direction'],'REPORT');send.assert_not_called()
   self.client.get('/api/notifications');send.assert_not_called()
  self.uid=2;notes=self.client.get('/api/notifications').json();warning=next(item for item in notes if item['status']=='REPORT_DEADLINE_WARNING');self.assertEqual(warning['direction'],'IN')


if __name__=='__main__':unittest.main()
