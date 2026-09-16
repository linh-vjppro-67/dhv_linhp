import React, { useEffect, useState } from 'react';

export default function EmailTemplates({ onApply, defaultKind = "monthly_reminder" }) {
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  });
  const [unit, setUnit] = useState('');
  const [kind, setKind] = useState(defaultKind);
  const [templates, setTemplates] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    setTemplates(null);
    if (!month) return;
    const controller = new AbortController();
    const query = new URLSearchParams({month: month + '-01', unit});
    fetch(`${import.meta.env.VITE_API_URL || '/api'}/email-templates?${query}`, {
      headers: {Authorization: `Bearer ${localStorage.token}`}, signal: controller.signal,
    }).then(async r => {
      const data = await r.json();
      if (!r.ok) throw Error(data.detail || 'Không tải được mẫu email');
      setTemplates(data); setError('');
    }).catch(e => { if (e.name !== 'AbortError') setError(e.message); });
    return () => controller.abort();
  }, [month, unit]);
  const template = templates?.[kind];
  return <details className="panel">
    <summary>Mẫu email báo cáo tháng</summary>
    <div className="grid">
      <label>Loại mẫu<select value={kind} onChange={e=>setKind(e.target.value)}>
        <option value="monthly_reminder">Văn phòng nhắc báo cáo tháng</option>
        <option value="monthly_report">Đơn vị gửi báo cáo tháng</option>
      </select></label>
      <label>Tháng báo cáo<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label>
      {kind === 'monthly_report' && <label>Tên đơn vị<input value={unit} onChange={e=>setUnit(e.target.value)} placeholder="Mặc định: đơn vị của tài khoản"/></label>}
    </div>
    {error && <p role="alert">{error}</p>}
    {template && <>
      {kind === 'monthly_reminder' && <p>Ngày nhắc: {template.send_date.split('-').reverse().join('/')} · Hạn nộp: {template.deadline.split('-').reverse().join('/')}.</p>}
      <label>Tiêu đề<input readOnly value={template.subject}/></label>
      <label>Nội dung<textarea readOnly rows={12} value={template.content}/></label>
      {onApply && <button type="button" onClick={()=>onApply(template)}>Dùng mẫu này</button>}
    </>}
  </details>;
}
