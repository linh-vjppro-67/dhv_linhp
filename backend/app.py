from __future__ import annotations
import hashlib,json,os,uuid,io,shutil,re,unicodedata,smtplib,html,base64
from html.parser import HTMLParser
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent/'.env')
from email.message import EmailMessage
from datetime import date,datetime,timedelta
from typing import Optional
import pymupdf
import pytesseract
from PIL import Image
from docx import Document as WordDocument
from fastapi import Depends,FastAPI,File,Form,HTTPException,UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse,Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError,jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import Boolean,Date,DateTime,Float,ForeignKey,Integer,String,Text,UniqueConstraint,create_engine,or_
from sqlalchemy.orm import DeclarativeBase,Mapped,Session,mapped_column,sessionmaker
ROOT=Path(__file__).parent;STORE=ROOT/'storage';STORE.mkdir(exist_ok=True);ARCHIVE_ROOT=ROOT/'archive';ARCHIVE_ROOT.mkdir(exist_ok=True)
DOC_TYPE_CODES={'QUYẾT ĐỊNH':'QD','THÔNG BÁO':'TB','KẾ HOẠCH':'KH','CÔNG VĂN':'CV'}
INTERNAL_UNITS={
 'Khoa Quản trị Kinh doanh – Marketing','Khoa Ngôn ngữ','Khoa Tài chính – Ngân hàng – Kế toán','Khoa Khoa học Sức khỏe','Khoa Luật','Khoa Khoa học Liên ngành','Khoa Kỹ thuật – Công nghệ','Khoa Du lịch – Nhà hàng – Khách sạn',
 'Viện Đào tạo Sau đại học','Viện Liên kết Giáo dục và Đào tạo từ xa','Viện Công nghệ tiên tiến và Trí tuệ nhân tạo DHV','Viện Văn hóa Doanh nghiệp','Viện Y dược Sài Gòn','Trung tâm Công nghệ','Trung tâm Tuyển sinh','Trung tâm Học liệu','Vườn ươm Khởi nghiệp DHV','Tạp chí Khoa học Trường Đại học Hùng Vương TP. Hồ Chí Minh',
 'Văn phòng Trường','Văn phòng Đảng, đoàn thể','Phòng Đào tạo','Phòng Khảo thí và Quản lý chất lượng','Phòng Quản lý Khoa học','Phòng Công tác sinh viên và Xã hội','Phòng Tài chính - Kế toán','Phòng Hợp tác và Phát triển','Phòng Truyền thông','Phòng Pháp chế và Quản trị tri thức'
}
def normalize_search(value:str)->str:
 value=(value or '').replace('Đ','D').replace('đ','d').casefold()
 return ' '.join(''.join(c for c in unicodedata.normalize('NFD',value) if unicodedata.category(c)!='Mn').split())
def number_symbol(doc_type:str,number:int,when:date,direction:Optional[str]=None):
 code='CVDEN' if doc_type=='CÔNG VĂN' and direction=='IN' else 'CVĐI' if doc_type=='CÔNG VĂN' and direction=='OUT' else DOC_TYPE_CODES.get(doc_type,doc_type)
 return f'{code} {number:02d}-{when.year%100:02d}, {when.day:02d}-{when.month:02d}'
def file_title_part(name:str)->str:
 stem=Path(name or '').stem.strip()
 return re.sub(r'^[A-ZĐ]+\s+\d+-\d{2},\s*\d{2}-\d{2}\s*','',stem,flags=re.IGNORECASE).strip()
def safe_file_title(title:str)->str:
 value=re.sub(r'[\\/:*?"<>|\0]+',' ',(title or '').strip())
 value=' '.join(value.split()).strip(' .')
 return (value or 'Văn bản')[:180].rstrip(' .')
def numbered_file_name(symbol:str,title:str)->str:
 return f'{safe_file_title(symbol)} {safe_file_title(title)}.pdf'
def document_file_name(title:str,symbol:Optional[str]=None)->str:
 return numbered_file_name(symbol,title) if symbol else f'{safe_file_title(title)}.pdf'
def clean_workflow_suffixes(name:str)->str:
 if not name:return name
 suffix=Path(name).suffix or '.pdf';stem=Path(name).stem
 while True:
  cleaned=re.sub(r'-(?:office-opinion-signed|office-opinion|signed|sealed)$','',stem,flags=re.IGNORECASE)
  if cleaned==stem:break
  stem=cleaned
 return f'{stem}{suffix}'
engine=create_engine(f"sqlite:///{ROOT/'dhv.db'}",connect_args={'check_same_thread':False});DB=sessionmaker(bind=engine,expire_on_commit=False)
SECRET=os.getenv('SECRET_KEY','change-me-production');pwd=CryptContext(schemes=['pbkdf2_sha256'],deprecated='auto');oauth=OAuth2PasswordBearer(tokenUrl='/api/auth/login')
class Base(DeclarativeBase):pass
class Department(Base):
 __tablename__='departments';id:Mapped[int]=mapped_column(primary_key=True);name:Mapped[str]=mapped_column(unique=True);code:Mapped[str]=mapped_column(unique=True)
class User(Base):
 __tablename__='users';id:Mapped[int]=mapped_column(primary_key=True);username:Mapped[str]=mapped_column(unique=True);full_name:Mapped[str];password_hash:Mapped[str];role:Mapped[str];department_id:Mapped[Optional[int]]=mapped_column(ForeignKey('departments.id'));active:Mapped[bool]=mapped_column(Boolean,default=True)
class Sequence(Base):
 __tablename__='sequences';__table_args__=(UniqueConstraint('year','doc_type'),);id:Mapped[int]=mapped_column(primary_key=True);year:Mapped[int];doc_type:Mapped[str];current:Mapped[int]=mapped_column(default=0);prefix:Mapped[str]
class Document(Base):
 __tablename__='managed_documents';id:Mapped[int]=mapped_column(primary_key=True);direction:Mapped[str];doc_type:Mapped[str];number:Mapped[Optional[int]];symbol:Mapped[Optional[str]];title:Mapped[str];summary:Mapped[str]=mapped_column(Text,default='');issuing_agency:Mapped[str]=mapped_column(default='');issued_date:Mapped[Optional[date]]=mapped_column(Date);received_date:Mapped[Optional[date]]=mapped_column(Date);status:Mapped[str]=mapped_column(default='DRAFT');priority:Mapped[str]=mapped_column(default='Bình thường');owner_id:Mapped[int]=mapped_column(ForeignKey('users.id'));department_id:Mapped[Optional[int]]=mapped_column(ForeignKey('departments.id'));assignee_ids:Mapped[str]=mapped_column(default='[]');file_name:Mapped[Optional[str]];file_path:Mapped[Optional[str]];ocr_text:Mapped[str]=mapped_column(Text,default='');search_text:Mapped[str]=mapped_column(Text,default='');reserved:Mapped[bool]=mapped_column(Boolean,default=False);signed_personal:Mapped[bool]=mapped_column(Boolean,default=False);sealed:Mapped[bool]=mapped_column(Boolean,default=False);signature_hash:Mapped[Optional[str]];created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow);updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class Action(Base):
 __tablename__='actions';id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'));user_id:Mapped[int]=mapped_column(ForeignKey('users.id'));action:Mapped[str];comment:Mapped[str]=mapped_column(default='');created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class DigitalSignature(Base):
 __tablename__='digital_signatures';id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'));user_id:Mapped[int]=mapped_column(ForeignKey('users.id'));page:Mapped[int]=mapped_column(default=1);x_percent:Mapped[float]=mapped_column(Float);y_percent:Mapped[float]=mapped_column(Float);file_hash:Mapped[str];created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class DigitalSeal(Base):
 __tablename__='digital_seals';id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'));user_id:Mapped[int]=mapped_column(ForeignKey('users.id'));seal_type:Mapped[str];page:Mapped[int]=mapped_column(default=1);x_percent:Mapped[float]=mapped_column(Float);y_percent:Mapped[float]=mapped_column(Float);file_hash:Mapped[str];created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class DocumentSource(Base):
 __tablename__='document_sources';id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'),unique=True);file_path:Mapped[str];file_name:Mapped[str]
class IncomingNumber(Base):
 __tablename__='incoming_numbers';__table_args__=(UniqueConstraint('year','doc_type','number'),);id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'),unique=True);year:Mapped[int];doc_type:Mapped[str];number:Mapped[int]
class DeletedRecord(Base):
 __tablename__='deleted_records';id:Mapped[int]=mapped_column(primary_key=True);document_id:Mapped[int]=mapped_column(ForeignKey('managed_documents.id'),unique=True);previous_status:Mapped[str];deleted_by:Mapped[int]=mapped_column(ForeignKey('users.id'));reason:Mapped[str];deleted_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class EmailSetting(Base):
 __tablename__='email_settings';id:Mapped[int]=mapped_column(primary_key=True);smtp_host:Mapped[str]=mapped_column(default='');smtp_port:Mapped[int]=mapped_column(default=587);username:Mapped[str]=mapped_column(default='');sender_name:Mapped[str]=mapped_column(default='Đại học Hùng Vương');sender_email:Mapped[str]=mapped_column(default='');signature_html:Mapped[str]=mapped_column(Text,default='');use_tls:Mapped[bool]=mapped_column(Boolean,default=True);enabled:Mapped[bool]=mapped_column(Boolean,default=False);updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
class RolePermission(Base):
 __tablename__='role_permissions';__table_args__=(UniqueConstraint('role','permission'),);id:Mapped[int]=mapped_column(primary_key=True);role:Mapped[str];permission:Mapped[str];enabled:Mapped[bool]=mapped_column(Boolean,default=True)
