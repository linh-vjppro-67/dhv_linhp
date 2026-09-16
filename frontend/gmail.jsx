import React, { useState } from 'react';

export async function prepareGmail(request) {
  const tab = window.open('about:blank', '_blank');
  if (tab) tab.opener = null;
  try {
    const draft = await request();
    if (tab) tab.location.replace(draft.gmail_url);
    return draft;
  } catch (error) {
    if (tab) tab.close();
    throw error;
  }
}

export function GmailDraft({ draft, onConfirm }) {
  const [error, setError] = useState('');
  if (!draft) return null;
  async function download() {
    try {
      const r = await fetch((import.meta.env.VITE_API_URL || '/api') + draft.attachment_url, {
        headers: {Authorization: `Bearer ${localStorage.token}`},
      });
      if (!r.ok) throw Error('Không tải được tệp đính kèm');
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a');
      a.href = url; a.download = draft.attachment_name || 'van-ban.pdf'; a.click();
      setTimeout(()=>URL.revokeObjectURL(url), 10000);
    } catch (e) { setError(e.message); }
  }
  return <section className="panel">
    <p>Đăng nhập Gmail bằng <b>{draft.gmail_account}</b>, kiểm tra người nhận và nội dung, đính kèm PDF rồi bấm Gửi trong Gmail.</p>
    <p>Hồ sơ chưa được đánh dấu đã gửi.</p>
    <a href={draft.gmail_url} target="_blank" rel="noreferrer">Mở cửa sổ soạn thư Gmail</a>{' '}
    <button type="button" onClick={download}>Tải PDF để đính kèm</button>
    {onConfirm && <button type="button" onClick={onConfirm}>Tôi đã gửi thư trong Gmail</button>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
