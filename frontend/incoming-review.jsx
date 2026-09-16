import { prepareGmail, GmailDraft } from './gmail.jsx';
import EmailTemplates from './email-templates.jsx';
import React, { useEffect, useRef, useState } from 'react';
import './incoming-review.css';

const statuses = {PENDING_BGH:'Chờ BGH duyệt',DEPARTMENT_REVIEW:'Chờ các đơn vị phản hồi',REVIEW_CHANGES:'Có yêu cầu chỉnh sửa',REVIEW_READY:'Đã hoàn tất duyệt — có thể lưu trữ',FORWARDED:'Đã gửi email',ARCHIVED:'Đã lưu trữ'};
const decisionName = d => d?.decision === 'APPROVE' ? 'Đã đồng ý' : d?.decision === 'REPORT' ? 'Đã gửi báo cáo' : d?.decision === 'REJECT' ? 'Yêu cầu sửa' : 'Chưa phản hồi';
const responsibilityGroups = ['Đơn vị chủ trì xử lý','Đơn vị đồng chủ trì xử lý','Đơn vị phối hợp','Đơn vị tiếp nhận thông tin'];
export default function IncomingReviewDialog({action,call,deps,close,done}) {
  const [draft,setDraft]=useState(null);
  const [data,setData]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [note,setNote]=useState(''),[assignments,setAssignments]=useState([]),[comment,setComment]=useState('');
  const [pdf,setPdf]=useState('');
  const [deadline,setDeadline]=useState(''),[purpose,setPurpose]=useState('');
  const [openRole,setOpenRole]=useState(''),[unitQuery,setUnitQuery]=useState('');
  const groupsRef=useRef(null), reportForm=useRef(null);
  const base=`/documents/${action.document.id}/review`;
  async function refresh(){const r=await call(base);setData(r);setNote(r.note);setPurpose(r.purpose || "");setAssignments(r.assignments.map(a=>({...a,responsibility:a.responsibility || 'Đơn vị phối hợp'})));setDeadline(r.assignments[0]?.deadline || "");}
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[action.document.id]);
  useEffect(()=>{if(!openRole)return;const outside=e=>{if(!groupsRef.current?.contains(e.target))setOpenRole('');},escape=e=>{if(e.key==='Escape')setOpenRole('');};document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',escape);};},[openRole]);
  useEffect(()=>{
    if(!data)return;
    const controller=new AbortController();let url='';setPdf('');
    fetch(`${import.meta.env.VITE_API_URL || '/api'}/documents/${action.document.id}/file`,{headers:{Authorization:`Bearer ${localStorage.token}`},cache:'no-store',signal:controller.signal})
      .then(r=>{if(!r.ok)throw Error('Không tải được PDF');return r.blob();})
      .then(b=>{if(controller.signal.aborted)return;url=URL.createObjectURL(b);setPdf(url);})
      .catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>{controller.abort();if(url)URL.revokeObjectURL(url);};
  },[data?.revision]);
  async function send(path,body){
    setBusy(true);setError('');
    try{const request=()=>call(`${base}/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:data.revision,...body})});if(path==='email'){setDraft({...await prepareGmail(request),review_revision:data.revision});}else{await request();setComment('');await refresh();}}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function sendReport(e){
    e.preventDefault();setBusy(true);setError('');
    try{const body=new FormData(e.currentTarget);body.set('revision',data.revision);await call(`${base}/report`,{method:'POST',body});setComment('');await refresh();e.currentTarget.reset();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function downloadReport(item){
    setError('');
    try{const response=await fetch(`${import.meta.env.VITE_API_URL || '/api'}/documents/${action.document.id}/review/reports/${item.id}`,{headers:{Authorization:`Bearer ${localStorage.token}`}});if(!response.ok)throw Error((await response.json()).detail || 'Không tải được báo cáo');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=item.report_file_name;link.click();URL.revokeObjectURL(url);}
    catch(e){setError(e.message);}
  }
  function select(dep,responsibility,checked){setAssignments(items=>checked?[...items.filter(x=>x.department_id!==dep.id),{department_id:dep.id,name:dep.name,email:dep.email || '',responsibility}]:items.filter(x=>!(x.department_id===dep.id&&x.responsibility===responsibility)));}
  function normalized(value){return (value||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[đĐ]/g,'d').toLowerCase();}
  return <div className="modal incoming-review-overlay">
    <section className="incoming-review-panel" role="dialog" aria-modal="true" aria-labelledby="incoming-review-title">
    <div className="incoming-review-heading"><h2 id="incoming-review-title">Giao việc và phản hồi công văn đến</h2><button type="button" disabled={busy} onClick={done} aria-label="Đóng hộp thoại">Đóng</button></div>
    <p><b>{action.document.symbol}</b> · {action.document.title}</p>
    {error&&<p className="form-error" role="alert">{error}</p>}
    {!data?<p>Đang tải hồ sơ...</p>:<>
      <p role="status"><b>Vòng {data.revision || 'chưa trình'}</b> · {statuses[data.status] || 'Chánh VP chuẩn bị phiếu giao việc'}</p>
      <p>Chánh VP trình phiếu → BGH duyệt → các đơn vị đọc và đồng ý. Có yêu cầu sửa thì Chánh VP trình vòng mới; mọi xác nhận được lấy lại trước khi gửi email.</p>
      {pdf&&<details open><summary>Đọc công văn và phiếu đính kèm</summary><object data={pdf} type="application/pdf" style={{width:'100%',height:420}}><a href={pdf} target="_blank" rel="noreferrer">Mở PDF</a></object></details>}
      {data.revision>0&&<>
        <h3>Trạng thái đồng ý của vòng hiện tại</h3><p>Mục đích: {data.purpose || "Không nhập"}</p><p>Hạn xử lý: {data.assignments[0]?.deadline || "Không đặt"}</p>
        <table><thead><tr><th>Đơn vị</th><th>Email nhận việc</th><th>Xác nhận</th></tr></thead><tbody>
          <tr><td>Ban Giám hiệu</td><td>Phê duyệt trên hệ thống</td><td>{decisionName(data.decisions.BGH)}</td></tr>
          {data.assignments.map(a=><tr key={a.department_id}><td>{a.name}</td><td>{deps.find(d=>d.id===a.department_id)?.email || 'Chưa cấu hình'}{a.responsibility&&<small> · {a.responsibility}</small>}</td><td>{decisionName(data.decisions[String(a.department_id)])}</td></tr>)}
        </tbody></table>
      </>}
      {data.can_submit&&<form onSubmit={e=>{e.preventDefault();send('submit',{note,purpose,deadline:deadline || null,assignments:assignments.map(({department_id,responsibility})=>({department_id,responsibility}))});}}>
        <h3>{data.revision?'Sửa phiếu và trình BGH vòng tiếp theo':'Lập phiếu giao việc'}</h3>
        <label>Mục đích (không bắt buộc)<input value={purpose} maxLength={500} placeholder="Ví dụ: Để báo cáo" onChange={e=>setPurpose(e.target.value)}/></label>
        <label>Nội dung phân công trên phiếu đính kèm<textarea required value={note} onChange={e=>setNote(e.target.value)} rows={6}/></label>
        <p>Giao đơn vị xử lý (không bắt buộc). Có thể không chọn đơn vị nào, hoặc mở từng vai trò để chọn một hay nhiều đơn vị. Mỗi đơn vị chỉ thuộc một vai trò; chọn vai trò mới sẽ tự chuyển đơn vị.</p>
        <div className="incoming-responsibility-groups" ref={groupsRef}>{responsibilityGroups.map(responsibility=>{
          const selected=assignments.filter(a=>a.responsibility===responsibility),count=selected.length,open=openRole===responsibility;
          const visible=deps.filter(d=>d.code!=='BGH'&&normalized(d.name).includes(normalized(unitQuery)));
          return <section key={responsibility} className={`incoming-responsibility-group${open?' is-open':''}`}><label>{responsibility}</label><button type="button" className="incoming-department-trigger" aria-expanded={open} onClick={()=>{setOpenRole(open?'':responsibility);setUnitQuery('');}}><span title={selected.map(a=>a.name).join(', ')}>{count?selected.map(a=>a.name).join(', '):'-- Chọn đơn vị --'}</span><b>{count} đơn vị</b><i aria-hidden="true">▾</i></button>{open&&<div className="incoming-department-menu"><div className="incoming-department-search"><input autoFocus value={unitQuery} onChange={e=>setUnitQuery(e.target.value)} placeholder="Tìm tên đơn vị..." aria-label={`Tìm trong ${responsibility}`}/></div><div className="incoming-department-options">{visible.map(dep=>{
            const current=assignments.find(a=>a.department_id===dep.id),checked=current?.responsibility===responsibility;
            return <label key={dep.id} className={`incoming-department-option${checked?' selected':''}`}><input type="checkbox" checked={checked} onChange={e=>select(dep,responsibility,e.target.checked)}/><span><b>{dep.name}</b><small>{current&&!checked?`Đang thuộc: ${current.responsibility}`:`Email: ${dep.email || 'Chưa cấu hình'}`}</small></span></label>;
          })}{!visible.length&&<p className="incoming-department-empty">Không tìm thấy đơn vị</p>}</div><footer><span>Đã chọn {count} đơn vị</span><div>{count>0&&<button type="button" onClick={()=>setAssignments(items=>items.filter(a=>a.responsibility!==responsibility))}>Bỏ chọn</button>}<button type="button" className="primary" onClick={()=>setOpenRole('')}>Xong</button></div></footer></div>}</section>;
        })}</div>
        <label>Hạn xử lý (không bắt buộc)<input type="date" value={deadline} onChange={e=>setDeadline(e.target.value)}/></label>
        <button className="primary" disabled={busy}>{busy?'Đang xử lý...':data.revision?'Lưu phiếu mới và trình BGH duyệt lại':'Tạo phiếu và trình BGH'}</button>
        {data.revision>0&&<p>Trình lại sẽ tạo vòng mới và yêu cầu BGH cùng tất cả đơn vị xác nhận lại. PDF gốc được giữ nguyên.</p>}
      </form>}
      {data.can_comment&&<section>
        <h3>Trao đổi trên hệ thống</h3>
        <textarea aria-label="Nội dung phản hồi" rows={3} placeholder="Nhập bình luận hoặc nội dung cần chỉnh sửa" value={comment} onChange={e=>setComment(e.target.value)}/>
        <div className="end">
          <button disabled={busy||!comment.trim()} onClick={()=>send('respond',{decision:'COMMENT',comment})}>Gửi bình luận</button>
          {data.can_decide&&<><button disabled={busy||!comment.trim()} onClick={()=>send('respond',{decision:'REJECT',comment})}>Không đồng ý / Yêu cầu sửa</button><button className="primary" disabled={busy} onClick={()=>send('respond',{decision:'APPROVE',comment})}>Đã đọc và đồng ý</button></>}
        </div>
      </section>}
      {data.can_report&&<form ref={reportForm} onSubmit={sendReport}>
        <h3>Gửi báo cáo xử lý</h3>
        <EmailTemplates defaultKind="monthly_report" onApply={template => {
          const input = reportForm.current?.elements.namedItem('comment');
          if (input) input.value = template.content;
        }} />
        <p>Gửi nội dung báo cáo cho Chánh Văn phòng và BGH. Có thể đính kèm một tệp PDF, DOC hoặc DOCX.</p>
        <textarea name="comment" rows={4} placeholder="Nhập nội dung hoặc kết quả xử lý" />
        <label>Tệp báo cáo (không bắt buộc)<input name="file" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" /></label>
        <button className="primary" disabled={busy}>{busy?'Đang gửi...':'Gửi lại báo cáo'}</button>
      </form>}
      {data.can_email&&<section>
        <h3>Gửi email báo việc</h3>
        {data.email_template && <details open><summary>Nội dung email theo mẫu</summary><b>{data.email_template.subject}</b><p style={{whiteSpace:'pre-wrap'}}>{data.email_template.content}</p></details>}
        <p>BGH và tất cả đơn vị đã đồng ý vòng {data.revision}. Tải PDF và phiếu hiện tại để đính kèm trong Gmail.</p>
        <p>Mục đích: {data.purpose || "Không nhập"}</p><p>Mục đích và deadline được lấy từ phiếu đã duyệt. Muốn thay đổi, hãy sửa phiếu và trình lại.</p>
        {data.assignments.map(a=><p key={a.department_id}>{a.name}: {a.responsibility || 'Không chọn vai trò'} — {deps.find(d=>d.id===a.department_id)?.email || 'Chưa cấu hình email'}</p>)}
        <p>Hạn xử lý: {data.assignments[0]?.deadline || 'Không đặt'}</p>
        <button className="primary" disabled={busy} onClick={()=>send('email',{decision:'EMAIL'})}>{busy?'Đang mở...':'Mở Gmail để gửi mail'}</button>
      </section>}
      <GmailDraft draft={draft} onConfirm={async () => {
        setBusy(true);
        try { await call(`/documents/${action.document.id}/gmail-confirm`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:draft.document.revision,review_revision:draft.review_revision})}); setDraft(null); await refresh(); }
        catch(e) {setError(e.message);} finally {setBusy(false);}
      }} />
      <button disabled={busy} onClick={()=>refresh().catch(e=>setError(e.message))}>Tải lại phản hồi và phiếu hiện tại</button>
      <h3>Lịch sử trao đổi và duyệt</h3>
      {!data.comments.length&&<p>Chưa có phản hồi.</p>}
      {data.comments.map((c,i)=><article key={i} style={{borderBottom:'1px solid #ddd',padding:'10px 0'}}><b>{c.user}</b> · Vòng {c.revision} · {({REVIEW_SUBMIT:'Trình phiếu',REVIEW_APPROVE:'Đồng ý',REVIEW_REJECT:'Yêu cầu sửa',REVIEW_COMMENT:'Bình luận',REVIEW_REPORT:'Gửi báo cáo',REVIEW_EMAIL:'Gửi email'})[c.action]}<small> · {c.created_at}</small><p style={{whiteSpace:'pre-wrap'}}>{c.comment}</p>{c.report_file_name&&<p><button type="button" onClick={()=>downloadReport(c)}>Tải báo cáo: {c.report_file_name}</button></p>}{c.deadline&&<p>Hạn xử lý: {c.deadline.split('-').reverse().join('/')}</p>}{c.delivery&&<ul>{c.delivery.map(a=><li key={a.department_id}>{a.name} — {a.email}{a.responsibility?` — ${a.responsibility}`:''}</li>)}</ul>}</article>)}
      {data.rounds.map(r=><details key={r.revision}><summary>Phiếu vòng {r.revision}</summary><p>Mục đích: {r.assignments[0]?.purpose || "Không nhập"}</p><p style={{whiteSpace:'pre-wrap'}}>{r.note}</p><ul>{r.assignments.map(a=><li key={a.department_id}>{a.name} — {a.email} — {decisionName(r.decisions[String(a.department_id)])}</li>)}</ul><p>BGH: {decisionName(r.decisions.BGH)}</p></details>)}
    </>}
    <div className="end"><button disabled={busy} onClick={()=>{done();}}>Đóng và cập nhật danh sách</button></div>
    </section>
  </div>;
}