Base.metadata.create_all(engine)
with engine.begin() as conn:
 columns={row[1] for row in conn.exec_driver_sql('PRAGMA table_info(managed_documents)')}
 if 'search_text' not in columns:conn.exec_driver_sql("ALTER TABLE managed_documents ADD COLUMN search_text TEXT NOT NULL DEFAULT ''")
 email_columns={row[1] for row in conn.exec_driver_sql('PRAGMA table_info(email_settings)')}
 if 'signature_html' not in email_columns:conn.exec_driver_sql("ALTER TABLE email_settings ADD COLUMN signature_html TEXT NOT NULL DEFAULT ''")
def db():
 s=DB()
 try:yield s
 finally:s.close()
def seed():
 s=DB()
 if not s.query(User).count():
  ds=[Department(name=n,code=c) for n,c in [('Ban Giám hiệu','BGH'),('Văn phòng','VP'),('Phòng Đào tạo','PDT'),('Phòng Tài chính - Kế toán','TCKT'),('Phòng Công tác sinh viên','CTSV')]];s.add_all(ds);s.flush()
  for u,n,r,d in [('admin','Quản trị hệ thống','ADMIN',1),('hieu_truong','Hiệu trưởng Nguyễn Văn A','BGH',1),('truong_vp','Trưởng Văn phòng','OFFICE_HEAD',2),('van_thu','Chuyên viên Văn thư','CLERK',2),('phong_dao_tao','Chuyên viên Đào tạo','DEPARTMENT',3)]:s.add(User(username=u,full_name=n,role=r,department_id=d,password_hash=pwd.hash('123456')))
  for t,p in [('QUYẾT ĐỊNH','QĐ-DHV'),('THÔNG BÁO','TB-DHV'),('CÔNG VĂN','DHV'),('KẾ HOẠCH','KH-DHV')]:s.add(Sequence(year=date.today().year,doc_type=t,prefix=p))
  s.commit()
 s.close()
seed();app=FastAPI(title='DHV - Quản lý văn bản',version='1.0');app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
with DB() as admin_session:
 admin_account=admin_session.query(User).filter_by(username='admin').first()
 if admin_account and (not admin_account.active or admin_account.role!='ADMIN'):
  admin_account.active=True;admin_account.role='ADMIN';admin_session.commit()
class Login(BaseModel):username:str;password:str
class Act(BaseModel):action:str;comment:str='';department_ids:list[int]=[]
class Reserve(BaseModel):doc_type:str;year:int=date.today().year;quantity:int=1
class RenameFile(BaseModel):name:str
class UserConfig(BaseModel):full_name:str;role:str;department_id:Optional[int]=None;active:bool=True
class EmailConfig(BaseModel):smtp_host:str='';smtp_port:int=587;username:str='';sender_name:str='Đại học Hùng Vương';sender_email:str='';signature_html:str='';use_tls:bool=True;enabled:bool=False
class PermissionConfig(BaseModel):role:str;permissions:list[str]
def current(token=Depends(oauth),s:Session=Depends(db)):
 try:uid=int(jwt.decode(token,SECRET,algorithms=['HS256'])['sub'])
 except (JWTError,KeyError):raise HTTPException(401,'Phiên đăng nhập không hợp lệ')
 u=s.get(User,uid)
 if not u or not u.active:raise HTTPException(401,'Tài khoản bị khóa')
 return u
PERMISSION_LABELS={'VIEW_ALL':'Xem toàn bộ hồ sơ','CREATE':'Tạo và tiếp nhận văn bản','EDIT':'Sửa và bổ sung văn bản','RESERVE_NUMBER':'Xin số trước','ASSIGN_NUMBER':'Cấp số văn bản','OFFICE_OPINION':'Ý kiến Trưởng Văn phòng','INTERNAL_APPROVE':'Phê duyệt văn bản nội bộ','SEND_BGH':'Trình Ban Giám hiệu','BGH_DECIDE':'Duyệt hoặc từ chối','FORWARD':'Chuyển đơn vị xử lý','SIGN':'Ký số','SEAL':'Đóng dấu','EMAIL':'Phát hành qua email','ARCHIVE':'Lưu trữ và OCR','RENAME':'Đổi tên file','DELETE':'Xóa có lý do','RESTORE':'Khôi phục văn bản','MANAGE_USERS':'Quản lý người dùng','MANAGE_PERMISSIONS':'Cấu hình phân quyền','MANAGE_EMAIL':'Cấu hình email','VIEW_ACTIVITY':'Xem activity log'}
ROLE_DEFAULTS={'ADMIN':set(PERMISSION_LABELS),'BGH':{'VIEW_ALL','BGH_DECIDE'},'OFFICE_HEAD':{'VIEW_ALL','OFFICE_OPINION','INTERNAL_APPROVE','SIGN'},'CLERK':{'VIEW_ALL','CREATE','EDIT','RESERVE_NUMBER','ASSIGN_NUMBER','SEND_BGH','FORWARD','SEAL','EMAIL','ARCHIVE','RENAME','DELETE'},'DEPARTMENT':set()}
def has_permission(s,u,permission):
 if u.role=='ADMIN':return True
 if permission not in ROLE_DEFAULTS.get(u.role,set()):return False
 row=s.query(RolePermission).filter_by(role=u.role,permission=permission).first()
 return row.enabled if row else permission in ROLE_DEFAULTS.get(u.role,set())
def require_permission(s,u,permission,message='Bạn không có quyền thực hiện thao tác này'):
 if not has_permission(s,u,permission):raise HTTPException(403,message)
def view(u,d,s=None):return (has_permission(s,u,'VIEW_ALL') if s else u.role in {'ADMIN','BGH','OFFICE_HEAD','CLERK'}) or u.id==d.owner_id or (u.department_id is not None and (u.department_id==d.department_id or u.department_id in json.loads(d.assignee_ids or '[]')))
def require_document_access(s,u,d):
 if not view(u,d,s):raise HTTPException(404,'Không tìm thấy văn bản')
def out(d):return {c.name:getattr(d,c.name) for c in d.__table__.columns if c.name!='search_text'}
def refresh_search(d):d.search_text=normalize_search(' '.join(str(x or '') for x in (d.symbol,d.title,d.summary,d.issuing_agency,d.file_name,d.ocr_text)))
class EmailHTMLSanitizer(HTMLParser):
 allowed={'p','div','br','b','strong','i','em','u','ul','ol','li','blockquote','span','font','img'}
 styles={'font-weight','font-style','text-decoration','font-size','font-family','color','margin-left','text-align'}
 def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
 def handle_starttag(self,tag,attrs):
  if tag not in self.allowed:return
  clean=[]
  for key,value in attrs:
   if tag=='img' and key=='src' and (value.startswith('data:image/png;base64,') or value.startswith('data:image/jpeg;base64,') or value.startswith('data:image/gif;base64,')):clean.append(('src',value))
   elif tag=='img' and key in {'alt','width','height'} and re.fullmatch(r'[\w .,%()\-À-ỹ]*',value or ''):clean.append((key,value))
   elif tag=='font' and key in {'size','color','face'} and re.fullmatch(r'[\w #(),.%\-À-ỹ]*',value or ''):clean.append((key,value))
   elif key=='style':
    declarations=[]
    for item in (value or '').split(';'):
     name,sep,val=item.partition(':');name=name.strip().lower();val=val.strip()
     if sep and name in self.styles and not re.search(r'url|expression|javascript',val,re.I):declarations.append(f'{name}:{val}')
    if declarations:clean.append(('style',';'.join(declarations)))
  rendered=''.join(f' {k}="{html.escape(v,quote=True)}"' for k,v in clean);self.parts.append(f'<{tag}{rendered}>')
 def handle_endtag(self,tag):
  if tag in self.allowed and tag not in {'br','img'}:self.parts.append(f'</{tag}>')
 def handle_data(self,data):self.parts.append(html.escape(data))

def clean_email_html(value:str)->str:
 parser=EmailHTMLSanitizer();parser.feed(value or '');return ''.join(parser.parts).strip()
def constrain_signature_images(value:str,max_width:int=100)->str:
 def resize(match):
  tag=match.group(0);source=re.search(r'src="data:image/(?:png|jpeg|gif);base64,([A-Za-z0-9+/=]+)"',tag,re.I)
  if not source:return tag
  try:
   with Image.open(io.BytesIO(base64.b64decode(source.group(1),validate=True))) as picture:natural_width,natural_height=picture.size
  except Exception:return tag
  width=min(natural_width,max_width);height=max(1,round(width*natural_height/natural_width))
  tag=re.sub(r'\s(?:width|height|style)="[^"]*"','',tag,flags=re.I)
  return tag[:-1]+f' width="{width}" height="{height}" style="width:{width}px;height:auto;max-width:100%">'
 return re.sub(r'<img\b[^>]*>',resize,value or '',flags=re.I)
