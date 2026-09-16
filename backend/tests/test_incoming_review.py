from urllib.parse import urlparse, parse_qs
"""Run: backend/.venv/bin/python -m unittest backend.tests.test_incoming_review"""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException,UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import backend.app as app


class IncomingReviewTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.engine=create_engine('sqlite:///'+self.temp.name+'/test.db')
  app.Base.metadata.create_all(self.engine)
  self.store=patch.object(app,'STORE',Path(self.temp.name));self.store.start()
  with Session(self.engine) as s:
   s.add_all([app.Department(id=1,name='Văn phòng',code='VP'),app.Department(id=2,name='BGH',code='BGH'),app.Department(id=3,name='Đào tạo',code='PDT',email='dt@example.com'),app.Department(id=4,name='Kế toán',code='KT',email='kt@example.com')])
   for uid,role,dep in [(1,'OFFICE_HEAD',1),(2,'BGH',2),(3,'DEPARTMENT',3),(4,'DEPARTMENT',4),(5,'CLERK',1),(6,'DEPARTMENT',1)]:
    s.add(app.User(id=uid,username=str(uid),full_name=str(uid),role=role,department_id=dep,password_hash='unused',active=True))
   pdf=app.pymupdf.open();pdf.new_page().insert_text((40,40),'Original document');pdf.save(self.temp.name+'/original.pdf');pdf.close()
   s.add(app.Document(id=1,direction='IN',doc_type='CÔNG VĂN',title='Test',number=1,symbol='001',status='NUMBERED',owner_id=5,file_path=self.temp.name+'/original.pdf',file_name='test.pdf'))
   s.commit()
  self.sent=[]
  self.mail=patch.object(app,'send_document_email',side_effect=lambda *a:self.sent.append(a[2]));self.mail.start()
 def tearDown(self):
  self.mail.stop();self.store.stop();self.engine.dispose();self.temp.cleanup()
 def invoke(self,fn,uid,*args):
  with Session(self.engine) as s:
   u=s.get(app.User,uid)
   return fn(1,*args,u=u,s=s)
 def submit(self,rev=0):
  return self.invoke(app.submit_review,1,app.ReviewSubmission(revision=rev,note='Phân công kiểm tra và phản hồi.',assignments=[app.ReviewAssignment(department_id=3,responsibility='Đơn vị chủ trì xử lý'),app.ReviewAssignment(department_id=4,responsibility='Đơn vị phối hợp')]))
 def respond(self,uid,rev=1,decision='APPROVE',comment=''):
  return self.invoke(app.respond_review,uid,app.ReviewResponse(revision=rev,decision=decision,comment=comment))
 def report(self,uid,rev=1,comment='Đã hoàn thành báo cáo'):
  with Session(self.engine) as s:
   return asyncio.run(app.submit_review_report(1,rev,comment,None,u=s.get(app.User,uid),s=s))
 def email(self,rev=1):
  return self.invoke(app.email_review,1,app.ReviewResponse(revision=rev,decision='EMAIL'))
 def test_full_revision_and_email_gate(self):
  self.submit()
  with self.assertRaises(HTTPException):self.respond(3)
  with self.assertRaises(HTTPException):self.email()
  self.respond(2)
  self.report(3)
  self.respond(4,decision='COMMENT',comment='Cần sửa phân công')
  with self.assertRaises(HTTPException):self.email()
  self.respond(1,decision='COMMENT',comment='Đã nhận phản hồi, sẽ sửa phiếu')
  self.submit(1)
  with self.assertRaises(HTTPException):self.respond(3,rev=1)
  with self.assertRaises(HTTPException):self.email(2)
  self.respond(2,rev=2);self.report(3,rev=2)
  with self.assertRaises(HTTPException):self.email(2)
  self.report(4,rev=2)
  draft=self.email(2)
  self.assertEqual(draft['email_status'],'draft')
  query=parse_qs(urlparse(draft['gmail_url']).query)
  self.assertEqual(urlparse(draft['gmail_url']).netloc,'mail.google.com')
  self.assertEqual(query['authuser'],['ngcphnglinhp6.7.2000@gmail.com'])
  self.assertEqual(query['view'],['cm'])
  self.assertEqual(query['su'],[draft['document']['title']])
  self.assertEqual(draft['document']['status'],'REVIEW_READY')
  self.assertEqual(parse_qs(urlparse(draft['gmail_url']).query)['to'],['dt@example.com,kt@example.com'])
  self.assertEqual(self.sent,[])
  confirmed=self.invoke(app.confirm_gmail,1,app.GmailConfirmation(revision=draft['document']['revision'],review_revision=2))
  self.assertEqual(confirmed['status'],'FORWARDED')
  with self.assertRaises(HTTPException):self.email(2)
  with Session(self.engine) as s:
   rounds=s.query(app.IncomingReview).order_by(app.IncomingReview.revision).all()
   self.assertEqual(len(rounds),2)
   for r in rounds:
    with app.pymupdf.open(r.pdf_path) as pdf:
     self.assertEqual(len(pdf),2)
     opinion=pdf[0].get_text()
     self.assertIn('Phân công kiểm tra và phản hồi.',opinion)
     self.assertNotIn('Vòng duyệt',opinion)
     self.assertNotIn('Đơn vị nhận:',opinion)
     self.assertNotIn('Hạn xử lý:',opinion)
   self.assertIn('Đã hoàn thành báo cáo',rounds[0].decisions)
  history=self.invoke(app.get_review,3)
  self.assertEqual(len(history['rounds']),2)
  self.assertTrue(any(c['action']=='REVIEW_COMMENT' for c in history['comments']))
 def test_review_without_assignments_can_be_approved_and_archived(self):
  result=self.invoke(app.submit_review,1,app.ReviewSubmission(note='Lưu để biết'))
  self.assertEqual(result['status'],'PENDING_BGH')
  before=self.invoke(app.get_review,1)
  self.assertEqual(before['assignments'],[])
  self.assertFalse(before['can_email'])
  approved=self.respond(2)
  self.assertEqual(approved['status'],'REVIEW_READY')
  review=self.invoke(app.get_review,1)
  self.assertFalse(review['can_email'])
  with patch.object(app,'ocr_pdf',return_value='Text'),patch.object(app,'archive_file'):
   with Session(self.engine) as session:
    clerk=app.User(id=99,username='archive_clerk',full_name='Clerk',role='CLERK',password_hash='unused',active=True)
    session.add(clerk);session.commit()
    result=app.action(1,app.Act(action='ARCHIVE'),u=clerk,s=session)
    self.assertEqual(result['status'],'ARCHIVED')

 def test_permissions_and_validation(self):
  self.submit()
  with self.assertRaises(HTTPException):self.respond(6)
  with self.assertRaises(HTTPException):self.respond(5)
  with self.assertRaises(HTTPException):self.respond(3)
  with self.assertRaises(HTTPException):self.respond(2,decision='REJECT')
  with self.assertRaises(HTTPException):self.invoke(app.submit_review,5,app.ReviewSubmission(revision=1,note='x',assignments=[]))
  with self.assertRaises(HTTPException):self.submit(0)
  with self.assertRaises(HTTPException):app.retired_incoming_step(1,u=None)
 def test_failed_email_keeps_approved_state(self):
  self.submit();self.respond(2);self.report(3);self.report(4)
  with patch.object(app,'send_document_email',side_effect=HTTPException(502,'SMTP failed')):
   self.assertEqual(self.email()['email_status'],'draft')
  self.assertEqual(self.invoke(app.get_review,1)['status'],'REVIEW_READY')

 def test_email_optional_purpose_and_deadline(self):
  self.invoke(app.submit_review,1,app.ReviewSubmission(purpose='Để báo cáo',note='Phân công',deadline='2026-10-01',assignments=[app.ReviewAssignment(department_id=3,responsibility='Đơn vị chủ trì xử lý'),app.ReviewAssignment(department_id=4,responsibility='Đơn vị phối hợp')]))
  self.respond(2);self.report(3);self.report(4)
  with patch.object(app,'send_document_email') as mail:
   draft=self.invoke(app.email_review,1,app.ReviewResponse(revision=1,decision='EMAIL',deadline='2026-10-01'))
   mail.assert_not_called()
   content=parse_qs(urlparse(draft['gmail_url']).query)['body'][0]
   self.assertIn('Kính gửi:',content)
   self.assertIn('Phó Hiệu trưởng - TS. Lương Thị Hòa',content)
   self.assertIn('đồng ý đề xuất của Văn phòng Trường – Phân công',content)
   self.assertIn('Văn phòng Trường kính chuyển văn bản đến quý đơn vị.',content)
   self.assertNotIn('Mục đích:',content)
   self.assertNotIn('Vai trò đơn vị',content)
   self.assertNotIn('Hạn xử lý:',content)
  history=self.invoke(app.get_review,1)
  self.assertEqual(history['status'],'REVIEW_READY')
  self.assertFalse(any(c['action']=='REVIEW_EMAIL' for c in history['comments']))

 def test_configured_email_and_separate_assignment_fields(self):
  self.invoke(app.submit_review,1,app.ReviewSubmission(purpose='Để báo cáo',note='Phân công',assignments=[app.ReviewAssignment(department_id=3,purpose='Để báo cáo',responsibility='Đơn vị phối hợp')]))
  r=self.invoke(app.get_review,1)
  self.assertEqual(r['assignments'][0]['purpose'],'Để báo cáo')
  self.assertEqual(r['assignments'][0]['responsibility'],'Đơn vị phối hợp')
  self.respond(2);self.report(3)
  with Session(self.engine) as s:
   s.get(app.Department,3).email='';s.commit()
  with self.assertRaises(HTTPException):self.email()
  with Session(self.engine) as s:
   s.get(app.Department,3).email='updated@example.com';s.commit()
  draft=self.email()
  self.assertEqual(parse_qs(urlparse(draft['gmail_url']).query)['to'],['updated@example.com'])
  self.assertEqual(self.sent,[])

 def test_department_discusses_and_submits_report(self):
  self.submit();self.respond(2)
  self.respond(3,decision='COMMENT',comment='Đang tổng hợp số liệu')
  with Session(self.engine) as s:
   user=s.get(app.User,3)
   result=asyncio.run(app.submit_review_report(1,1,'Đã hoàn thành báo cáo',None,u=user,s=s))
   self.assertEqual(result['status'],'DEPARTMENT_REVIEW')
   review=app.get_review(1,u=user,s=s)
   self.assertTrue(review['can_report'])
   self.assertFalse(review['can_decide'])
   self.assertEqual(review['decisions']['3']['decision'],'REPORT')
   self.assertEqual(review['comments'][-1]['action'],'REVIEW_REPORT')
   self.assertNotIn('report_file_path',review['comments'][-1])

 def test_department_report_accepts_pdf_attachment(self):
  self.submit();self.respond(2)
  upload=UploadFile(filename='bao-cao.pdf',file=io.BytesIO(b'%PDF-1.4 report'))
  with Session(self.engine) as s:
   user=s.get(app.User,3)
   asyncio.run(app.submit_review_report(1,1,'Báo cáo đính kèm',upload,u=user,s=s))
   action=s.query(app.Action).filter_by(document_id=1,action='REVIEW_REPORT').one()
   payload=app.json.loads(action.comment)
   self.assertEqual(payload['report_file_name'],'bao-cao.pdf')
   self.assertTrue(Path(payload['report_file_path']).is_file())
   response=app.download_review_report(1,action.id,u=user,s=s)
   self.assertEqual(Path(response.path),Path(payload['report_file_path']))

if __name__=='__main__':unittest.main()
