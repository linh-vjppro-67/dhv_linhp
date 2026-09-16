"""Shared outgoing/internal workflow, permissions, and signature preservation."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import backend.app as api


class OutgoingWorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.engine=create_engine('sqlite:///'+str(self.root/'test.db'),connect_args={'check_same_thread':False})
  api.Base.metadata.create_all(self.engine)
  self.store=patch.object(api,'STORE',self.root);self.store.start()
  self.session=Session(self.engine,expire_on_commit=False)
  self.session.add_all([api.Department(id=1,name='Văn phòng Trường',code='VP'),api.Department(id=2,name='Phòng Đào tạo',code='PDT'),api.Department(id=3,name='Khác',code='OTHER')])
  self.users={}
  for uid,role,dep in [(1,'DEPARTMENT',2),(2,'DEPARTMENT_HEAD',2),(3,'BGH',1),(4,'CLERK',1),(5,'DEPARTMENT_HEAD',3)]:
   user=api.User(id=uid,username=str(uid),full_name=role,role=role,department_id=dep,password_hash='unused',active=True)
   self.session.add(user);self.users[uid]=user
  self.session.commit();self.uid=1
  api.app.dependency_overrides[api.db]=lambda:self.session
  api.app.dependency_overrides[api.current]=lambda:self.users[self.uid]
  self.client=TestClient(api.app)
  pdf=api.pymupdf.open();pdf.new_page().insert_text((40,40),'Original document');self.pdf=pdf.tobytes();pdf.close()
 def tearDown(self):
  self.client.close();api.app.dependency_overrides.clear();self.session.close();self.engine.dispose();self.store.stop();self.tmp.cleanup()
 def test_reservation_requires_unit_and_uses_account_department(self):
  payload={'direction':'OUT','title':'Reserved','reason':'Prepare','issuing_agency':'Forged unit','department_id':3}
  for role in ['BGH']:
   self.users[1].role=role
   self.assertFalse(api.has_permission(self.session,self.users[1],'RESERVE_NUMBER'))
   self.assertEqual(self.client.post('/api/reserve-number',data=payload).status_code,403)
   self.assertEqual(self.client.post('/api/sequences/reserve',json={'doc_type':'CÔNG VĂN','year':2026,'quantity':1}).status_code,403)
  self.assertEqual(self.session.query(api.Document).count(),0)
  for role in ['DEPARTMENT','DEPARTMENT_HEAD']:
   self.users[1].role=role
   for direction in ['OUT','INTERNAL']:
    payload.update(direction=direction,doc_type='CÔNG VĂN' if direction=='OUT' else 'QUYẾT ĐỊNH')
    response=self.client.post('/api/reserve-number',data=payload)
    self.assertEqual(response.status_code,200,response.text)
    item=response.json()
    self.assertEqual(item['issuing_agency'],'Phòng Đào tạo')
    self.assertEqual(item['department_id'],2)
    self.assertEqual(item['owner_id'],1)
  self.users[1].department_id=None
  self.assertEqual(self.client.post('/api/reserve-number',data=payload).status_code,403)

 def test_office_roles_choose_configured_reservation_department(self):
  for role in ['ADMIN','CLERK','OFFICE_HEAD']:
   self.users[1].role=role
   self.assertTrue(api.has_permission(self.session,self.users[1],'RESERVE_NUMBER'))
   for direction,kind in [('OUT','CÔNG VĂN'),('INTERNAL','QUYẾT ĐỊNH')]:
    payload={'direction':direction,'doc_type':kind,'title':'Reserve','reason':'Prepare'}
    self.assertEqual(self.client.post('/api/reserve-number',data=payload).status_code,422)
    payload['department_id']=99999
    self.assertEqual(self.client.post('/api/reserve-number',data=payload).status_code,422)
    payload.update(department_id=3,issuing_agency='Forged')
    response=self.client.post('/api/reserve-number',data=payload)
    self.assertEqual(response.status_code,200,response.text)
    self.assertEqual(response.json()['department_id'],3)
    self.assertEqual(response.json()['issuing_agency'],'Khác')
   legacy=self.client.post('/api/sequences/reserve',json={'doc_type':'CÔNG VĂN','year':2026,'department_id':3})
   self.assertEqual(legacy.status_code,200,legacy.text)
   self.assertEqual(legacy.json()[0]['department_id'],3)

 def test_reservation_reject_resubmit_approve_and_delete(self):
  payload={'direction':'OUT','title':'Initial','reason':'Prepare'}
  response=self.client.post('/api/reserve-number',data=payload)
  self.assertEqual(response.status_code,200,response.text)
  did=response.json()['id']
  self.assertIsNone(response.json()['number'])
  self.assertEqual(self.session.query(api.Sequence).count(),0)
  route=f'/api/documents/{did}/reservation-decision'
  self.assertEqual(self.client.post(route,json={'decision':'APPROVE','revision':1}).status_code,403)
  self.uid=4
  self.assertEqual(self.client.post(route,json={'decision':'REJECT','revision':1}).status_code,422)
  for revision in [1,2]:
   rejected=self.client.post(route,json={'decision':'REJECT','revision':revision,'note':'Please revise'})
   self.assertEqual(rejected.status_code,200,rejected.text)
   self.assertEqual(rejected.json()['status'],'RESERVATION_REJECTED')
   self.uid=5
   self.assertEqual(self.client.post('/api/reserve-number',data={**payload,'request_id':did}).status_code,404)
   self.uid=1
   updated=self.client.post('/api/reserve-number',data={**payload,'request_id':did,'title':'Revised'})
   self.assertEqual(updated.status_code,200,updated.text)
   self.assertEqual(updated.json()['revision'],revision+1)
   self.assertIsNone(updated.json()['number'])
   self.uid=4
  self.assertEqual(self.client.post(route,json={'decision':'APPROVE','revision':1}).status_code,409)
  approved=self.client.post(route,json={'decision':'APPROVE','revision':3})
  self.assertEqual(approved.status_code,200,approved.text)
  self.assertEqual(approved.json()['number'],1)
  self.assertEqual(approved.json()['status'],'RESERVED_OUTGOING')
  self.assertEqual(self.client.post(route,json={'decision':'APPROVE','revision':3}).status_code,409)
  self.uid=1
  second=self.client.post('/api/reserve-number',data=payload).json()
  self.uid=4
  route=f"/api/documents/{second['id']}/reservation-decision"
  self.client.post(route,json={'decision':'REJECT','revision':1,'note':'No'})
  self.uid=1
  deleted=self.client.post(route,json={'decision':'DELETE','revision':1})
  self.assertEqual(deleted.status_code,200,deleted.text)
  self.assertEqual(deleted.json()['status'],'DELETED')
  self.assertEqual(self.session.query(api.Sequence).one().current,1)

 def test_reservation_empty_optional_date_from_browser(self):
  for value in ['', '   ', None]:
   fields={'direction':'OUT','doc_type':'CÔNG VĂN','title':'Test','reason':'Test'}
   if value is not None:fields['issued_date']=value
   response=self.client.post('/api/reserve-number',files={key:(None,val) for key,val in fields.items()})
   self.assertEqual(response.status_code,200,response.text)
   self.assertIsNone(response.json()['issued_date'])
   self.assertEqual(response.json()['status'],'RESERVATION_PENDING')
  fields['issued_date']='not-a-date'
  response=self.client.post('/api/reserve-number',files={key:(None,val) for key,val in fields.items()})
  self.assertEqual(response.status_code,422)
  self.assertEqual(response.json()['detail'],'Ngày phát hành không hợp lệ')

 def test_new_document_types_can_be_created_and_reserved(self):
  for kind in api.DOCUMENT_TYPE_CODES:
   with self.subTest(kind=kind):
    did=self.create(kind)
    self.assertEqual(self.session.get(api.Document,did).doc_type,kind)
    response=self.client.post('/api/reserve-number',data={'direction':'OUT','doc_type':kind,'title':'Reserve','reason':'Prepare'})
    self.assertEqual(response.status_code,200,response.text)
    self.uid=4
    approved=self.client.post(f"/api/documents/{response.json()['id']}/reservation-decision",json={'decision':'APPROVE','revision':1})
    self.assertEqual(approved.status_code,200,approved.text)
    self.assertEqual(approved.json()['symbol'],api.number_symbol(kind,1,date.today(),'OUT'))

 def test_reservation_dates(self):
  self.uid=1
  for direction,kind in [('OUT','CÔNG VĂN'),('INTERNAL','QUYẾT ĐỊNH')]:
   payload={'direction':direction,'doc_type':kind,'title':'Reserved document','reason':'Prepare document','issued_date':'2026-09-20'}
   response=self.client.post('/api/reserve-number',data=payload)
   self.assertEqual(response.status_code,200,response.text)
   document=response.json()
   self.assertEqual(document['issued_date'],'2026-09-20')
   self.assertTrue(document['created_at'])
   self.assertTrue(document['reserved'])
   payload['issued_date']='invalid'
   self.assertEqual(self.client.post('/api/reserve-number',data=payload).status_code,422)
  response=self.client.post('/api/incoming/reserve-number',data={'title':'Incoming','reason':'Prepare','issued_date':'2026-09-20'})
  self.assertIn(response.status_code,(404,405),response.text)

 def test_docx_create_edit_preview_and_reserved_upload(self):
  with patch('backend.document_upload.convert_docx',return_value=self.pdf):
   files={'file':('document.docx',b'word','application/vnd.openxmlformats-officedocument.wordprocessingml.document')}
   for kind in ['CÔNG VĂN','QUYẾT ĐỊNH','KẾ HOẠCH','THÔNG BÁO']:
    self.uid=1
    agency='External' if kind=='CÔNG VĂN' else next(iter(api.INTERNAL_UNITS))
    response=self.client.post('/api/documents',data={'direction':'OUT','doc_type':kind,'title':'Word','issuing_agency':agency},files=files)
    self.assertEqual(response.status_code,200,response.text)
    item=response.json()
    self.assertEqual(Path(item['file_path']).read_bytes(),self.pdf)
    self.assertTrue(item['file_name'].endswith('.pdf'))
    edited=self.client.post(f"/api/documents/{item['id']}/edit-outgoing",data={'title':'Updated','issuing_agency':agency},files=files)
    self.assertEqual(edited.status_code,200,edited.text)
   preview=self.client.post('/api/documents/preview-upload',files=files)
   self.assertEqual(preview.status_code,200,preview.text)
   self.assertEqual(preview.content,self.pdf)
   self.uid=4
   incoming=self.client.post('/api/documents',data={'direction':'IN','title':'Incoming','issuing_agency':'External','issued_date':'2026-09-15'},files=files)
   self.assertEqual(incoming.status_code,200,incoming.text)
   edited=self.client.post(f"/api/documents/{incoming.json()['id']}/edit-received",data={'title':'Updated','issuing_agency':'External','issued_date':'2026-09-15'},files=files)
   self.assertEqual(edited.status_code,200,edited.text)
   self.uid=1
   for direction,kind in [('OUT','CÔNG VĂN'),('INTERNAL','QUYẾT ĐỊNH')]:
    reserved=self.client.post('/api/reserve-number',data={'direction':direction,'doc_type':kind,'title':'Reserve','reason':'Prepare'})
    self.assertEqual(reserved.status_code,200,reserved.text)
    self.uid=4
    approved=self.client.post(f"/api/documents/{reserved.json()['id']}/reservation-decision",json={'decision':'APPROVE','revision':1})
    self.assertEqual(approved.status_code,200,approved.text)
    self.uid=1
    attached=self.client.post(f"/api/documents/{reserved.json()['id']}/attach-reserved",data={'issued_date':'2026-09-15','issuing_agency':next(iter(api.INTERNAL_UNITS))},files=files)
    self.assertEqual(attached.status_code,200,attached.text)
    self.assertEqual(Path(attached.json()['file_path']).read_bytes(),self.pdf)

 def test_archive_with_or_without_email(self):
  self.uid=4
  for direction,status in [('OUT','SEALED'),('OUT','EMAILED'),('INTERNAL','INTERNAL_SEALED'),('INTERNAL','INTERNAL_PUBLISHED'),('IN','REVIEW_READY'),('IN','FORWARDED')]:
   document=api.Document(direction=direction,doc_type='CÔNG VĂN',title='Archive',owner_id=4,department_id=1,status=status,sealed=direction!='IN',file_path=str(self.root/'archive-source.pdf'),file_name='source.pdf')
   (self.root/'archive-source.pdf').write_bytes(self.pdf)
   self.session.add(document);self.session.flush()
   if direction=='IN':
    self.session.add(api.IncomingReview(document_id=document.id,revision=1,note='Approved',assignments='[{"department_id":2}]',decisions='{"BGH":{"decision":"APPROVE"},"2":{"decision":"APPROVE"}}',pdf_path=document.file_path,created_by=4))
   self.session.commit()
   with patch.object(api,'ocr_pdf',return_value='Text'),patch.object(api,'archive_file'),patch.object(api,'incoming_source',return_value=None),patch.object(api,'send_document_email') as send:
    response=self.client.post(f'/api/documents/{document.id}/action',json={'action':'ARCHIVE'})
    self.assertEqual(response.status_code,200,response.text)
    self.assertEqual(response.json()['status'],'ARCHIVED')
    send.assert_not_called()
   event=self.session.query(api.Action).filter_by(document_id=document.id,action='ARCHIVE').one()
   self.assertIn('không gửi mail' if status in {'SEALED','INTERNAL_SEALED','REVIEW_READY'} else 'sau khi gửi mail',event.comment)
  for direction,status in [('OUT','DRAFT'),('OUT','OUT_NUMBERED'),('INTERNAL','INTERNAL_APPROVED'),('IN','PENDING_BGH'),('IN','REVIEW_READY')]:
   document=api.Document(direction=direction,doc_type='CÔNG VĂN',title='Not ready',owner_id=4,status=status)
   self.session.add(document);self.session.commit()
   response=self.client.post(f'/api/documents/{document.id}/action',json={'action':'ARCHIVE'})
   self.assertEqual(response.status_code,409,response.text)

 def test_limited_roles_cannot_access_office_modules(self):
  did=self.create()
  for uid in [1,2,3]:
   self.uid=uid
   for endpoint in ['/api/dashboard','/api/dashboard/meeting-report?start=2026-01-01&end=2026-12-31','/api/documents?archive_workspace=true','/api/documents?status=ARCHIVED','/api/reports/tracking','/api/ai/status','/api/register/export?year=2026']:
    self.assertEqual(self.client.get(endpoint).status_code,403,endpoint)
   upload=self.client.post('/api/archive/uploads',data={'folder':'BÁO CÁO'},files={'file':('file.pdf',self.pdf,'application/pdf')})
   self.assertEqual(upload.status_code,403)
  self.uid=3
  config=self.client.get('/api/config').json()
  self.assertNotIn('VIEW_ALL',config['permissions'])
  self.assertNotIn('AI_CHAT',config['permissions'])
  self.assertEqual(self.client.get(f'/api/documents/{did}/file').status_code,404)
  self.assertEqual(self.client.get('/api/documents?direction=OUT').json(),[])
  self.uid=1
  self.submit_bgh(did,'SIGN')
  self.uid=3
  self.assertTrue(any(row['id']==did for row in self.client.get('/api/documents?direction=OUT').json()))
  self.assertEqual(self.client.get(f'/api/documents/{did}/file').status_code,200)

 def create(self,kind='CÔNG VĂN'):
  self.uid=1
  recipient=next(iter(api.INTERNAL_UNITS)) if kind!='CÔNG VĂN' else 'External recipient'
  r=self.client.post('/api/documents',data={'direction':'OUT','doc_type':kind,'title':'Test','issuing_agency':recipient},files={'file':('test.pdf',self.pdf,'application/pdf')})
  self.assertEqual(r.status_code,200,r.text);self.assertIsNone(r.json()['issued_date']);return r.json()['id']
 def post(self,did,action,uid,data=None):
  self.uid=uid
  if action=='outgoing-number' and data is None:data={'placement':json.dumps({'number':{'x':10,'y':12,'width':8,'height':3},'date':{'x':50,'y':12,'width':45,'height':3}})}
  return self.client.post(f'/api/documents/{did}/{action}',data=data)
 def sign(self,did,uid,y=65):return self.post(did,'digital-sign',uid,{'page':1,'x_percent':55,'y_percent':y,'note':'BGH đồng ý ban hành' if uid==3 else ''})
 def submit_bgh(self,did,mode='APPROVE'):return self.post(did,'outgoing-submit',1,{'bgh_action':mode})
 def approve_bgh(self,did,note='BGH đồng ý ban hành'):return self.post(did,'outgoing-bgh-approve',3,{'note':note})
 def test_shared_flow_and_gates(self):
  self.assertEqual(api.ROLE_DEFAULTS['DEPARTMENT'],{'CREATE','EDIT','SIGN','RESERVE_NUMBER'})
  for kind in ['CÔNG VĂN','QUYẾT ĐỊNH','KẾ HOẠCH','THÔNG BÁO']:
   did=self.create(kind)
   self.assertEqual(self.submit_bgh(did).status_code,409)
   self.assertEqual(self.sign(did,1).status_code,200)
   self.assertEqual(self.sign(did,5).status_code,404)
   self.assertEqual(self.post(did,'outgoing-number',4).status_code,409)
   self.assertEqual(self.submit_bgh(did).status_code,200)
   self.assertEqual(self.sign(did,3,80).status_code,409)
   self.assertEqual(self.post(did,'outgoing-bgh-approve',3).status_code,422)
   self.assertEqual(self.approve_bgh(did).status_code,200)
   approval=self.session.query(api.Action).filter_by(document_id=did,action='OUTGOING_BGH_APPROVE').one()
   self.assertEqual(json.loads(approval.comment)['note'],'BGH đồng ý ban hành')
   self.assertEqual(self.sign(did,3).status_code,409)
   d=self.session.get(api.Document,did)
   with api.pymupdf.open(d.file_path) as pdf:self.assertEqual(pdf[0].get_text().count('DA KY SO'),1)
   self.assertEqual(self.session.query(api.DigitalSignature).filter_by(document_id=did).count(),1)
   numbered=self.post(did,'outgoing-number',4)
   self.assertEqual(numbered.status_code,200,numbered.text)
   self.assertEqual(numbered.json()['issued_date'],date.today().isoformat())
   self.assertEqual(numbered.json()['doc_type'],kind)
   self.assertEqual(numbered.json()['symbol'],f"01/{date.today().year}/"+('ĐHHV' if kind=='CÔNG VĂN' else api.DOC_TYPE_CODES[kind]+'-ĐHHV'))
   with patch.object(api,'ARCHIVE_ROOT',self.root/'archive'):
    api.archive_file(d)
    self.assertEqual(Path(d.file_path).parent.name,'CÔNG VĂN ĐI' if kind=='CÔNG VĂN' else kind)
   self.assertEqual(self.post(did,'outgoing-number',4).status_code,409)
   with api.pymupdf.open(d.file_path) as pdf:self.assertEqual(len(pdf),1)
   mail={'emails':'test@example.com','subject':'Test','content_html':'<p>Test</p>','signature_html':'<p>VP</p>'}
   self.assertEqual(self.post(did,'outgoing-email',4,mail).status_code,409)
   self.assertEqual(self.post(did,'digital-seal',4,{'seal_type':'SCHOOL','page':1,'x_percent':60,'y_percent':80}).status_code,200)
   with patch.object(api,'send_document_email') as send:
    draft=self.post(did,'outgoing-email',4,mail)
    self.assertEqual(draft.status_code,200,draft.text);send.assert_not_called()
    self.assertEqual(draft.json()['email_status'],'draft')
    self.assertEqual(draft.json()['document']['status'],'SEALED')
    confirm=self.client.post(f'/api/documents/{did}/gmail-confirm',json={'revision':draft.json()['document']['revision']})
    self.assertEqual(confirm.status_code,200,confirm.text)
    self.assertEqual(confirm.json()['status'],'EMAILED')
    self.assertEqual(self.client.post(f'/api/documents/{did}/gmail-confirm',json={'revision':1}).status_code,409)
  self.uid=4
  rows=self.client.get('/api/documents?direction=OUT').json()
  self.assertEqual(len(rows),4);self.assertEqual(sorted(d['number'] for d in rows),[1,1,1,1])
 def test_return_edit_and_resign(self):
  did=self.create();self.sign(did,2);self.submit_bgh(did)
  self.assertEqual(self.post(did,'outgoing-return',3,{'note':'Please revise'}).status_code,200)
  d=self.session.get(api.Document,did)
  self.assertEqual(d.revision,2)
  event=self.session.query(api.Action).filter_by(document_id=did,action='OUTGOING_RETURN').one()
  self.assertEqual(json.loads(event.comment),{'actor':'BGH','from_revision':1,'to_revision':2,'reason':'Please revise'})
  r=self.post(did,'edit-outgoing',1,{'title':'Revised','issuing_agency':'External'})
  self.assertEqual(r.status_code,200,r.text)
  edit_event=self.session.query(api.Action).filter_by(document_id=did,action='EDIT_OUTGOING').one()
  self.assertEqual(edit_event.comment,'Cập nhật phiên bản 2')
  self.assertEqual(self.sign(did,2).status_code,200)
  self.submit_bgh(did);self.assertEqual(self.approve_bgh(did).status_code,200)
  d=self.session.get(api.Document,did)
  with api.pymupdf.open(d.file_path) as pdf:self.assertEqual(pdf[0].get_text().count('DA KY SO'),1)

 def test_unsigned_document_is_signed_by_bgh_then_sent_to_clerk(self):
  did=self.create()
  self.assertEqual(self.submit_bgh(did,'SIGN').status_code,200)
  self.assertEqual(self.sign(did,1).status_code,403)
  self.assertEqual(self.post(did,'digital-sign',3,{'page':1,'x_percent':55,'y_percent':80}).status_code,422)
  self.assertEqual(self.sign(did,3,80).status_code,200)
  d=self.session.get(api.Document,did)
  self.assertEqual(d.status,'READY_FOR_CLERK')
  self.assertEqual(self.session.query(api.DigitalSignature).filter_by(document_id=did).count(),1)
  event=self.session.query(api.Action).filter_by(document_id=did,action='BGH_DIGITAL_SIGN').one()
  self.assertEqual(json.loads(event.comment)['note'],'BGH đồng ý ban hành')
  self.uid=4
  self.assertTrue(any(item['document_id']==did and item['status']=='READY_FOR_CLERK' for item in self.client.get('/api/notifications').json()))

 def test_accounts_and_legacy_visibility(self):
  denied=self.client.post('/api/documents',data={'direction':'IN','doc_type':'CÔNG VĂN','title':'Không được tạo','issuing_agency':'Bộ Giáo dục'})
  self.assertEqual(denied.status_code,403)
  payload={'username':'new_head','full_name':'New Head','password':'test-password','role':'DEPARTMENT_HEAD','department_id':2}
  self.assertEqual(self.client.post('/api/config/users',json=payload).status_code,403)
  admin=api.User(id=6,username='test_admin',full_name='Admin',password_hash='unused',role='ADMIN',active=True,department_id=1)
  self.session.add(admin);self.session.commit();self.users[6]=admin;self.uid=6
  self.assertEqual(self.client.post('/api/config/users',json=payload).status_code,200)
  self.assertEqual(self.client.post('/api/config/users',json=payload).status_code,409)
  created=self.client.post('/api/documents',data={'direction':'IN','doc_type':'CÔNG VĂN','title':'Công văn do Admin tiếp nhận','issuing_agency':'Bộ Giáo dục','issued_date':'2026-09-12'},files={'file':('incoming.pdf',self.pdf,'application/pdf')})
  self.assertEqual(created.status_code,200,created.text)
  self.session.add(api.Document(direction='INTERNAL',doc_type='THÔNG BÁO',title='Legacy',owner_id=6,status='INTERNAL_PUBLISHED'))
  self.session.commit()
  rows=self.client.get('/api/documents?direction=OUT').json()
  self.assertEqual(rows[0]['title'],'Legacy')

 def test_document_search_accumulates_an_ordered_phrase(self):
  did=self.create();d=self.session.get(api.Document,did)
  d.title='Xác minh văn bằng';d.summary='Gửi Bộ Giáo dục';api.refresh_search(d);self.session.commit()
  self.uid=1
  rows=self.client.get('/api/documents?direction=OUT&q=xac%20minh').json()
  self.assertEqual([row['id'] for row in rows],[did])
  self.assertEqual([row['id'] for row in self.client.get('/api/documents?direction=OUT&q=xac').json()],[did])
  self.assertEqual(self.client.get('/api/documents?direction=OUT&q=minh%20xac').json(),[])
  self.assertEqual(self.client.get('/api/documents?direction=OUT&q=khongco').json(),[])
 def test_number_uses_office_receipt_date(self):
  did=self.create();self.sign(did,2);self.submit_bgh(did);self.approve_bgh(did)
  d=self.session.get(api.Document,did);d.received_date=date(2025,12,31);self.session.commit()
  r=self.post(did,'outgoing-number',4)
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.json()['issued_date'],'2025-12-31')
  self.assertIsNotNone(self.session.query(api.Sequence).filter_by(year=2025,doc_type='CÔNG VĂN ĐI').first())

 def test_inline_numbering_native_and_scanned(self):
  placement=api.NumberPlacement(number=api.NumberRegion(x=10,y=10,width=8,height=4),date=api.NumberRegion(x=50,y=10,width=45,height=4))
  for scanned in (False,True):
   original=api.pymupdf.open();page=original.new_page(width=600,height=800)
   page.insert_text((60,100),'588',fontsize=12)
   page.insert_text((300,100),'old date',fontsize=12)
   page.insert_text((60,300),'KEEP BODY AND SIGNATURE',fontsize=12)
   if scanned:
    pix=page.get_pixmap();original.close();original=api.pymupdf.open();page=original.new_page(width=600,height=800);page.insert_image(page.rect,pixmap=pix)
   source=self.root/f'inline-{scanned}.pdf';original.save(source);original.close()
   output=api.render_outgoing_number(source,589,date(2026,9,10),placement)
   with api.pymupdf.open(stream=output,filetype='pdf') as result, api.pymupdf.open(source) as before:
    self.assertEqual(len(result),1)
    text=result[0].get_text();self.assertIn('589',text);self.assertIn('2026',text);self.assertNotIn('588',text);self.assertNotIn('old date',text)
    spans=[span for block in result[0].get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans'] if span['text'].strip()=='589']
    self.assertTrue(spans)
    self.assertAlmostEqual(spans[0]['size'],14,places=1)
    clip=api.pymupdf.Rect(0,150,600,800)
    self.assertEqual(result[0].get_pixmap(clip=clip).samples,before[0].get_pixmap(clip=clip).samples)

 def test_native_pdf_number_and_date_positions_are_detected_automatically(self):
  pdf=api.pymupdf.open();page=pdf.new_page(width=600,height=800)
  page.insert_text((60,100),'Số:',fontsize=12);page.insert_text((95,100),'588/2024/QĐ-ĐHHV',fontsize=12)
  page.insert_text((330,100),'TP. Hồ Chí Minh, ngày 27 tháng 11 năm 2024',fontsize=12)
  source=self.root/'auto-placement.pdf';pdf.save(source);pdf.close()
  placement=api.detect_outgoing_number_placement(source)
  self.assertGreater(placement.date.x,placement.number.x)
  output=api.render_outgoing_number(source,589,date(2026,9,10),placement)
  with api.pymupdf.open(stream=output,filetype='pdf') as result:
   text=result[0].get_text();self.assertIn('589',text);self.assertIn('ngày 10 tháng 09 năm 2026',text)
 def test_invalid_placement_does_not_allocate_number(self):
  did=self.create();self.sign(did,2);self.submit_bgh(did);self.approve_bgh(did)
  r=self.post(did,'outgoing-number',4,{'placement':'{}'})
  self.assertEqual(r.status_code,422)
  self.assertEqual(self.session.get(api.Document,did).status,'READY_FOR_CLERK')
  self.assertEqual(self.session.query(api.Sequence).count(),0)

 def test_preview_does_not_allocate_and_render_failure_rolls_back(self):
  did=self.create();self.sign(did,2);self.submit_bgh(did);self.approve_bgh(did)
  data={'placement':json.dumps({'number':{'x':10,'y':12,'width':8,'height':3},'date':{'x':50,'y':12,'width':45,'height':3}})}
  response=self.post(did,'outgoing-number-preview',4,data)
  self.assertEqual(response.status_code,200);self.assertTrue(response.content.startswith(b'\x89PNG'))
  self.assertEqual(self.session.query(api.Sequence).count(),0)
  with patch.object(api,'render_outgoing_number',side_effect=api.HTTPException(422,'Too small')):
   self.assertEqual(self.post(did,'outgoing-number',4,data).status_code,422)
  self.assertEqual(self.session.query(api.Sequence).count(),0)
  self.assertEqual(self.session.get(api.Document,did).status,'READY_FOR_CLERK')

 def test_selected_issue_date_is_preserved(self):
  self.uid=1
  r=self.client.post('/api/documents',data={'direction':'OUT','doc_type':'CÔNG VĂN','title':'Dated document','issuing_agency':'External','issued_date':'2024-11-27'},files={'file':('test.pdf',self.pdf,'application/pdf')})
  self.assertEqual(r.status_code,200,r.text);did=r.json()['id']
  self.assertEqual(r.json()['issued_date'],'2024-11-27')
  r=self.post(did,'edit-outgoing',1,{'title':'Edited','issuing_agency':'External','issued_date':'2025-12-20'})
  self.assertEqual(r.status_code,200,r.text)
  self.sign(did,2);self.submit_bgh(did);self.approve_bgh(did)
  r=self.post(did,'outgoing-number',4)
  self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['issued_date'],'2025-12-20')