def has_email_content(value:str)->bool:return bool(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',value or '')).strip() or re.search(r'<img\b',value or '',re.I))
def email_plain_text(value:str)->str:
 value=re.sub(r'<(?:br|/p|/div|/li)>', '\n',value or '',flags=re.I);return html.unescape(re.sub(r'<[^>]+>','',value)).strip()
def prepare_inline_images(value:str):
 images=[]
 def replace(match):
  subtype={'jpeg':'jpeg','png':'png','gif':'gif'}[match.group(1)];cid=f'email-image-{uuid.uuid4().hex}'
  try:data=base64.b64decode(match.group(2),validate=True)
  except ValueError:return ''
  if len(data)>1024*1024:return ''
  images.append((cid,subtype,data));return f'cid:{cid}'
 return re.sub(r'data:image/(png|jpeg|gif);base64,([A-Za-z0-9+/=]+)',replace,value,flags=re.I),images

def send_document_email(s:Session,d:Document,recipients:list[str],subject:str,content_html:str,signature_html:str):
 setting=s.query(EmailSetting).first()
 if not setting or not setting.enabled:raise HTTPException(409,'Gửi email đang tắt trong phần cấu hình hệ thống')
 password=os.getenv('SMTP_PASSWORD','').replace(' ','')
 if not password:raise HTTPException(503,'Máy chủ chưa được cấu hình biến môi trường SMTP_PASSWORD')
 if not d.file_path or not Path(d.file_path).is_file():raise HTTPException(400,'Văn bản chưa có tệp PDF để gửi')
 subject=subject.strip();content_html=clean_email_html(content_html);signature_html=constrain_signature_images(clean_email_html(signature_html))
 if not subject:raise HTTPException(422,'Tiêu đề email là bắt buộc')
 if not has_email_content(content_html):raise HTTPException(422,'Nội dung email là bắt buộc')
 if not has_email_content(signature_html):raise HTTPException(422,'Chữ ký email là bắt buộc')
 full_html=f'<div>{content_html}</div><div style="margin-top:24px">{signature_html}</div>';full_html,inline_images=prepare_inline_images(full_html)
 message=EmailMessage();message['Subject']=subject;message['From']=f'{setting.sender_name} <{setting.sender_email}>';message['To']=', '.join(recipients)
 message.set_content(f'{email_plain_text(content_html)}\n\n{email_plain_text(signature_html)}');message.add_alternative(full_html,subtype='html')
 html_part=message.get_payload()[-1]
 for cid,subtype,data in inline_images:html_part.add_related(data,maintype='image',subtype=subtype,cid=f'<{cid}>',filename=f'{cid}.{subtype}')
 file_path=Path(d.file_path);message.add_attachment(file_path.read_bytes(),maintype='application',subtype='pdf',filename=d.file_name or file_path.name)
 try:
  with smtplib.SMTP(setting.smtp_host,setting.smtp_port,timeout=120) as smtp:
   smtp.ehlo()
   if setting.use_tls:smtp.starttls();smtp.ehlo()
   smtp.login(setting.username,password);smtp.send_message(message)
 except smtplib.SMTPAuthenticationError as exc:
  raise HTTPException(502,'Gmail từ chối đăng nhập. Hãy kiểm tra email gửi và tạo lại App Password') from exc
 except smtplib.SMTPRecipientsRefused as exc:
  rejected=', '.join(exc.recipients.keys())
  raise HTTPException(422,f'Gmail từ chối địa chỉ người nhận: {rejected}') from exc
 except smtplib.SMTPSenderRefused as exc:
  raise HTTPException(422,'Gmail từ chối địa chỉ người gửi. Email người gửi phải trùng tài khoản SMTP') from exc
 except smtplib.SMTPDataError as exc:
  raise HTTPException(502,f'Gmail từ chối nội dung thư (mã SMTP {exc.smtp_code})') from exc
 except (OSError,smtplib.SMTPException) as exc:
  raise HTTPException(502,f'Không thể gửi email qua SMTP ({type(exc).__name__})') from exc
with DB() as search_session:
 for search_document in search_session.query(Document):
  old_name=search_document.file_name or '';clean_name=clean_workflow_suffixes(old_name)
  if old_name:clean_name=document_file_name(search_document.title,search_document.symbol)
  if clean_name!=old_name:
   path=Path(search_document.file_path) if search_document.file_path else None
   if path and path.exists() and path.name.endswith(old_name):
    target=path.with_name(path.name[:-len(old_name)]+clean_name)
    if not target.exists():path.rename(target);search_document.file_path=str(target)
   search_document.file_name=clean_name
  refresh_search(search_document)
 search_session.commit()
def log(s,d,u,a,c=''):s.add(Action(document_id=d.id,user_id=u.id,action=a,comment=c))
def pdf_point(page,x_percent,y_percent):
 return page.rect.width*x_percent/100,page.rect.height*y_percent/100
def render_signature(source:Path,x_percent:int,y_percent:int,page_number:int)->Path:
 doc=pymupdf.open(source);page=doc[max(0,min(len(doc)-1,page_number-1))];cx,cy=pdf_point(page,x_percent,y_percent);w,h=150,62;visual=pymupdf.Rect(cx-w/2,cy-h/2,cx+w/2,cy+h/2);box=visual*page.derotation_matrix;page.draw_oval(box,color=(.75,.04,.08),width=2.2,overlay=True);page.insert_textbox(box,'\nDA KY SO - GIA LAP\nDH HUNG VUONG',fontname='helv',fontsize=8,color=(.75,.04,.08),align=1,rotate=page.rotation,overlay=True);target=STORE/f'{uuid.uuid4()}-signed.pdf';doc.save(target,garbage=4,deflate=True);doc.close();return target
def render_seal(source:Path,x_percent:int,y_percent:int,page_number:int,seal_type:str)->Path:
 doc=pymupdf.open(source);page=doc[max(0,min(len(doc)-1,page_number-1))];cx,cy=pdf_point(page,x_percent,y_percent);size=112;visual=pymupdf.Rect(cx-size/2,cy-size/2,cx+size/2,cy+size/2);outer=visual*page.derotation_matrix;inner=pymupdf.Rect(outer.x0+7,outer.y0+7,outer.x1-7,outer.y1-7);red=(.75,.04,.08);page.draw_oval(outer,color=red,width=2.5,overlay=True);page.draw_oval(inner,color=red,width=1.2,overlay=True);name='DAU TRUONG' if seal_type=='SCHOOL' else 'DAU VAN PHONG';page.insert_textbox(outer,f'\n{name}\nGIA LAP\nDH HUNG VUONG',fontname='helv',fontsize=7,color=red,align=1,rotate=page.rotation,overlay=True);target=STORE/f'{uuid.uuid4()}-sealed.pdf';doc.save(target,garbage=4,deflate=True);doc.close();return target
def append_opinion(source:Path,note:str,author:str,symbol:str,title:str)->Path:
 base=pymupdf.open(source);sheet=pymupdf.open();page=sheet.new_page(width=595,height=842);regular=Path('/System/Library/Fonts/Supplemental/Arial.ttf');bold=Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf')
 if regular.exists():page.insert_font(fontname='arial',fontfile=str(regular))
 if bold.exists():page.insert_font(fontname='arial-bold',fontfile=str(bold))
 normal='arial' if regular.exists() else 'helv';strong='arial-bold' if bold.exists() else 'hebo';red=(.48,.04,.07);gray=(.25,.3,.36)
 page.insert_textbox(pymupdf.Rect(55,48,540,78),'TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG TP. HỒ CHÍ MINH',fontname=strong,fontsize=10,color=gray,align=1)
 page.insert_textbox(pymupdf.Rect(55,92,540,135),'PHIẾU Ý KIẾN XỬ LÝ CÔNG VĂN ĐẾN',fontname=strong,fontsize=17,color=red,align=1)
 page.insert_textbox(pymupdf.Rect(65,145,530,190),f'Số/Ký hiệu: {symbol or "Chưa cấp số"}\nTrích yếu: {title}',fontname=normal,fontsize=9.5,color=gray,lineheight=1.25)
 box=pymupdf.Rect(65,220,530,610);page.draw_rect(box,color=(.58,.62,.68),width=1.2);page.insert_textbox(pymupdf.Rect(82,238,513,270),'Ý KIẾN CỦA TRƯỞNG VĂN PHÒNG',fontname=strong,fontsize=11,color=red,align=1)
 page.insert_textbox(pymupdf.Rect(88,292,507,490),note,fontname=normal,fontsize=12,color=(.08,.1,.13),lineheight=1.45,align=0)
 page.insert_textbox(pymupdf.Rect(300,510,500,535),f'TP. Hồ Chí Minh, {datetime.now().strftime("ngày %d/%m/%Y")}',fontname=normal,fontsize=9,color=gray,align=1)
 sign=pymupdf.Rect(330,540,485,600);page.draw_oval(sign,color=(.75,.04,.08),width=1.8);page.insert_textbox(sign,'\nĐÃ KÝ SỐ - GIẢ LẬP\n'+author,fontname=strong,fontsize=8,color=(.75,.04,.08),align=1)
 page.insert_textbox(pymupdf.Rect(65,650,530,720),'Phiếu được tạo và ký điện tử trên Hệ thống Quản lý văn bản. Nội dung được khóa sau khi xác nhận.',fontname=normal,fontsize=8.5,color=(.4,.44,.5),align=1)
 combined=pymupdf.open();combined.insert_pdf(sheet);combined.insert_pdf(base);target=STORE/f'{uuid.uuid4()}-office-opinion.pdf';combined.save(target,garbage=4,deflate=True);combined.close();base.close();sheet.close();return target
def ocr_pdf(path:Path)->str:
 doc=pymupdf.open(path);parts=[]
 for page in doc:
  native=page.get_text().strip()
  if len(native)>=80:parts.append(native);continue
  pix=page.get_pixmap(matrix=pymupdf.Matrix(2,2),alpha=False);img=Image.open(io.BytesIO(pix.tobytes('png')));parts.append(pytesseract.image_to_string(img,lang=os.getenv('OCR_LANGUAGES','vie+eng')))
 doc.close();return '\n'.join(parts)
def archive_file(d:Document,source:Optional[DocumentSource]=None):
 path=Path(source.file_path) if source else Path(d.file_path) if d.file_path else None
 if not path or not path.exists():return
 year=(d.issued_date or d.received_date or d.created_at.date()).year;category=('CÔNG VĂN ĐẾN' if d.direction=='IN' else 'CÔNG VĂN ĐI') if d.doc_type=='CÔNG VĂN' else d.doc_type;folder=ARCHIVE_ROOT/str(year)/category
 folder.mkdir(parents=True,exist_ok=True);safe=''.join(c for c in (d.file_name or f'van-ban-{d.id}.pdf') if c not in '/\\:');target=folder/f'{d.id:06d}-{safe}'
 if path.resolve()!=target.resolve():shutil.copy2(path,target)
 if source:source.file_path=str(target);source.file_name=d.file_name or source.file_name
 else:d.file_path=str(target)
def incoming_source(s:Session,d:Document)->Optional[DocumentSource]:
 if d.direction!='IN' or not d.file_path:return None
 source=s.query(DocumentSource).filter_by(document_id=d.id).first()
 if source:return source
 source_path=Path(d.file_path)
 if not source_path.exists():return None
 opinion_statuses={'OFFICE_OPINION_COMPLETED','PENDING_BGH','BGH_APPROVED','BGH_REJECTED','FORWARDED','ARCHIVED'}
 if d.status in opinion_statuses:
  combined=pymupdf.open(source_path)
  if len(combined)<2:combined.close();return None
  original=pymupdf.open();original.insert_pdf(combined,from_page=1);target=STORE/f'{uuid.uuid4()}-incoming-original.pdf';original.save(target,garbage=4,deflate=True);original.close();combined.close();source_path=target
 source=DocumentSource(document_id=d.id,file_path=str(source_path),file_name=d.file_name or source_path.name);s.add(source);s.flush();return source
@app.post('/api/auth/login')
def login(x:Login,s:Session=Depends(db)):
 u=s.query(User).filter_by(username=x.username).first()
 if not u or not pwd.verify(x.password,u.password_hash):raise HTTPException(401,'Sai tài khoản hoặc mật khẩu')
 if not u.active:raise HTTPException(403,'Tài khoản đã bị khóa')
 return {'access_token':jwt.encode({'sub':str(u.id),'exp':datetime.utcnow()+timedelta(hours=12)},SECRET,algorithm='HS256'),'user':{'id':u.id,'full_name':u.full_name,'role':u.role,'department_id':u.department_id}}
@app.get('/api/dashboard')
def dashboard(u=Depends(current),s:Session=Depends(db)):
 a=[d for d in s.query(Document).filter(Document.status!='DELETED').all() if view(u,d,s)];return {'total':len(a),'incoming':sum(d.direction=='IN' for d in a),'outgoing':sum(d.direction=='OUT' for d in a),'pending':sum(d.status.startswith('PENDING') for d in a),'archived':sum(d.status=='ARCHIVED' for d in a),'recent':[out(d) for d in sorted(a,key=lambda x:x.updated_at,reverse=True)[:6]]}
@app.get('/api/documents')
def docs(direction:Optional[str]=None,q:Optional[str]=None,status:Optional[str]=None,u=Depends(current),s:Session=Depends(db)):
 x=s.query(Document).filter(Document.status!='DELETED')
 if direction:x=x.filter_by(direction=direction)
 if status:x=x.filter_by(status=status)
 if q:x=x.filter(Document.search_text.contains(normalize_search(q)))
 return [out(d) for d in x.order_by(Document.updated_at.desc()) if view(u,d,s)]
@app.post('/api/documents')
async def create(direction:str=Form(...),doc_type:str=Form('CÔNG VĂN'),title:str=Form(...),summary:str=Form(''),issuing_agency:str=Form(''),issued_date:Optional[str]=Form(None),department_id:Optional[int]=Form(None),priority:str=Form('Bình thường'),file:Optional[UploadFile]=File(None),u=Depends(current),s:Session=Depends(db)):
 require_permission(s,u,'CREATE','Bạn không có quyền tạo văn bản')
 if direction in {'IN','OUT'}:doc_type='CÔNG VĂN'
 if direction=='INTERNAL' and doc_type not in {'QUYẾT ĐỊNH','KẾ HOẠCH','THÔNG BÁO'}:raise HTTPException(400,'Loại văn bản nội bộ không hợp lệ')
 if direction in {'IN','OUT','INTERNAL'}:
  if not issued_date:raise HTTPException(422,'Ngày ban hành là bắt buộc')
  if not issuing_agency.strip():raise HTTPException(422,'Đơn vị phát hành là bắt buộc' if direction=='INTERNAL' else 'Đơn vị ban hành là bắt buộc' if direction=='IN' else 'Đơn vị tiếp nhận là bắt buộc')
  if direction=='INTERNAL' and issuing_agency.strip() not in INTERNAL_UNITS:raise HTTPException(400,'Đơn vị phát hành nội bộ không hợp lệ')
  if not file or not file.filename:raise HTTPException(422,'Bản scan / văn bản là bắt buộc')
  if Path(file.filename).suffix.lower()!='.pdf':raise HTTPException(400,'Chỉ chấp nhận file PDF')
  office=s.query(Department).filter_by(code='VP').first()
  if not office:raise HTTPException(500,'Chưa cấu hình đơn vị Văn phòng trường')
  department_id=office.id
 d=Document(direction=direction,doc_type=doc_type,title=title,summary=summary,issuing_agency=issuing_agency,issued_date=date.fromisoformat(issued_date) if issued_date else None,received_date=date.today() if direction=='IN' else None,department_id=department_id,priority=priority,owner_id=u.id,status='RECEIVED' if direction=='IN' else 'DRAFT')
 if file and file.filename:
  p=STORE/f'{uuid.uuid4()}{Path(file.filename).suffix}';p.write_bytes(await file.read());d.file_name=document_file_name(title);d.file_path=str(p)
  try:
   if p.suffix.lower()=='.pdf':d.ocr_text='\n'.join(x.get_text() for x in pymupdf.open(p))
  except Exception:d.ocr_text=''
 s.add(d);s.flush();refresh_search(d);log(s,d,u,'CREATE');s.commit();return out(d)
@app.post('/api/documents/{did}/outgoing-submit')
def outgoing_submit(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='OUT':raise HTTPException(404,'Không tìm thấy công văn đi')
 require_permission(s,u,'EDIT','Chỉ Văn thư được trình công văn đi')
 if not view(u,d,s):raise HTTPException(404,'Không tìm thấy công văn đi')
 if d.status not in {'DRAFT','RETURNED'}:raise HTTPException(409,'Văn bản không ở trạng thái có thể trình')
 if not d.file_path or not d.issued_date or not d.issuing_agency.strip():raise HTTPException(422,'Văn bản chưa đủ thông tin bắt buộc')
 d.status='PENDING_OFFICE_SIGN';log(s,d,u,'OUTGOING_SUBMIT_OFFICE');s.commit();return out(d)
@app.post('/api/documents/{did}/outgoing-return')
def outgoing_return(did:int,note:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='OUT':raise HTTPException(404,'Không tìm thấy công văn đi')
 require_document_access(s,u,d)
 require_permission(s,u,'SIGN','Bạn không có quyền trả lại văn bản')
 if d.status!='PENDING_OFFICE_SIGN':raise HTTPException(409,'Văn bản chưa được trình Trưởng Văn phòng')
 if not note.strip():raise HTTPException(422,'Lý do trả lại là bắt buộc')
 d.status='RETURNED';log(s,d,u,'OUTGOING_RETURN',note.strip());s.commit();return out(d)
@app.post('/api/documents/{did}/outgoing-number')
def outgoing_number(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='OUT':raise HTTPException(404,'Không tìm thấy công văn đi')
 require_document_access(s,u,d)
 require_permission(s,u,'ASSIGN_NUMBER','Bạn không có quyền cấp số')
 if d.status!='OFFICE_SIGNED' or not d.signed_personal:raise HTTPException(409,'Trưởng Văn phòng phải ký số trước khi cấp số')
 year=date.today().year;seq=s.query(Sequence).filter_by(year=year,doc_type='CÔNG VĂN ĐI').first()
 if not seq:seq=Sequence(year=year,doc_type='CÔNG VĂN ĐI',current=0,prefix='CV');s.add(seq);s.flush()
 seq.current+=1;d.number=seq.current;d.symbol=number_symbol('CÔNG VĂN',d.number,date.today(),'OUT');d.file_name=document_file_name(d.title,d.symbol);d.status='OUT_NUMBERED';refresh_search(d);log(s,d,u,'OUTGOING_NUMBER',d.symbol);s.commit();return out(d)
@app.post('/api/documents/{did}/outgoing-email')
def outgoing_email(did:int,emails:str=Form(...),subject:str=Form(...),content_html:str=Form(...),signature_html:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='OUT':raise HTTPException(404,'Không tìm thấy công văn đi')
 require_document_access(s,u,d);require_permission(s,u,'EMAIL','Bạn không có quyền phát hành văn bản')
 if d.status!='SEALED':raise HTTPException(409,'Văn bản phải được đóng dấu trước khi gửi mail')
 recipients=[x.strip() for x in re.split(r'[,;\n]',emails) if x.strip()]
 if not recipients:raise HTTPException(422,'Phải nhập ít nhất một email nhận')
 send_document_email(s,d,recipients,subject,content_html,signature_html)
 d.status='EMAILED';log(s,d,u,'OUTGOING_EMAIL',json.dumps({'recipients':recipients,'subject':subject},ensure_ascii=False));s.commit();return {'document':out(d),'email_status':'sent','recipients':recipients}
@app.post('/api/documents/{did}/internal-number')
def internal_number(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='INTERNAL':raise HTTPException(404,'Không tìm thấy công văn nội bộ')
 require_document_access(s,u,d)
 require_permission(s,u,'ASSIGN_NUMBER','Bạn không có quyền cấp số')
 if d.status!='DRAFT':raise HTTPException(409,'Chỉ văn bản nội bộ vừa tạo mới được cấp số')
 year=date.today().year;seq=s.query(Sequence).filter_by(year=year,doc_type=d.doc_type).first()
 if not seq:seq=Sequence(year=year,doc_type=d.doc_type,current=0,prefix=DOC_TYPE_CODES.get(d.doc_type,d.doc_type));s.add(seq);s.flush()
 seq.current+=1;d.number=seq.current;d.symbol=number_symbol(d.doc_type,d.number,date.today(),'INTERNAL');d.file_name=document_file_name(d.title,d.symbol);d.status='INTERNAL_NUMBERED';refresh_search(d);log(s,d,u,'INTERNAL_NUMBER',d.symbol);s.commit();return out(d)
@app.post('/api/documents/{did}/internal-submit')
def internal_submit(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='INTERNAL':raise HTTPException(404,'Không tìm thấy văn bản nội bộ')
 require_document_access(s,u,d);require_permission(s,u,'EDIT','Chỉ Văn thư được trình văn bản nội bộ')
 if d.status!='INTERNAL_NUMBERED':raise HTTPException(409,'Văn bản nội bộ phải được cấp số trước khi trình duyệt')
 d.status='PENDING_INTERNAL_APPROVAL';log(s,d,u,'INTERNAL_SUBMIT_OFFICE');s.commit();return out(d)
@app.post('/api/documents/{did}/internal-approve')
def internal_approve(did:int,note:str=Form(''),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='INTERNAL':raise HTTPException(404,'Không tìm thấy văn bản nội bộ')
 require_document_access(s,u,d);require_permission(s,u,'INTERNAL_APPROVE','Chỉ Trưởng Văn phòng được phê duyệt văn bản nội bộ')
 if d.status!='PENDING_INTERNAL_APPROVAL':raise HTTPException(409,'Văn bản nội bộ chưa được trình Trưởng Văn phòng')
 d.status='INTERNAL_APPROVED';log(s,d,u,'INTERNAL_APPROVED',note.strip());s.commit();return out(d)
@app.post('/api/documents/{did}/internal-email')
def internal_email(did:int,emails:str=Form(...),subject:str=Form(...),content_html:str=Form(...),signature_html:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='INTERNAL':raise HTTPException(404,'Không tìm thấy công văn nội bộ')
 require_document_access(s,u,d);require_permission(s,u,'EMAIL','Bạn không có quyền phát hành văn bản')
 if d.status!='INTERNAL_SEALED' or not d.sealed:raise HTTPException(409,'Văn bản nội bộ phải được đóng dấu trước khi phát hành')
 recipients=[x.strip() for x in re.split(r'[,;\n]',emails) if x.strip()]
 if not recipients:raise HTTPException(422,'Phải nhập ít nhất một email nhận')
 send_document_email(s,d,recipients,subject,content_html,signature_html)
 d.status='INTERNAL_PUBLISHED';log(s,d,u,'INTERNAL_EMAIL_PUBLISH',json.dumps({'recipients':recipients,'subject':subject},ensure_ascii=False));s.commit();return {'document':out(d),'email_status':'sent','recipients':recipients}
@app.post('/api/documents/{did}/incoming-number')
def incoming_number(did:int,year:int=Form(default=date.today().year),number:Optional[int]=Form(None),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 require_permission(s,u,'ASSIGN_NUMBER','Bạn không có quyền vào số')
 if d.status!='RECEIVED':raise HTTPException(409,'Chỉ công văn vừa tiếp nhận mới được vào số')
 last=s.query(IncomingNumber).filter_by(year=year,doc_type=d.doc_type).order_by(IncomingNumber.number.desc()).first();chosen=number or ((last.number if last else 0)+1)
 if chosen<1:raise HTTPException(400,'Số văn bản phải lớn hơn 0')
 if s.query(IncomingNumber).filter_by(year=year,doc_type=d.doc_type,number=chosen).first():raise HTTPException(409,'Số này đã tồn tại trong sổ văn bản cùng loại và năm')
 s.add(IncomingNumber(document_id=d.id,year=year,doc_type=d.doc_type,number=chosen));d.number=chosen;d.symbol=number_symbol(d.doc_type,chosen,date.today(),'IN');d.file_name=document_file_name(d.title,d.symbol) if d.file_name else None;d.status='NUMBERED';refresh_search(d);log(s,d,u,'INCOMING_NUMBER',d.symbol);s.commit();return out(d)
@app.post('/api/documents/{did}/edit-received')
async def edit_received(did:int,title:str=Form(...),doc_type:str=Form('CÔNG VĂN'),summary:str=Form(''),issuing_agency:str=Form(''),issued_date:Optional[str]=Form(None),file_name:Optional[str]=Form(None),file:Optional[UploadFile]=File(None),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 if d.status!='RECEIVED':raise HTTPException(409,'Văn bản đã vào số nên không được chỉnh sửa')
 require_permission(s,u,'EDIT','Chỉ Văn thư được chỉnh sửa công văn đến')
 doc_type='CÔNG VĂN'
 if not issued_date:raise HTTPException(422,'Ngày ban hành là bắt buộc')
 if not issuing_agency.strip():raise HTTPException(422,'Đơn vị ban hành là bắt buộc')
 if not d.file_path and (not file or not file.filename):raise HTTPException(422,'Bản scan / văn bản là bắt buộc')
 d.title=title.strip();d.doc_type=doc_type;d.summary=summary;d.issuing_agency=issuing_agency;d.issued_date=date.fromisoformat(issued_date) if issued_date else None
 d.file_name=document_file_name(d.title,d.symbol) if d.file_name else None
 if file and file.filename:
  if Path(file.filename).suffix.lower()!='.pdf':raise HTTPException(400,'Chỉ chấp nhận PDF')
  content=await file.read();p=STORE/f'{uuid.uuid4()}.pdf';p.write_bytes(content);d.file_name=document_file_name(d.title,d.symbol);d.file_path=str(p)
 refresh_search(d);log(s,d,u,'EDIT_RECEIVED',f'Tên file: {d.file_name or "không có"}');s.commit();return out(d)
@app.post('/api/incoming/reserve-number')
def reserve_incoming_number(doc_type:str=Form('CÔNG VĂN'),year:int=Form(default=date.today().year),title:str=Form(...),issuing_agency:str=Form(''),reason:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 require_permission(s,u,'RESERVE_NUMBER','Bạn không có quyền xin số trước')
 doc_type='CÔNG VĂN'
 if not title.strip() or not reason.strip():raise HTTPException(422,'Trích yếu dự kiến và lý do xin số là bắt buộc')
 last=s.query(IncomingNumber).filter_by(year=year,doc_type=doc_type).order_by(IncomingNumber.number.desc()).first();chosen=(last.number if last else 0)+1;d=Document(direction='IN',doc_type=doc_type,number=chosen,symbol=number_symbol(doc_type,chosen,date.today(),'IN'),title=title.strip(),summary=f'Lý do xin số trước: {reason.strip()}',issuing_agency=issuing_agency,received_date=date.today(),status='RESERVED_INCOMING',reserved=True,owner_id=u.id);s.add(d);s.flush();refresh_search(d);s.add(IncomingNumber(document_id=d.id,year=year,doc_type=doc_type,number=chosen));log(s,d,u,'RESERVE_INCOMING_NUMBER',reason.strip());s.commit();return out(d)
@app.post('/api/reserve-number')
def reserve_number(direction:str=Form(...),doc_type:str=Form('CÔNG VĂN'),title:str=Form(...),issuing_agency:str=Form(''),reason:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 require_permission(s,u,'RESERVE_NUMBER','Bạn không có quyền xin số trước')
 if direction not in {'OUT','INTERNAL'}:raise HTTPException(400,'Luồng xin số không hợp lệ')
 if direction=='OUT':doc_type='CÔNG VĂN'
 if direction=='INTERNAL' and doc_type not in {'QUYẾT ĐỊNH','KẾ HOẠCH','THÔNG BÁO'}:raise HTTPException(400,'Loại văn bản nội bộ không hợp lệ')
 if not title.strip() or not reason.strip():raise HTTPException(422,'Trích yếu dự kiến và lý do xin số là bắt buộc')
 if direction=='INTERNAL' and issuing_agency.strip() and issuing_agency.strip() not in INTERNAL_UNITS:raise HTTPException(400,'Đơn vị phát hành nội bộ không hợp lệ')
 year=date.today().year;sequence_type='CÔNG VĂN ĐI' if direction=='OUT' else doc_type;seq=s.query(Sequence).filter_by(year=year,doc_type=sequence_type).first()
 if not seq:seq=Sequence(year=year,doc_type=sequence_type,current=0,prefix='CV' if direction=='OUT' else DOC_TYPE_CODES.get(doc_type,doc_type));s.add(seq);s.flush()
 seq.current+=1;symbol=number_symbol(doc_type,seq.current,date.today(),direction);status='RESERVED_OUTGOING' if direction=='OUT' else 'RESERVED_INTERNAL'
 d=Document(direction=direction,doc_type=doc_type,number=seq.current,symbol=symbol,title=title.strip(),summary=f'Lý do xin số trước: {reason.strip()}',issuing_agency=issuing_agency.strip(),status=status,reserved=True,owner_id=u.id);s.add(d);s.flush();refresh_search(d);log(s,d,u,'RESERVE_NUMBER',reason.strip());s.commit();return out(d)
@app.post('/api/documents/{did}/edit-outgoing')
async def edit_outgoing(did:int,title:str=Form(...),summary:str=Form(''),issuing_agency:str=Form(...),issued_date:str=Form(...),file_name:Optional[str]=Form(None),file:Optional[UploadFile]=File(None),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='OUT':raise HTTPException(404,'Không tìm thấy công văn đi')
 require_permission(s,u,'EDIT','Chỉ Văn thư được sửa công văn đi')
 if not view(u,d,s):raise HTTPException(404,'Không tìm thấy công văn đi')
 if d.status not in {'DRAFT','RETURNED'}:raise HTTPException(409,'Chỉ được sửa bản nháp hoặc văn bản bị trả lại')
 if not title.strip() or not issuing_agency.strip() or not issued_date:raise HTTPException(422,'Thiếu thông tin bắt buộc')
 if not d.file_path and (not file or not file.filename):raise HTTPException(422,'File PDF là bắt buộc')
 d.title=title.strip();d.summary=summary;d.issuing_agency=issuing_agency.strip();d.issued_date=date.fromisoformat(issued_date);d.file_name=document_file_name(d.title,d.symbol)
 if file and file.filename:
  if Path(file.filename).suffix.lower()!='.pdf':raise HTTPException(400,'Chỉ chấp nhận PDF')
  p=STORE/f'{uuid.uuid4()}.pdf';p.write_bytes(await file.read());d.file_path=str(p);d.file_name=document_file_name(d.title,d.symbol)
 refresh_search(d);log(s,d,u,'EDIT_OUTGOING');s.commit();return out(d)
@app.post('/api/documents/{did}/attach-reserved')
async def attach_reserved(did:int,file:UploadFile=File(...),title:Optional[str]=Form(None),issuing_agency:Optional[str]=Form(None),issued_date:Optional[str]=Form(None),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.status not in {'RESERVED_INCOMING','RESERVED_OUTGOING','RESERVED_INTERNAL'}:raise HTTPException(404,'Không tìm thấy số đã giữ')
 require_document_access(s,u,d)
 require_permission(s,u,'EDIT','Bạn không có quyền bổ sung văn bản')
 if Path(file.filename or '').suffix.lower()!='.pdf':raise HTTPException(400,'Văn bản bổ sung phải là PDF')
 if d.direction in {'OUT','INTERNAL'} and (not issued_date or not (issuing_agency or d.issuing_agency).strip()):raise HTTPException(422,'Ngày phát hành và đơn vị là bắt buộc')
 content=await file.read()
 if len(content)>25*1024*1024:raise HTTPException(413,'Tệp PDF vượt quá 25 MB')
 p=STORE/f'{uuid.uuid4()}.pdf';p.write_bytes(content);d.file_path=str(p);d.title=title.strip() if title and title.strip() else d.title;d.file_name=document_file_name(d.title,d.symbol);d.issuing_agency=issuing_agency.strip() if issuing_agency else d.issuing_agency;d.issued_date=date.fromisoformat(issued_date) if issued_date else d.issued_date;d.status='NUMBERED' if d.direction=='IN' else 'DRAFT' if d.direction=='OUT' else 'INTERNAL_NUMBERED';d.reserved=False;refresh_search(d);log(s,d,u,'ATTACH_RESERVED_DOCUMENT',file.filename);s.commit();return out(d)
@app.post('/api/documents/{did}/office-opinion')
async def office_opinion(did:int,note:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 require_permission(s,u,'OFFICE_OPINION','Bạn không có quyền cho ý kiến Trưởng Văn phòng')
 if d.status!='NUMBERED':raise HTTPException(409,'Văn bản phải được vào số trước')
 if not note.strip():raise HTTPException(422,'Ý kiến của Trưởng Văn phòng là bắt buộc')
 if not d.file_path:raise HTTPException(400,'Văn bản chưa có PDF')
 incoming_source(s,d)
 result=append_opinion(Path(d.file_path),note.strip(),u.full_name,d.symbol or '',d.title);d.file_path=str(result);d.status='OFFICE_OPINION_COMPLETED';log(s,d,u,'OFFICE_OPINION_DIGITALLY_SIGNED',note.strip());s.commit();return out(d)
@app.post('/api/documents/{did}/send-bgh')
def send_bgh(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 require_permission(s,u,'SEND_BGH','Bạn không có quyền gửi Ban Giám hiệu')
 if d.status!='OFFICE_OPINION_COMPLETED':raise HTTPException(409,'Phải hoàn tất ý kiến Trưởng Văn phòng trước')
 d.status='PENDING_BGH';log(s,d,u,'SEND_BGH');s.commit();return out(d)
@app.post('/api/documents/{did}/bgh-decision')
def bgh_decision(did:int,decision:str=Form(...),note:str=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 require_permission(s,u,'BGH_DECIDE','Bạn không có quyền duyệt hoặc từ chối')
 if d.status!='PENDING_BGH':raise HTTPException(409,'Văn bản chưa được gửi BGH')
 if not note.strip():raise HTTPException(422,'Ý kiến BGH là bắt buộc')
 if decision not in {'APPROVE','REJECT'}:raise HTTPException(400,'Quyết định không hợp lệ')
 d.status='BGH_APPROVED' if decision=='APPROVE' else 'BGH_REJECTED';log(s,d,u,f'BGH_{decision}',note.strip());s.commit();return out(d)
@app.post('/api/documents/{did}/forward')
def forward_incoming(did:int,department_ids:str=Form(...),emails:str=Form('[]'),note:str=Form(''),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or d.direction!='IN':raise HTTPException(404,'Không tìm thấy công văn đến')
 require_document_access(s,u,d)
 require_permission(s,u,'FORWARD','Bạn không có quyền chuyển văn bản')
 if d.status!='BGH_APPROVED':raise HTTPException(409,'BGH phải duyệt trước khi chuyển đơn vị')
 deps=json.loads(department_ids);mail_list=json.loads(emails)
 if not deps:raise HTTPException(422,'Phải chọn ít nhất một đơn vị')
 if mail_list:
  setting=s.query(EmailSetting).first();send_document_email(s,d,mail_list,d.title,f'<p>{html.escape(note)}</p>',setting.signature_html if setting else '')
 d.assignee_ids=json.dumps(deps);d.status='FORWARDED';log(s,d,u,'FORWARD',json.dumps({'departments':deps,'emails':mail_list,'note':note},ensure_ascii=False));s.commit();return {'document':out(d),'email_status':'sent' if mail_list else 'not_requested','recipients':mail_list}
@app.post('/api/sequences/reserve')
def reserve(x:Reserve,u=Depends(current),s:Session=Depends(db)):
 require_permission(s,u,'RESERVE_NUMBER','Bạn không có quyền giữ số')
 seq=s.query(Sequence).filter_by(year=x.year,doc_type=x.doc_type).first()
 if not seq:seq=Sequence(year=x.year,doc_type=x.doc_type,current=0,prefix=x.doc_type);s.add(seq);s.flush()
 result=[]
 for _ in range(min(x.quantity,50)):
  seq.current+=1;d=Document(direction='OUT',doc_type=x.doc_type,number=seq.current,symbol=f'{seq.current:03d}/{seq.prefix}',title='Số dự kiến - chưa gắn văn bản',status='RESERVED',reserved=True,owner_id=u.id);s.add(d);s.flush();log(s,d,u,'RESERVE_NUMBER');result.append(out(d))
 s.commit();return result
@app.post('/api/documents/{did}/action')
def action(did:int,x:Act,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404,'Không tìm thấy văn bản')
 if x.action=='DELETE':
  require_permission(s,u,'DELETE','Bạn không có quyền xóa văn bản')
  if not x.comment.strip():raise HTTPException(422,'Lý do xóa là bắt buộc')
  if d.status=='DELETED':raise HTTPException(409,'Văn bản đã được xóa')
  s.add(DeletedRecord(document_id=d.id,previous_status=d.status,deleted_by=u.id,reason=x.comment.strip()));d.status='DELETED';log(s,d,u,'SOFT_DELETE',x.comment.strip());s.commit();return out(d)
 if x.action=='ARCHIVE':
  if d.status=='ARCHIVED':raise HTTPException(409,'Văn bản đã được lưu trữ')
  require_permission(s,u,'ARCHIVE','Bạn không có quyền lưu trữ văn bản')
  if d.direction=='OUT' and d.status!='EMAILED':raise HTTPException(409,'Văn bản đi phải được gửi mail trước khi lưu trữ')
  if d.direction=='IN' and d.status!='FORWARDED':raise HTTPException(409,'Công văn đến phải được BGH duyệt và chuyển đơn vị trước khi lưu trữ')
  if d.direction=='INTERNAL' and d.status!='INTERNAL_PUBLISHED':raise HTTPException(409,'Văn bản nội bộ phải được phát hành qua mail trước khi lưu trữ')
  if not d.file_path:raise HTTPException(400,'Văn bản chưa có PDF để OCR')
  source=incoming_source(s,d) if d.direction=='IN' else None
  archive_path=Path(source.file_path) if source else Path(d.file_path)
  d.ocr_text=ocr_pdf(archive_path)
  archive_file(d,source)
  d.status='ARCHIVED';refresh_search(d);log(s,d,u,'ARCHIVE',x.comment);s.commit();return out(d)
 raise HTTPException(400,'Thao tác không hợp lệ hoặc đã được thay bằng quy trình chuyên biệt')
@app.post('/api/documents/{did}/restore')
def restore_document(did:int,u=Depends(current),s:Session=Depends(db)):
 require_permission(s,u,'RESTORE','Bạn không có quyền khôi phục văn bản')
 d=s.get(Document,did);deleted=s.query(DeletedRecord).filter_by(document_id=did).first()
 if not d or d.status!='DELETED' or not deleted:raise HTTPException(404,'Không tìm thấy văn bản đã xóa')
 d.status=deleted.previous_status;log(s,d,u,'RESTORE',deleted.reason);s.delete(deleted);s.commit();return out(d)
@app.get('/api/documents/{did}/history')
def history(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404)
 return [{'action':a.action,'comment':a.comment,'user_id':a.user_id,'created_at':a.created_at} for a in s.query(Action).filter_by(document_id=did).order_by(Action.created_at.desc())]
@app.get('/api/documents/{did}/file')
def download(did:int,original:bool=False,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s) or not d.file_path:raise HTTPException(404)
 source=incoming_source(s,d) if original and d.direction=='IN' else None
 if source:s.commit()
 path=source.file_path if source else d.file_path
 if not path or not Path(path).exists():raise HTTPException(404,'Không tìm thấy file văn bản')
 return FileResponse(path,filename=d.file_name)
@app.post('/api/documents/{did}/rename-file')
def rename_file(did:int,x:RenameFile,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s) or not d.file_path:raise HTTPException(404,'Không tìm thấy file văn bản')
 require_permission(s,u,'RENAME','Bạn không có quyền đổi tên file')
 name=x.name.strip()
 if not name or any(c in name for c in '/\\\0'):raise HTTPException(422,'Tên file không hợp lệ')
 source=Path(d.file_path);suffix=source.suffix or Path(d.file_name or '').suffix
 if suffix and not name.lower().endswith(suffix.lower()):name+=suffix
 target=source.with_name(name)
 if target.exists() and target.resolve()!=source.resolve():raise HTTPException(409,'Tên file đã tồn tại')
 old=d.file_name or source.name;source.rename(target);d.file_path=str(target);d.file_name=name;log(s,d,u,'RENAME_FILE',f'{old} -> {name}');s.commit();return out(d)
@app.get('/api/documents/{did}/pages/{page_number}/preview')
def preview_page(did:int,page_number:int,source:bool=False,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s) or not d.file_path:raise HTTPException(404,'Không tìm thấy PDF')
 source_row=s.query(DocumentSource).filter_by(document_id=did).first() if source else None;pdf_path=source_row.file_path if source_row else d.file_path;doc=pymupdf.open(pdf_path)
 if page_number<1 or page_number>len(doc):doc.close();raise HTTPException(404,'Trang PDF không tồn tại')
 pix=doc[page_number-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5),alpha=False);content=pix.tobytes('png');doc.close();return Response(content=content,media_type='image/png')
@app.get('/api/documents/{did}/preview-info')
def preview_info(did:int,source:bool=False,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s) or not d.file_path:raise HTTPException(404,'Không tìm thấy PDF')
 source_row=s.query(DocumentSource).filter_by(document_id=did).first() if source else None;pdf_path=source_row.file_path if source_row else d.file_path;doc=pymupdf.open(pdf_path);pages=[{'page':i+1,'width':round(p.rect.width,2),'height':round(p.rect.height,2)} for i,p in enumerate(doc)];doc.close();return {'page_count':len(pages),'pages':pages}
@app.post('/api/documents/{did}/digital-sign')
async def digital_sign(did:int,page:int=Form(1),x_percent:float=Form(...),y_percent:float=Form(...),file:Optional[UploadFile]=File(None),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404,'Không tìm thấy văn bản')
 if d.direction!='OUT':raise HTTPException(409,'Công văn đến không có bước ký số')
 require_permission(s,u,'SIGN','Bạn không có quyền ký số công văn đi')
 if d.status!='PENDING_OFFICE_SIGN':raise HTTPException(409,'Văn bản chưa được trình Trưởng Văn phòng ký số')
 if d.signed_personal:raise HTTPException(409,'Văn bản đã ký số; vị trí ký đã được khóa')
 if d.sealed:raise HTTPException(409,'Văn bản đã đóng dấu nên không thể thay đổi chữ ký')
 if file:
  if Path(file.filename or '').suffix.lower()!='.pdf':raise HTTPException(400,'Chỉ chấp nhận tệp PDF')
  content=await file.read()
  if len(content)>25*1024*1024:raise HTTPException(413,'Tệp PDF vượt quá 25 MB')
  p=STORE/f'{uuid.uuid4()}.pdf';p.write_bytes(content);d.file_name=document_file_name(d.title,d.symbol);d.file_path=str(p)
 if not d.file_path or not Path(d.file_path).exists():raise HTTPException(400,'Văn bản chưa có tệp PDF')
 source=s.query(DocumentSource).filter_by(document_id=d.id).first()
 if not source:source=DocumentSource(document_id=d.id,file_path=d.file_path,file_name=d.file_name or 'van-ban.pdf');s.add(source);s.flush()
 if not Path(source.file_path).exists():raise HTTPException(400,'Không tìm thấy PDF nguồn')
 signed_path=render_signature(Path(source.file_path),max(0,min(100,x_percent)),max(0,min(100,y_percent)),max(1,page));digest=hashlib.sha256(signed_path.read_bytes()).hexdigest();d.file_path=str(signed_path)
 sig=s.query(DigitalSignature).filter_by(document_id=d.id).order_by(DigitalSignature.created_at.desc()).first()
 if sig:sig.user_id=u.id;sig.page=max(1,page);sig.x_percent=max(0,min(100,x_percent));sig.y_percent=max(0,min(100,y_percent));sig.file_hash=digest
 else:sig=DigitalSignature(document_id=d.id,user_id=u.id,page=max(1,page),x_percent=max(0,min(100,x_percent)),y_percent=max(0,min(100,y_percent)),file_hash=digest);s.add(sig)
 d.signed_personal=True;d.signature_hash=digest;d.status='OUT_NUMBERED' if d.direction=='OUT' and d.number else 'OFFICE_SIGNED';log(s,d,u,'OFFICE_DIGITAL_SIGN_POSITION',f'Trang {sig.page}, vị trí {sig.x_percent}% / {sig.y_percent}% (giả lập)');s.commit()
 return {'status':'signed_simulation','signature_id':sig.id,'page':sig.page,'x_percent':sig.x_percent,'y_percent':sig.y_percent,'file_hash':digest}
@app.get('/api/documents/{did}/digital-signature')
def digital_signature_info(did:int,u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404,'Không tìm thấy văn bản')
 sig=s.query(DigitalSignature).filter_by(document_id=did).order_by(DigitalSignature.created_at.desc()).first()
 return {'signed':bool(sig),'page':sig.page if sig else 1,'x_percent':sig.x_percent if sig else 55,'y_percent':sig.y_percent if sig else 68,'locked':d.sealed}
@app.post('/api/documents/{did}/digital-seal')
def digital_seal(did:int,seal_type:str=Form(...),page:int=Form(1),x_percent:float=Form(...),y_percent:float=Form(...),u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404,'Không tìm thấy văn bản')
 if d.direction not in {'OUT','INTERNAL'}:raise HTTPException(409,'Công văn đến không có bước đóng dấu')
 require_permission(s,u,'SEAL','Bạn không có quyền đóng dấu')
 if d.direction=='OUT' and not d.signed_personal:raise HTTPException(409,'Văn bản phải được ký số trước khi đóng dấu')
 expected_status='OUT_NUMBERED' if d.direction=='OUT' else 'INTERNAL_APPROVED'
 if d.status!=expected_status:raise HTTPException(409,'Văn bản đi phải được cấp số; văn bản nội bộ phải được Trưởng Văn phòng phê duyệt trước khi đóng dấu')
 if d.sealed:raise HTTPException(409,'Văn bản này đã được đóng dấu')
 if seal_type not in {'SCHOOL','OFFICE'}:raise HTTPException(400,'Loại con dấu không hợp lệ')
 if not d.file_path or not Path(d.file_path).exists():raise HTTPException(400,'Văn bản chưa có tệp PDF')
 sealed_path=render_seal(Path(d.file_path),max(0,min(100,x_percent)),max(0,min(100,y_percent)),max(1,page),seal_type);digest=hashlib.sha256(sealed_path.read_bytes()).hexdigest();d.file_path=str(sealed_path);seal=DigitalSeal(document_id=d.id,user_id=u.id,seal_type=seal_type,page=max(1,page),x_percent=max(0,min(100,x_percent)),y_percent=max(0,min(100,y_percent)),file_hash=digest)
 s.add(seal);d.sealed=True;d.status='SEALED' if d.direction=='OUT' else 'INTERNAL_SEALED';log(s,d,u,'DIGITAL_SEAL',f'{seal_type}, trang {seal.page}, vị trí {seal.x_percent}% / {seal.y_percent}% (giả lập)');s.commit()
 return {'status':'sealed_simulation','seal_id':seal.id,'seal_type':seal.seal_type,'page':seal.page,'x_percent':seal.x_percent,'y_percent':seal.y_percent,'file_hash':digest}
@app.get('/api/config')
def config(u=Depends(current),s:Session=Depends(db)):
 effective=[code for code in PERMISSION_LABELS if has_permission(s,u,code)]
 if u.role!='ADMIN':return {'departments':[{'id':d.id,'name':d.name,'code':d.code} for d in s.query(Department)],'sequences':[],'users':[],'roles':[],'email':{},'permissions':effective}
 email=s.query(EmailSetting).first();roles=[
  {'code':'ADMIN','name':'Quản trị hệ thống','permissions':['Quản lý người dùng','Cấu hình hệ thống','Xem toàn bộ hồ sơ','Xóa và khôi phục']},
  {'code':'BGH','name':'Ban Giám hiệu','permissions':['Xem hồ sơ được trình','Duyệt hoặc từ chối','Theo dõi xử lý']},
  {'code':'OFFICE_HEAD','name':'Trưởng Văn phòng','permissions':['Cho ý kiến công văn đến','Phê duyệt văn bản nội bộ','Ký hoặc trả công văn đi']},
  {'code':'CLERK','name':'Văn thư','permissions':['Tiếp nhận và tạo văn bản','Sửa và cấp số','Gửi Ban Giám hiệu','Chuyển đơn vị xử lý','Đóng dấu','Phát hành qua email','Lưu trữ','Xóa có lý do']},
  {'code':'DEPARTMENT','name':'Đơn vị xử lý','permissions':['Xem hồ sơ được phân công','Theo dõi tiến độ']},
 ]
 overrides={(x.role,x.permission):x.enabled for x in s.query(RolePermission)}
 for role in roles:
  role['permission_options']=[{'code':code,'name':PERMISSION_LABELS[code],'enabled':overrides.get((role['code'],code),True)} for code in ROLE_DEFAULTS.get(role['code'],set())]
  role['permissions']=[x['name'] for x in role['permission_options'] if x['enabled']]
 return {'departments':[{'id':d.id,'name':d.name,'code':d.code} for d in s.query(Department)],'sequences':[{'year':x.year,'doc_type':x.doc_type,'current':x.current,'prefix':x.prefix} for x in s.query(Sequence)],'users':[{'id':x.id,'username':x.username,'full_name':x.full_name,'role':x.role,'department_id':x.department_id,'active':x.active} for x in s.query(User)] if has_permission(s,u,'MANAGE_USERS') else [],'roles':roles,'email':({'smtp_host':email.smtp_host,'smtp_port':email.smtp_port,'username':email.username,'sender_name':email.sender_name,'sender_email':email.sender_email,'signature_html':email.signature_html,'use_tls':email.use_tls,'enabled':email.enabled} if email else {'smtp_host':'','smtp_port':587,'username':'','sender_name':'Đại học Hùng Vương','sender_email':'','signature_html':'','use_tls':True,'enabled':False}),'permissions':effective}
@app.put('/api/config/users/{uid}')
def update_user_config(uid:int,x:UserConfig,u=Depends(current),s:Session=Depends(db)):
 if u.role!='ADMIN':raise HTTPException(403,'Chỉ Admin được cấu hình người dùng')
 target=s.get(User,uid)
 if not target:raise HTTPException(404,'Không tìm thấy người dùng')
 if x.role not in {'ADMIN','BGH','OFFICE_HEAD','CLERK','DEPARTMENT'}:raise HTTPException(400,'Vai trò không hợp lệ')
 if target.username=='admin' and (not x.active or x.role!='ADMIN'):raise HTTPException(409,'Tài khoản admin luôn hoạt động và luôn có toàn quyền')
 if target.username!='admin' and x.role=='ADMIN':raise HTTPException(409,'Không thể gán vai trò quản trị tối cao cho tài khoản khác')
 target.full_name=x.full_name.strip();target.role=x.role;target.department_id=x.department_id;target.active=x.active;s.commit();return {'status':'updated'}
@app.put('/api/config/email')
def update_email_config(x:EmailConfig,u=Depends(current),s:Session=Depends(db)):
 if u.role!='ADMIN':raise HTTPException(403,'Chỉ Admin được cấu hình email')
 if x.smtp_port<1 or x.smtp_port>65535:raise HTTPException(422,'Cổng SMTP không hợp lệ')
 x.signature_html=constrain_signature_images(clean_email_html(x.signature_html))
 if not has_email_content(x.signature_html):raise HTTPException(422,'Chữ ký email là bắt buộc')
 email=s.query(EmailSetting).first()
 if not email:email=EmailSetting();s.add(email)
 for key,value in x.model_dump().items():setattr(email,key,value)
 s.commit();return {'status':'updated'}
@app.put('/api/config/permissions')
def update_permissions(x:PermissionConfig,u=Depends(current),s:Session=Depends(db)):
 if u.role!='ADMIN':raise HTTPException(403,'Chỉ Admin được cấu hình phân quyền')
 if x.role not in ROLE_DEFAULTS:raise HTTPException(400,'Vai trò không hợp lệ')
 if x.role=='ADMIN':raise HTTPException(409,'Quyền Quản trị hệ thống được khóa để tránh mất quyền quản trị')
 invalid=set(x.permissions)-set(PERMISSION_LABELS)
 if invalid:raise HTTPException(400,f'Quyền không hợp lệ: {", ".join(sorted(invalid))}')
 outside_role=set(x.permissions)-ROLE_DEFAULTS[x.role]
 if outside_role:raise HTTPException(400,'Không thể gán quyền nghiệp vụ ngoài phạm vi của vai trò')
 selected=set(x.permissions)
 for code in PERMISSION_LABELS:
  row=s.query(RolePermission).filter_by(role=x.role,permission=code).first()
  if not row:row=RolePermission(role=x.role,permission=code);s.add(row)
  row.enabled=code in selected
 s.commit();return {'status':'updated','role':x.role,'permissions':sorted(selected)}
@app.get('/api/activity')
def activity(limit:int=200,u=Depends(current),s:Session=Depends(db)):
 if u.role!='ADMIN':raise HTTPException(403,'Chỉ Admin được xem nhật ký toàn hệ thống')
 rows=s.query(Action,User,Document).join(User,Action.user_id==User.id).join(Document,Action.document_id==Document.id).order_by(Action.created_at.desc()).limit(max(1,min(limit,1000))).all()
 return [{'id':a.id,'created_at':a.created_at,'user_id':user.id,'username':user.username,'full_name':user.full_name,'role':user.role,'action':a.action,'comment':a.comment,'document_id':doc.id,'symbol':doc.symbol,'title':doc.title,'direction':doc.direction,'status':doc.status} for a,user,doc in rows]
@app.get('/api/notifications')
def notifications(u=Depends(current),s:Session=Depends(db)):
 tasks={
  'RECEIVED':('ASSIGN_NUMBER','Công văn đến mới','Cần vào số công văn đến'),
  'NUMBERED':('OFFICE_OPINION','Công văn chờ ý kiến','Trưởng Văn phòng cần ghi ý kiến xử lý'),
  'OFFICE_OPINION_COMPLETED':('SEND_BGH','Hồ sơ chờ trình BGH','Phiếu ý kiến đã hoàn tất, cần gửi Ban Giám hiệu'),
  'PENDING_BGH':('BGH_DECIDE','Văn bản chờ BGH xử lý','Cần duyệt hoặc từ chối văn bản'),
  'BGH_APPROVED':('FORWARD','Văn bản đã được duyệt','Cần chuyển đến đơn vị xử lý'),
  'FORWARDED':(None,'Văn bản được phân công','Đơn vị của bạn được giao xử lý văn bản'),
  'PENDING_OFFICE_SIGN':('SIGN','Công văn đi chờ ký','Trưởng Văn phòng cần xem xét và ký số'),
  'OFFICE_SIGNED':('ASSIGN_NUMBER','Công văn đi đã ký','Cần cấp số công văn đi'),
  'OUT_NUMBERED':('SEAL','Công văn đi đã cấp số','Cần đóng dấu văn bản'),
  'SEALED':('EMAIL','Văn bản đã đóng dấu','Cần phát hành văn bản qua email'),
  'INTERNAL_NUMBERED':('EDIT','Văn bản nội bộ đã cấp số','Cần trình Trưởng Văn phòng phê duyệt'),
  'PENDING_INTERNAL_APPROVAL':('INTERNAL_APPROVE','Văn bản nội bộ chờ duyệt','Trưởng Văn phòng cần phê duyệt văn bản'),
  'INTERNAL_APPROVED':('SEAL','Văn bản nội bộ đã được duyệt','Cần đóng dấu văn bản'),
  'INTERNAL_SEALED':('EMAIL','Văn bản nội bộ đã đóng dấu','Cần phát hành văn bản'),
  'RETURNED':('EDIT','Văn bản bị trả lại','Cần chỉnh sửa và trình lại'),
 }
 rows=[]
 for d in s.query(Document).filter(Document.status.in_(tasks)).order_by(Document.updated_at.desc()).limit(100):
  permission,title,message=tasks[d.status]
  assigned=u.department_id in json.loads(d.assignee_ids or '[]')
  if d.status=='FORWARDED':
   if u.role!='ADMIN' and not assigned:continue
  elif not has_permission(s,u,permission):continue
  if not view(u,d,s):continue
  rows.append({'id':f'{d.id}:{d.status}:{d.updated_at.isoformat()}','document_id':d.id,'direction':d.direction,'status':d.status,'symbol':d.symbol,'document_title':d.title,'title':title,'message':message,'created_at':d.updated_at})
 return rows
@app.post('/api/documents/{did}/email')
def email(did:int,recipients:list[str],u=Depends(current),s:Session=Depends(db)):
 d=s.get(Document,did)
 if not d or not view(u,d,s):raise HTTPException(404)
 require_permission(s,u,'EMAIL','Bạn không có quyền gửi email văn bản')
 log(s,d,u,'EMAIL',', '.join(recipients));s.commit();return {'status':'simulated','recipients':recipients}

@app.get('/api/health')
def health():return {'status':'ok'}

# Serve the compiled React application from the same process in production.
# This catch-all mount must remain after every API route.
FRONTEND_DIST=ROOT.parent/'frontend'/'dist'
if FRONTEND_DIST.is_dir():
 app.mount('/assets',StaticFiles(directory=FRONTEND_DIST/'assets'),name='frontend-assets')
 @app.get('/{full_path:path}',include_in_schema=False)
 def frontend_app(full_path:str):
  if full_path.startswith('api/'):raise HTTPException(404,'Không tìm thấy API')
  return FileResponse(FRONTEND_DIST/'index.html')
