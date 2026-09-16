import { DOCUMENT_TYPES, ARCHIVE_TYPES } from './document-types.mjs';
import { prepareGmail, GmailDraft } from './gmail.jsx';
import EmailTemplates from './email-templates.jsx';
import IncomingReviewDialog from "./incoming-review.jsx";
import React, { useEffect, useRef, useState } from "react";
import { requestPdfTitle } from "./pdf-title.mjs";
import { createRoot } from "react-dom/client";
import {
  LayoutDashboard,
  Inbox,
  Send,
  Archive,
  Search,
  Settings,
  LogOut,
  Plus,
  FileText,
  Clock,
  ShieldCheck,
  Bell,
  CheckCheck,
  Bot,
  Files,
  BarChart3,
  Download,
} from "lucide-react";
import logo from "./assets/dhv.png";
import "./style.css";
import "./logo.css";
import "./edit.css";
const API = import.meta.env.VITE_API_URL || "/api";
const normalizeExactSearch = (value) => String(value || "").replace(/[Đđ]/g,"d").normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/\s+/g," ").trim();
let sessionTimer;
function logoutExpired() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  sessionStorage.setItem(
    "session_message",
    "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
  );
  location.replace("/login");
}
function scheduleSessionExpiry(token = localStorage.token) {
  clearTimeout(sessionTimer);
  if (!token) return;
  try {
    let payload = JSON.parse(
        atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
      ),
      remaining = payload.exp * 1000 - Date.now();
    if (remaining <= 0) logoutExpired();
    else sessionTimer = setTimeout(logoutExpired, remaining);
  } catch {
    logoutExpired();
  }
}
const nativeFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  let response = await nativeFetch(...args),
    url = String(args[0] || "");
  if (response.status === 401 && !url.includes("/auth/login")) logoutExpired();
  return response;
};
scheduleSessionExpiry();
if (!localStorage.token && location.pathname !== "/login")
  history.replaceState({}, "", "/login");
if (localStorage.token && location.pathname === "/login")
  history.replaceState({}, "", "/");
const TAB_PATHS = {
  "Tổng quan": "/",
  "Công văn đến": "/cv-den",
  "Công văn đi": "/cv-di",
  "Lưu trữ": "/luu-tru",
  "Theo dõi báo cáo": "/theo-doi-bao-cao",
  "Tra cứu văn bản": "/tra-cuu",
  "Phân tích văn bản": "/phan-tich",
  "Lập báo cáo tổng hợp": "/bao-cao-ai",
  "Cấu hình hệ thống": "/cau-hinh",
};
const PATH_TABS = {
  ...Object.fromEntries(
    Object.entries(TAB_PATHS).map(([tab, path]) => [path, tab]),
  ),
  "/cv-noi-bo": "Công văn đi",
  "/tro-ly-ai": "Tra cứu văn bản",
};
const schoolUnits = (departments = []) => departments.filter((unit) => unit.code !== "BGH");
const ACTION_LABELS = {
  CREATE: "Tạo văn bản",
  EDIT_RECEIVED: "Sửa công văn đến",
  EDIT_OUTGOING: "Sửa công văn đi",
  RESERVE_NUMBER: "Xin số trước",
  RESERVATION_SUBMIT: "Trình xin số trước",
  RESERVATION_RESUBMIT: "Trình lại yêu cầu xin số",
  RESERVATION_APPROVE: "Văn thư duyệt xin số",
  RESERVATION_REJECT: "Văn thư từ chối xin số",
  RESERVATION_DELETE: "Xoá yêu cầu xin số bị từ chối",
  RESERVE_INCOMING_NUMBER: "Xin số đến trước",
  ATTACH_RESERVED_DOCUMENT: "Bổ sung văn bản",
  INCOMING_NUMBER: "Vào số công văn đến",
  OUTGOING_NUMBER: "Cấp số công văn đi",
  INTERNAL_NUMBER: "Cấp số văn bản nội bộ",
  INTERNAL_SUBMIT_OFFICE: "Trình duyệt văn bản nội bộ",
  INTERNAL_APPROVED: "Phê duyệt văn bản nội bộ",
  OFFICE_OPINION: "Ghi ý kiến Chánh Văn phòng",
  OFFICE_OPINION_DIGITALLY_SIGNED: "Ký số ý kiến Chánh Văn phòng",
  SEND_BGH: "Gửi Ban Giám hiệu",
  BGH_DECISION: "Ban Giám hiệu xử lý",
  FORWARD: "Chuyển đơn vị",
  UNIT_DIGITAL_SIGN: "Trưởng đơn vị ký số",
  BGH_DIGITAL_SIGN: "BGH ký số",
  OUTGOING_SUBMIT_BGH_APPROVAL: "Gửi BGH duyệt",
  OUTGOING_SUBMIT_BGH_SIGN: "Gửi BGH duyệt và ký số",
  OUTGOING_BGH_APPROVE: "BGH duyệt văn bản",
  OUTGOING_SUBMIT_OFFICE: "Trình Chánh Văn phòng",
  OUTGOING_RETURN: "Trả lại văn bản",
  OFFICE_DIGITAL_SIGN_POSITION: "Ký số",
  DIGITAL_SEAL: "Đóng dấu",
  OUTGOING_EMAIL: "Phát hành công văn đi",
  INTERNAL_EMAIL_PUBLISH: "Phát hành văn bản nội bộ",
  GMAIL_SEND_CONFIRMED: "Người dùng xác nhận đã gửi qua Gmail",
  ARCHIVE: "Lưu trữ và OCR",
  SOFT_DELETE: "Xóa văn bản",
  RENAME_FILE: "Đổi tên file",
  RESTORE: "Khôi phục văn bản",
};
function App() {
  const [token, setToken] = useState(localStorage.token || ""),
    [user, setUser] = useState(JSON.parse(localStorage.user || "null")),
    [tab, setTab] = useState(PATH_TABS[location.pathname] || "Tổng quan"),
    [data, setData] = useState([]),
    [dash, setDash] = useState({}),
    [q, setQ] = useState(""),
    [show, setShow] = useState(false),
    [cfg, setCfg] = useState({
      departments: [],
      sequences: [],
      users: [],
      permissions: [],
    }),
    [notifications, setNotifications] = useState([]),
    documentRequest = useRef(0),
    searchReady = useRef(false);
  const call = async (p, o = {}) => {
    let r = await fetch(API + p, {
      ...o,
      headers: { Authorization: `Bearer ${token}`, ...o.headers },
    });
    if (!r.ok) throw Error((await r.json()).detail || "Có lỗi");
    return r.json();
  };
  const loadDocuments = () => {
    if (!token) return;
    if (["BGH","DEPARTMENT","DEPARTMENT_HEAD"].includes(user?.role) && !["Công văn đến","Công văn đi"].includes(tab)) return;
    let dir =
        tab === "Công văn đến"
          ? "IN"
          : tab === "Công văn đi"
            ? "OUT"
            : tab === "Công văn nội bộ"
              ? "INTERNAL"
              : "",
      archived = ["Lưu trữ", "Tra cứu văn bản"].includes(tab);
    if (!["Tổng quan", "Cấu hình hệ thống", "Theo dõi báo cáo"].includes(tab)) {
      const request = ++documentRequest.current;
      call(
        `/documents?${dir ? "direction=" + dir + "&" : ""}${tab === "Lưu trữ" ? "archive_workspace=true&" : archived ? "status=ARCHIVED&" : ""}${q ? "q=" + encodeURIComponent(q) : ""}`,
      ).then((rows) => request === documentRequest.current && setData(rows));
    }
  };
  const load = () => {
    if (!token) return;
    if (["ADMIN", "CLERK", "OFFICE_HEAD"].includes(user?.role))
      call("/dashboard").then(setDash);
    call("/config").then(setCfg);
    call("/notifications").then(setNotifications);
    loadDocuments();
  };
  function navigate(next) {
    if (next === tab) return;
    history.pushState({}, "", TAB_PATHS[next]);
    setTab(next);
    setShow(false);
  }
  useEffect(() => {
    const back = () => {
      setTab(PATH_TABS[location.pathname] || "Tổng quan");
      setShow(false);
    };
    addEventListener("popstate", back);
    return () => removeEventListener("popstate", back);
  }, []);
  useEffect(load, [token, tab]);
  useEffect(() => {
    if (!searchReady.current) {
      searchReady.current = true;
      return;
    }
    const timer = setTimeout(loadDocuments, 250);
    return () => clearTimeout(timer);
  }, [q]);
  useEffect(() => {
    if (!token) return;
    let timer = setInterval(
      () => call("/notifications").then(setNotifications),
      30000,
    );
    return () => clearInterval(timer);
  }, [token]);
  useEffect(() => {
    const unitAccount = ["BGH", "DEPARTMENT", "DEPARTMENT_HEAD"].includes(user?.role);
    if (unitAccount && !["Công văn đến", "Công văn đi"].includes(tab)) {
      history.replaceState({}, "", TAB_PATHS["Công văn đến"]);
      setTab("Công văn đến");
    } else if (user && user.role !== "ADMIN" && tab === "Cấu hình hệ thống") {
      history.replaceState({}, "", TAB_PATHS["Tổng quan"]);
      setTab("Tổng quan");
    }
  }, [user, tab]);
  if (!token)
    return (
      <Login
        done={(t, u) => {
          localStorage.token = t;
          localStorage.user = JSON.stringify(u);
          setToken(t);
          setUser(u);
        }}
      />
    );
  let menu = [
      ["Tổng quan", LayoutDashboard],
      ["Công văn đến", Inbox],
      ["Công văn đi", Send],
      ["Lưu trữ", Archive],
      ["Theo dõi báo cáo", BarChart3],
      ["Tra cứu văn bản", Search],
      ["Phân tích văn bản", Files],
      ["Lập báo cáo tổng hợp", BarChart3],
      ["Cấu hình hệ thống", Settings],
    ].filter(
      ([name]) =>
        (!["BGH", "DEPARTMENT", "DEPARTMENT_HEAD"].includes(user.role) || ["Công văn đến", "Công văn đi"].includes(name)) &&
        (name !== "Cấu hình hệ thống" || user.role === "ADMIN") &&
        (!["Phân tích văn bản", "Lập báo cáo tổng hợp"].includes(name) ||
          (cfg.permissions || []).includes("AI_CHAT")),
    ),
    direction =
      tab === "Công văn đến"
        ? "IN"
        : tab === "Công văn đi"
          ? "OUT"
          : "INTERNAL",
    descriptions = {
      "Tổng quan": "Theo dõi tình hình xử lý và lưu trữ văn bản",
      "Công văn đến": "Tiếp nhận, xử lý và theo dõi công văn đến",
      "Công văn đi": "Lãnh đạo đơn vị ký thì BGH duyệt; chưa ký thì BGH duyệt và ký số; hoàn tất sẽ chuyển Văn thư",
      "Công văn nội bộ": "Quản lý và phát hành văn bản trong trường",
      "Lưu trữ": "Tra cứu hồ sơ văn bản đã hoàn tất",
      "Theo dõi báo cáo": "Theo dõi tiến độ nộp báo cáo của từng đơn vị và các hạn sắp đến",
      "Tra cứu văn bản":
        "Tìm chính xác theo hồ sơ hoặc hỏi đáp thông minh bằng AI",
      "Phân tích văn bản":
        "Hỏi, tổng hợp và đối chiếu trên các văn bản được chọn",
      "Lập báo cáo tổng hợp":
        "Soạn bản thảo hoàn chỉnh từ nội dung các văn bản được xác nhận",
      "Cấu hình hệ thống":
        "Quản lý người dùng, phân quyền và cấu hình hệ thống",
    },
    documentTab = ["Công văn đến", "Công văn đi", "Công văn nội bộ"].includes(
      tab,
    ),
    can = (code) => (cfg.permissions || []).includes(code);
  return (
    <div className="shell">
      <aside>
        <div className="brand">
          <img src={logo} alt="Logo Đại học Hùng Vương" />
          <span>
            TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG<small>QUẢN LÝ VĂN BẢN</small>
          </span>
        </div>
        {menu.map(([n, I]) => (
          <button
            key={n}
            className={tab === n ? "on" : ""}
            onClick={() => navigate(n)}
          >
            <I size={19} />
            {n}
          </button>
        ))}
      </aside>
      <main>
        <header className="page-header">
          <div>
            <h1>{tab}</h1>
            <p>{descriptions[tab]}</p>
          </div>
          <div className="header-actions">
            <NotificationCenter
              items={notifications}
              user={user}
              navigate={navigate}
            />
            <AccountMenu user={user} departments={cfg.departments} />
          </div>
        </header>
        <div className="page-content">
          {documentTab && ((tab !== "Công văn đến" && ["DEPARTMENT", "DEPARTMENT_HEAD", "ADMIN", "CLERK", "OFFICE_HEAD"].includes(user.role) && can("RESERVE_NUMBER")) || (can("CREATE") && (tab === "Công văn đi" || (tab === "Công văn đến" && !["DEPARTMENT", "DEPARTMENT_HEAD"].includes(user.role))))) && (
            <div className="content-actions">
              {tab !== "Công văn đến" && ["DEPARTMENT", "DEPARTMENT_HEAD", "ADMIN", "CLERK", "OFFICE_HEAD"].includes(user.role) && can("RESERVE_NUMBER") && (
                <button onClick={() => setShow("reserve")}>Xin số trước</button>
              )}
              {can("CREATE") && tab === "Công văn đi" && (
                <button className="primary" onClick={() => setShow("create")}>
                  <Plus />
                  Tạo văn bản
                </button>
              )}
              {can("CREATE") && tab === "Công văn đến" && !["DEPARTMENT", "DEPARTMENT_HEAD"].includes(user.role) && (
                <button className="primary" onClick={() => setShow("create")}>
                  <Plus />
                  Tạo văn bản
                </button>
              )}
            </div>
          )}
          {tab === "Lưu trữ" && can("CREATE") && <div className="content-actions"><button className="primary" onClick={() => setShow("archiveUpload")}><Plus />Gửi hồ sơ lưu trữ</button></div>}
          {tab === "Tổng quan" ? (
            <Dashboard d={dash} call={call} />
          ) : tab === "Cấu hình hệ thống" && user.role === "ADMIN" ? (
            <Config c={cfg} />
          ) : tab === "Tra cứu văn bản" ? (
            <DocumentLookup
              rows={data}
              q={q}
              setQ={setQ}
              load={load}
              call={call}
              token={token}
              deps={cfg.departments}
              emailConfig={cfg.email || {}}
              permissions={cfg.permissions || []}
            />
          ) : tab === "Theo dõi báo cáo" ? (
            <ReportTrackingPage call={call} />
          ) : tab === "Phân tích văn bản" ? (
            <DocumentAnalysis call={call} />
          ) : tab === "Lập báo cáo tổng hợp" ? (
            <AIReports call={call} />
          ) : (
            <Docs
              rows={data}
              q={q}
              setQ={setQ}
              load={load}
              call={call}
              token={token}
              deps={cfg.departments}
              emailConfig={cfg.email || {}}
              permissions={cfg.permissions || []}
              archive={tab === "Lưu trữ"}
              original={tab === "Lưu trữ"}
            />
          )}
        </div>
      </main>
      {show === "create" && (
        <Create
          direction={direction}
          deps={cfg.departments}
          token={token}
          close={() => setShow(false)}
          saved={() => {
            setShow(false);
            load();
          }}
        />
      )}
      {show === "reserve" && tab !== "Công văn đến" && ["DEPARTMENT", "DEPARTMENT_HEAD", "ADMIN", "CLERK", "OFFICE_HEAD"].includes(user.role) && (
        <ReserveNumber
          user={user}
          direction={direction}
          deps={cfg.departments}
          token={token}
          close={() => setShow(false)}
          saved={() => {
            setShow(false);
            load();
          }}
        />
      )}
      {show === "archiveUpload" && <DirectArchiveUpload token={token} direct={can("ARCHIVE")} close={() => setShow(false)} saved={() => {setShow(false);load();}} />}
    </div>
  );
}
function NotificationCenter({ items, user, navigate }) {
  const [open, setOpen] = useState(false),
    key = `dhv-notifications-read-${user.id}`,
    [read, setRead] = useState(() =>
      JSON.parse(localStorage.getItem(key) || "[]"),
    ),
    root = useRef(null);
  useEffect(() => {
    if (!open) return;
    function outside(e) {
      if (!root.current?.contains(e.target)) setOpen(false);
    }
    function escape(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  const unread = items.filter((x) => !read.includes(x.id));
  function persist(ids) {
    setRead(ids);
    localStorage.setItem(key, JSON.stringify(ids));
  }
  function openItem(item) {
    persist([...new Set([...read, item.id])]);
    setOpen(false);
    navigate(
      item.direction === "ARCHIVE"
        ? "Lưu trữ"
        : item.direction === "REPORT"
          ? "Theo dõi báo cáo"
        : item.direction === "IN"
        ? "Công văn đến"
        : item.direction === "OUT"
          ? "Công văn đi"
          : "Công văn đi",
    );
  }
  return (
    <div className="notification-center" ref={root}>
      <button
        className="notification-trigger"
        onClick={() => setOpen((x) => !x)}
        aria-label="Thông báo"
        aria-expanded={open}
      >
        <Bell />
        {unread.length > 0 && (
          <b>{unread.length > 99 ? "99+" : unread.length}</b>
        )}
      </button>
      {open && (
        <div className="notification-popover">
          <header>
            <div>
              <strong>Thông báo</strong>
              <small>{unread.length} chưa đọc</small>
            </div>
            {unread.length > 0 && (
              <button onClick={() => persist(items.map((x) => x.id))}>
                <CheckCheck />
                Đọc tất cả
              </button>
            )}
          </header>
          <div className="notification-list">
            {items.length ? (
              items.map((item) => (
                <button
                  key={item.id}
                  className={read.includes(item.id) ? "" : "unread"}
                  onClick={() => openItem(item)}
                >
                  <span className="notification-dot" />
                  <span>
                    <strong>{item.title}</strong>
                    <small>
                      {item.symbol || "Chưa cấp số"} · {item.document_title}
                    </small>
                    <p>{item.message}</p>
                    <time>
                      {new Date(item.created_at).toLocaleString("vi-VN")}
                    </time>
                  </span>
                </button>
              ))
            ) : (
              <div className="notification-empty">
                <Bell />
                <b>Không có thông báo mới</b>
                <small>Các công việc cần xử lý sẽ xuất hiện tại đây.</small>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
function AccountMenu({ user, departments }) {
  const [open, setOpen] = useState(false),
    root = useRef(null),
    department =
      departments.find((x) => x.id === user.department_id)?.name ||
      "Chưa gán đơn vị",
    initials = user.full_name
      .split(/\s+/)
      .slice(0, 2)
      .map((x) => x[0])
      .join("")
      .toUpperCase(),
    roleName =
      {
        ADMIN: "Quản trị hệ thống",
        BGH: "Ban Giám hiệu",
        OFFICE_HEAD: "Chánh Văn phòng",
        CLERK: "Văn thư",
        DEPARTMENT: "Đơn vị xử lý",
        DEPARTMENT_HEAD: "Trưởng đơn vị",
      }[user.role] || user.role;
  useEffect(() => {
    if (!open) return;
    function outside(e) {
      if (!root.current?.contains(e.target)) setOpen(false);
    }
    function escape(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div className="account-menu" ref={root}>
      <button
        className="account-trigger"
        onClick={() => setOpen((x) => !x)}
        aria-label="Thông tin cá nhân"
        aria-expanded={open}
      >
        <span>{initials}</span>
        <span className="account-summary">
          <strong>{user.full_name}</strong>
          <small>{roleName}</small>
        </span>
      </button>
      {open && (
        <div className="account-popover">
          <div className="account-identity">
            <span>{initials}</span>
            <div>
              <strong>{user.full_name}</strong>
              <small>{roleName}</small>
            </div>
          </div>
          <dl>
            <div>
              <dt>Vai trò</dt>
              <dd>{roleName}</dd>
            </div>
            <div>
              <dt>Đơn vị</dt>
              <dd>{department}</dd>
            </div>
          </dl>
          <button
            className="account-logout"
            onClick={() => {
              localStorage.clear();
              location.reload();
            }}
          >
            <LogOut />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
function Login({ done }) {
  const [e, setE] = useState(() => {
    let m = sessionStorage.getItem("session_message") || "";
    sessionStorage.removeItem("session_message");
    return m;
  });
  async function go(x) {
    x.preventDefault();
    let b = Object.fromEntries(new FormData(x.target));
    let r = await fetch(API + "/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(b),
      }),
      j = await r.json();
    if (r.ok) {
      scheduleSessionExpiry(j.access_token);
      history.replaceState({}, "", "/");
      done(j.access_token, j.user);
    } else setE(j.detail);
  }
  return (
    <div className="login">
      <form onSubmit={go}>
        <img className="seal" src={logo} alt="Logo Đại học Hùng Vương" />
        <h2>HỆ THỐNG QUẢN LÝ VĂN BẢN</h2>
        <p>Trường Đại học Hùng Vương TP. Hồ Chí Minh</p>
        <label>
          Tên đăng nhập
          <input name="username" defaultValue="admin" />
        </label>
        <label>
          Mật khẩu
          <input name="password" type="password" defaultValue="123456" />
        </label>
        {e && <i>{e}</i>}
        <button className="primary">ĐĂNG NHẬP</button>
        <small>Demo: admin / 123456</small>
      </form>
    </div>
  );
}
function Dashboard({ d, call }) {
  const total = d.total || 0,
    incoming = d.incoming || 0,
    outgoing = d.outgoing || 0,
    pending = d.pending || 0,
    archived = d.archived || 0,
    percent = (value) => (total ? Math.round((value / total) * 100) : 0),
    today = new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(new Date()),
    metrics = [
      ["Tổng văn bản", total, "Toàn bộ hồ sơ trên hệ thống", FileText, "blue"],
      ["Công văn đến", incoming, `${percent(incoming)}% tổng số văn bản`, Inbox, "cyan"],
      ["Công văn đi", outgoing, `${percent(outgoing)}% tổng số văn bản`, Send, "violet"],
      ["Đang chờ xử lý", pending, `${percent(pending)}% cần theo dõi`, Clock, "amber"],
      ["Đã lưu trữ", archived, `${percent(archived)}% đã hoàn tất lưu trữ`, Archive, "green"],
    ];
  return (
    <div className="dashboard-report">
      <section className="dashboard-report-head">
        <div>
          <small>BÁO CÁO TỔNG QUAN</small>
          <h2>Tình hình quản lý văn bản</h2>
          <p>Số liệu toàn hệ thống tính đến ngày {today}</p>
        </div>
        <div className="report-period"><span>Kỳ báo cáo</span><b>Lũy kế</b></div>
      </section>
      <section className="dashboard-metrics">
        {metrics.map(([name, value, note, Icon, tone]) => (
          <article key={name} className={tone}>
            <div className="metric-icon"><Icon /></div>
            <div><span>{name}</span><b>{value}</b><small>{note}</small></div>
          </article>
        ))}
      </section>
      <section className="dashboard-summary-grid">
        <article className="panel dashboard-composition">
          <div className="dashboard-section-title"><div><h3>Cơ cấu văn bản</h3><p>Phân loại theo chiều văn bản</p></div></div>
          <div className="composition-body">
            <div className="donut" style={{ "--incoming": `${percent(incoming) * 3.6}deg`, "--outgoing": `${percent(incoming + outgoing) * 3.6}deg` }}><span><b>{total}</b><small>văn bản</small></span></div>
            <div className="composition-legend">
              <div><i className="incoming"/><span>Công văn đến<small>{percent(incoming)}%</small></span><b>{incoming}</b></div>
              <div><i className="outgoing"/><span>Công văn đi<small>{percent(outgoing)}%</small></span><b>{outgoing}</b></div>
              <div><i className="other"/><span>Văn bản nội bộ/khác<small>{percent(Math.max(0, total-incoming-outgoing))}%</small></span><b>{Math.max(0, total-incoming-outgoing)}</b></div>
            </div>
          </div>
        </article>
        <article className="panel dashboard-progress">
          <div className="dashboard-section-title"><div><h3>Tình trạng hồ sơ</h3><p>Mức độ lưu trữ và công việc cần theo dõi</p></div></div>
          <div className="progress-row"><span><b>Đã lưu trữ</b><em>{archived}/{total}</em></span><div><i style={{width:`${percent(archived)}%`}}/></div><small>{percent(archived)}%</small></div>
          <div className="progress-row pending"><span><b>Đang chờ xử lý</b><em>{pending}/{total}</em></span><div><i style={{width:`${percent(pending)}%`}}/></div><small>{percent(pending)}%</small></div>
          <div className="dashboard-note"><ShieldCheck/><p><b>Dữ liệu có kiểm soát</b><span>Mọi thao tác cấp số, phê duyệt, ký, đóng dấu và lưu trữ đều được ghi nhật ký.</span></p></div>
        </article>
      </section>
      <MeetingReport call={call} />
      <section className="panel dashboard-recent">
        <div className="dashboard-section-title"><div><h3>Văn bản cập nhật gần đây</h3><p>{(d.recent || []).length} hồ sơ có thay đổi mới nhất</p></div><span>CẬP NHẬT GẦN NHẤT</span></div>
        <Table rows={d.recent || []} />
      </section>
    </div>
  );
}
function MeetingReport({ call }) {
  const now=new Date(),today=now.toLocaleDateString("en-CA"),[mode,setMode]=useState("month"),[month,setMonth]=useState(today.slice(0,7)),[quarter,setQuarter]=useState(String(Math.floor(now.getMonth()/3)+1)),[year,setYear]=useState(String(now.getFullYear())),[start,setStart]=useState(`${today.slice(0,7)}-01`),[end,setEnd]=useState(today),[report,setReport]=useState(null),[error,setError]=useState(""),[loading,setLoading]=useState(false);
  function range(){if(mode==="range")return {start,end};const y=Number(mode==="month"?month.slice(0,4):year);if(mode==="year")return {start:`${y}-01-01`,end:`${y}-12-31`};if(mode==="quarter"){const first=(Number(quarter)-1)*3+1,last=first+2;return {start:`${y}-${String(first).padStart(2,"0")}-01`,end:new Date(y,last,0).toLocaleDateString("en-CA")}}const m=Number(month.slice(5,7));return {start:`${month}-01`,end:new Date(y,m,0).toLocaleDateString("en-CA")}}
  const bounds=range();
  useEffect(()=>{if(!bounds.start||!bounds.end)return;let active=true;setLoading(true);setError("");call(`/dashboard/meeting-report?start=${bounds.start}&end=${bounds.end}`).then(data=>active&&setReport(data)).catch(e=>active&&setError(e.message)).finally(()=>active&&setLoading(false));return()=>{active=false}},[mode,month,quarter,year,start,end]);
  async function download(type){setError("");try{const response=await fetch(`${API}/dashboard/meeting-report/export/${type}?start=${bounds.start}&end=${bounds.end}`,{headers:{Authorization:`Bearer ${localStorage.token}`}});if(!response.ok)throw Error((await response.json()).detail||"Không thể xuất báo cáo");const url=URL.createObjectURL(await response.blob()),a=document.createElement("a");a.href=url;a.download=`bao-cao-giao-ban-${bounds.start}-${bounds.end}.${type}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){setError(e.message)}}
  return <section className="panel meeting-report"><div className="dashboard-section-title"><div><h3>Báo cáo giao ban</h3><p>Thống kê văn bản theo khoảng ngày, tháng, quý hoặc năm</p></div><div className="meeting-export"><button onClick={()=>download("pdf")} disabled={loading||!report}><Download/>Xuất PDF</button><button className="primary" onClick={()=>download("xlsx")} disabled={loading||!report}><Download/>Xuất Excel</button></div></div>
    <div className="meeting-filters"><label>Kỳ báo cáo<select value={mode} onChange={e=>setMode(e.target.value)}><option value="month">Theo tháng</option><option value="quarter">Theo quý</option><option value="year">Theo năm</option><option value="range">Từ ngày đến ngày</option></select></label>{mode==="month"&&<label>Tháng<input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label>}{mode==="quarter"&&<><label>Quý<select value={quarter} onChange={e=>setQuarter(e.target.value)}>{[1,2,3,4].map(x=><option key={x} value={x}>Quý {x}</option>)}</select></label><label>Năm<input type="number" min="2000" max="2100" value={year} onChange={e=>setYear(e.target.value)}/></label></>}{mode==="year"&&<label>Năm<input type="number" min="2000" max="2100" value={year} onChange={e=>setYear(e.target.value)}/></label>}{mode==="range"&&<><label>Từ ngày<input type="date" value={start} onChange={e=>setStart(e.target.value)}/></label><label>Đến ngày<input type="date" value={end} onChange={e=>setEnd(e.target.value)}/></label></>}</div>
    {error&&<p className="form-error">{error}</p>}{loading?<p>Đang tổng hợp số liệu...</p>:report&&<><div className="meeting-totals"><article><span>Tổng văn bản</span><b>{report.total}</b></article><article><span>Văn bản đến</span><b>{report.incoming}</b></article><article><span>Văn bản đi</span><b>{report.outgoing}</b></article><article><span>Hồ sơ tải trực tiếp</span><b>{report.direct_archive}</b></article></div><div className="meeting-types"><h4>Cơ cấu theo loại</h4>{report.by_type.length?report.by_type.map(item=><div key={item.name}><span>{item.name}</span><b>{item.count}</b></div>):<p>Không có văn bản trong kỳ đã chọn.</p>}</div></>}
  </section>;
}
const CONFIDENCE_LABELS = {
  high: "Độ tin cậy: cao",
  medium: "Độ tin cậy: trung bình",
  low: "Độ tin cậy: thấp",
};
function MarkdownInline({ text }) {
  let parts = String(text || "").split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**"))
          return (
          <strong key={i}>{part.slice(2, -2)}</strong>
          );
        if (part.startsWith("*") && part.endsWith("*"))
          return <em key={i}>{part.slice(1, -1)}</em>;
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
    </>
  );
}
function MarkdownText({ children }) {
  let blocks = [],
    list = null;
  function flush() {
    if (list) {
      blocks.push(
        <ul key={`list-${blocks.length}`}>
          {list.map((line, i) => (
            <li key={i}>
              <MarkdownInline text={line} />
            </li>
          ))}
        </ul>,
      );
      list = null;
    }
  }
  String(children || "")
    .split("\n")
    .forEach((raw, i) => {
      let line = raw.trim();
      if (!line) {
        flush();
        return;
      }
      if (/^_{3,}$|^-{3,}$|^\*{3,}$/.test(line)) {
        flush();
        blocks.push(<hr key={i} />);
        return;
      }
      let bullet = line.match(/^[-•]\s*(.+)/);
      if (bullet) {
        (list ??= []).push(bullet[1]);
        return;
      }
      flush();
      let heading = line.match(/^(#{1,3})\s+(.+)/),
        numbered = line.match(/^\d+[.)]\s+(.+)/);
      if (heading) {
        let Tag = `h${Math.min(4, heading[1].length + 2)}`;
        blocks.push(
          <Tag key={i}>
            <MarkdownInline text={heading[2]} />
          </Tag>,
        );
      } else if (numbered)
        blocks.push(
          <p className="md-numbered" key={i}>
            <MarkdownInline text={line} />
          </p>,
        );
      else
        blocks.push(
          <p key={i}>
            <MarkdownInline text={line} />
          </p>,
        );
    });
  flush();
  return <div className="markdown-text">{blocks}</div>;
}
function DocumentLookup(props) {
  const canAI = props.permissions.includes("AI_CHAT"),
    [mode, setMode] = useState(
      location.pathname === "/tro-ly-ai" && canAI ? "ai" : "search",
    );
  useEffect(() => {
    if (location.pathname === "/tro-ly-ai")
      history.replaceState({}, "", TAB_PATHS["Tra cứu văn bản"]);
  }, []);
  return (
    <div className="document-lookup">
      <div className="lookup-modes" role="tablist" aria-label="Chế độ tra cứu">
        <button
          className={mode === "search" ? "on" : ""}
          onClick={() => setMode("search")}
          role="tab"
          aria-selected={mode === "search"}
        >
          <Search />
          Tìm chính xác
        </button>
        {canAI && (
          <button
            className={mode === "ai" ? "on" : ""}
            onClick={() => setMode("ai")}
            role="tab"
            aria-selected={mode === "ai"}
          >
            <Bot />
            Tìm bằng AI
          </button>
        )}
      </div>
      {mode === "ai" && canAI ? (
        <AIFileSearch call={props.call} />
      ) : (
        <Docs {...props} archive={false} original />
      )}
    </div>
  );
}
function AIFileSearch({ call }) {
  const [query, setQuery] = useState(""),
    [results, setResults] = useState([]),
    [searched, setSearched] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    if (!query.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      let res = await call("/ai/search-documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim() }),
      });
      setResults(res.results || []);
      setSearched(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function openFile(src) {
    setError("");
    let target = window.open("", "_blank");
    try {
      let r = await fetch(`${API}/ai/documents/${src.document_id}/file`, {
        headers: { Authorization: `Bearer ${localStorage.token}` },
      });
      if (!r.ok)
        throw Error(
          (await r.json().catch(() => ({}))).detail || "Không thể mở file",
        );
      let url = URL.createObjectURL(await r.blob());
      if (target) target.location.href = url;
      else window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      target?.close();
      setError(err.message);
    }
  }
  return (
    <section className="panel ai-file-search">
      <div className="ai-guidance">
        <Search />
        <span>
          <b>Tìm đúng văn bản bằng AI</b>
          <small>
            Mô tả văn bản cần tìm; Qwen3-8B sẽ đối chiếu tên, loại và nội dung
            để trả về file phù hợp.
          </small>
        </span>
      </div>
      <form onSubmit={submit} className="ai-file-query">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ví dụ: Tìm văn bản quy định các danh hiệu thi đua ngành Giáo dục"
        />
        <button className="primary" disabled={busy || !query.trim()}>
          {busy ? "Đang đối chiếu..." : "Tìm văn bản"}
        </button>
      </form>
      {error && <div className="form-error">{error}</div>}
      <div className="ai-file-results">
        {results.map((src, i) => (
          <article key={`${src.document_id}-${i}`}>
            <FileText />
            <div>
              <b>{src.file_name}</b>
              <small>
                {src.category} · mức phù hợp {src.score}
              </small>
              <p>{src.reason || "Phù hợp với nội dung cần tìm"}</p>
              {src.excerpt && (
                <details>
                  <summary>Xem đoạn nội dung khớp</summary>
                  <p>{src.excerpt}</p>
                </details>
              )}
            </div>
            <button onClick={() => openFile(src)}>Mở file</button>
          </article>
        ))}
        {searched && !results.length && (
          <div className="empty">
            Không tìm thấy văn bản đủ phù hợp. Hãy mô tả rõ chủ đề, số ký hiệu
            hoặc đơn vị ban hành.
          </div>
        )}
      </div>
    </section>
  );
}
function DocumentAnalysis({ call }) {
  const [documents, setDocuments] = useState([]),
    [selected, setSelected] = useState([]),
    [filter, setFilter] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    call("/ai/documents")
      .then(setDocuments)
      .catch((e) => setError(e.message));
  }, []);
  function toggle(id) {
    setSelected((value) =>
      value.includes(id)
        ? value.filter((x) => x !== id)
        : value.length < 5
          ? [...value, id]
          : value,
    );
  }
  let shown = documents.filter((d) =>
    d.file_name.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <div className="analysis-layout">
      <section className="panel analysis-picker">
        <h3>Chọn văn bản để phân tích</h3>
        <p>
          Chọn tối đa 5 văn bản. AI sẽ chỉ sử dụng nội dung trong phạm vi này.
        </p>
        <div className="analysis-filter">
          <Search />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Tìm tên văn bản..."
          />
          <b>{selected.length}/5 đã chọn</b>
        </div>
        <div className="analysis-documents">
          {shown.map((doc) => (
            <label
              key={doc.id}
              className={selected.includes(doc.id) ? "selected" : ""}
            >
              <input
                type="checkbox"
                checked={selected.includes(doc.id)}
                disabled={!selected.includes(doc.id) && selected.length >= 5}
                onChange={() => toggle(doc.id)}
              />
              <span>
                <b>{doc.file_name}</b>
                <small>
                  {doc.category}
                  {doc.chunk_count ? ` · ${doc.chunk_count} đoạn nội dung` : ""}
                </small>
              </span>
            </label>
          ))}
        </div>
        {error && <div className="form-error">{error}</div>}
      </section>
      <div>
        {selected.length ? (
          <AIAssistant
            key={selected.join("-")}
            call={call}
            endpoint="/ai/analyze"
            extraPayload={{ document_ids: selected }}
            analysis
          />
        ) : (
          <section className="panel analysis-empty">
            <Files />
            <h3>Chọn ít nhất một văn bản</h3>
            <p>
              Sau đó bạn có thể hỏi yêu cầu, thời hạn, thành phần hồ sơ, quy
              trình hoặc so sánh điểm khác nhau.
            </p>
          </section>
        )}
      </div>
    </div>
  );
}
function AIReports({ call }) {
  const defaultOutline = [
    "Phạm vi và tài liệu sử dụng",
    "Tổng hợp các nội dung chính",
    "Các yêu cầu, trách nhiệm và thời hạn",
    "Điểm khác biệt hoặc nội dung cần làm rõ",
    "Đề xuất tham khảo (nếu yêu cầu)",
    "Danh mục văn bản nguồn",
  ].join("\n");
  const [requirement, setRequirement] = useState(""),
    [audience, setAudience] = useState("Ban Giám hiệu"),
    [detailLevel, setDetailLevel] = useState("FULL"),
    [outline, setOutline] = useState(defaultOutline),
    [candidates, setCandidates] = useState([]),
    [selected, setSelected] = useState([]),
    [searched, setSearched] = useState(false),
    [draft, setDraft] = useState(""),
    [sources, setSources] = useState([]),
    [warnings, setWarnings] = useState([]),
    [editingDraft, setEditingDraft] = useState(false),
    [instruction, setInstruction] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function findSources() {
    if (!requirement.trim()) return;
    setBusy(true);
    setError("");
    try {
      const res = await call("/ai/search-documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: requirement.trim() }),
      });
      const rows = res.results || [];
      setCandidates(rows);
      setSelected(rows.slice(0, 5).map((row) => row.document_id));
      setSearched(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  function toggle(id) {
    setSelected((items) =>
      items.includes(id)
        ? items.filter((item) => item !== id)
        : items.length < 15
          ? [...items, id]
          : items,
    );
  }
  async function openFile(id) {
    const target = window.open("", "_blank");
    try {
      const response = await fetch(`${API}/ai/documents/${id}/file`, {
        headers: { Authorization: `Bearer ${localStorage.token}` },
      });
      if (!response.ok)
        throw Error((await response.json().catch(() => ({}))).detail || "Không thể mở file");
      const url = URL.createObjectURL(await response.blob());
      if (target) target.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      target?.close();
      setError(err.message);
    }
  }
  async function generate(e, revise = false) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      let payload = {
          requirement: requirement.trim(),
          document_ids: selected,
          audience,
          detail_level: detailLevel,
          outline: outline.split("\n").map((line) => line.trim()).filter(Boolean),
          instruction: revise ? instruction : "",
          history: revise && draft ? [{ role: "assistant", content: draft }] : [],
        },
        res = await call("/ai/reports/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      setDraft(res.draft);
      setEditingDraft(false);
      setSources(res.sources || []);
      setWarnings(res.warnings || []);
      setInstruction("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function exportFile(type) {
    let r = await fetch(`${API}/ai/reports/export/${type}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${localStorage.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title: "Báo cáo tổng hợp công văn",
        content: draft,
      }),
    });
    if (!r.ok) {
      setError((await r.json()).detail);
      return;
    }
    let url = URL.createObjectURL(await r.blob()),
      a = document.createElement("a");
    a.href = url;
    a.download = `bao-cao-dhv.${type}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <div className="report-composer">
      <section className="panel report-step">
        <div className="step-title"><b>1</b><span><h3>Yêu cầu báo cáo</h3><small>Mô tả mục đích và nội dung cần tổng hợp</small></span></div>
        <textarea className="report-requirement" value={requirement} onChange={(e) => setRequirement(e.target.value)} placeholder="Ví dụ: Tổng hợp các văn bản về tuyển sinh năm 2026 để trình BGH. Làm rõ yêu cầu đối với trường, các mốc thời gian, đơn vị chịu trách nhiệm và nội dung cần xin ý kiến." />
        <div className="report-options">
          <label>Người đọc<select value={audience} onChange={(e) => setAudience(e.target.value)}><option>Ban Giám hiệu</option><option>Phòng ban chuyên môn</option><option>Toàn trường</option></select></label>
          <label>Mức chi tiết<select value={detailLevel} onChange={(e) => setDetailLevel(e.target.value)}><option value="SHORT">Ngắn gọn</option><option value="FULL">Đầy đủ</option></select></label>
          <button className="primary" onClick={findSources} disabled={busy || requirement.trim().length < 5}>{busy ? "Đang tìm..." : "Tìm văn bản nguồn"}</button>
        </div>
      </section>
      <section className="panel report-step">
        <div className="step-title"><b>2</b><span><h3>Văn bản nguồn</h3><small>Xem và xác nhận tài liệu trước khi AI tổng hợp</small></span></div>
        <div className="report-source-list">
          {candidates.map((src) => <article key={src.document_id} className={selected.includes(src.document_id) ? "selected" : ""}>
            <input type="checkbox" checked={selected.includes(src.document_id)} onChange={() => toggle(src.document_id)} />
            <span><b>{src.file_name}</b><small>{src.category} · mức phù hợp {src.score}</small><p>{src.reason}</p></span>
            <button onClick={() => openFile(src.document_id)}>Mở file</button>
          </article>)}
          {!searched && <div className="report-hint">Nhập yêu cầu ở bước 1 để AI tìm và đề xuất các văn bản liên quan.</div>}
          {searched && !candidates.length && <div className="report-hint">Không tìm thấy nguồn phù hợp. Hãy mô tả rõ hơn chủ đề, số ký hiệu hoặc đơn vị ban hành.</div>}
        </div>
        {!!candidates.length && <div className="source-confirm">Đã chọn <b>{selected.length}</b> văn bản. AI chỉ được sử dụng nội dung trong các tài liệu này.</div>}
      </section>
      <section className="panel report-step">
        <div className="step-title"><b>3</b><span><h3>Đề cương báo cáo</h3><small>Mỗi dòng là một mục; có thể thêm, bớt hoặc đổi thứ tự</small></span></div>
        <textarea className="report-outline" value={outline} onChange={(e) => setOutline(e.target.value)} />
        <button className="primary generate-report" onClick={(e) => generate(e)} disabled={busy || !selected.length || !requirement.trim()}>{busy ? "Qwen3-8B đang đọc và tổng hợp..." : "Tạo bản nháp báo cáo"}</button>
      </section>
      <section className="panel report-editor">
        {draft ? (
          <>
            <div className="report-toolbar">
              <b>Bản nháp báo cáo</b>
              <div>
                <button onClick={() => setEditingDraft((value) => !value)}>
                  {editingDraft ? "Xem bản trình bày" : "Chỉnh sửa nội dung"}
                </button>
                <button onClick={() => exportFile("docx")}>
                  <Download />
                  Word
                </button>
                <button onClick={() => exportFile("pdf")}>
                  <Download />
                  PDF
                </button>
              </div>
            </div>
            {editingDraft ? (
              <textarea
                className="report-draft"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
              />
            ) : (
              <div className="report-preview">
                <MarkdownText>{draft}</MarkdownText>
              </div>
            )}
            <form className="report-followup" onSubmit={(e) => generate(e, true)}>
              <input
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Yêu cầu chỉnh tiếp: rút gọn còn một trang, chỉ lấy Phòng Đào tạo..."
              />
              <button disabled={busy || !instruction.trim()}>
                Chỉnh bằng AI
              </button>
            </form>
            <details className="report-sources">
              <summary>Danh mục văn bản nguồn ({sources.length})</summary>
              {sources.map((s) => (
                <div key={s.id}>
                  <b>[VB{s.source_number}]</b> {s.file_name} — {s.readable ? `${s.chunk_count} đoạn nội dung` : "chưa đọc được"}
                </div>
              ))}
            </details>
            {warnings.map((warning) => <div className="form-warning" key={warning}>{warning}</div>)}
          </>
        ) : (
          <div className="analysis-empty">
            <BarChart3 />
            <h3>Chưa có bản nháp</h3>
            <p>
              Hoàn tất yêu cầu, xác nhận văn bản nguồn và đề cương để tạo một
              bản thảo hoàn chỉnh có dẫn nguồn.
            </p>
          </div>
        )}
        {error && <div className="form-error">{error}</div>}
      </section>
    </div>
  );
}
function AIAssistant({
  call,
  endpoint = "/ai/chat",
  extraPayload = {},
  analysis = false,
}) {
  const [messages, setMessages] = useState([]),
    [input, setInput] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState(null),
    bottom = useRef(null);
  useEffect(() => {
    call("/ai/status")
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);
  async function submit(e) {
    e.preventDefault();
    let text = input.trim();
    if (!text || busy) return;
    let history = messages.map((m) => ({ role: m.role, content: m.content })),
      next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError("");
    try {
      let res = await call(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history, ...extraPayload }),
      });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          confidence: res.confidence,
          sources: res.sources || [],
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  async function openSource(src) {
    if (!src.document_id) return;
    setError("");
    let target = window.open("", "_blank");
    try {
      let r = await fetch(`${API}/ai/documents/${src.document_id}/file`, {
        headers: { Authorization: `Bearer ${localStorage.token}` },
      });
      if (!r.ok)
        throw Error(
          (await r.json().catch(() => ({}))).detail || "Không thể mở file",
        );
      let url = URL.createObjectURL(await r.blob());
      if (target) target.location.href = url;
      else window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      target?.close();
      setError(err.message);
    }
  }
  return (
    <section className="panel ai-assistant">
      {status && !status.ready && (
        <div className="form-error">
          Chưa có mô hình Qwen tại {status.path}. Hãy chạy
          scripts/download_qwen_chat.py.
        </div>
      )}
      <div className="ai-guidance">
        <ShieldCheck />
        <span>
          <b>Trả lời có kiểm chứng</b>
          <small>
            {analysis
              ? "Chỉ phân tích các văn bản đã chọn; mỗi kết luận kèm nguồn và số trang khi xác định được."
              : "AI chỉ dựa trên văn bản đã lập chỉ mục, kèm độ tin cậy và nguồn đối chiếu."}
          </small>
        </span>
      </div>
      <div className="ai-messages">
        {!messages.length && (
          <div className="empty">
            {analysis
              ? "Hỏi về yêu cầu, đối tượng thực hiện, thời hạn, quy trình hoặc điểm khác nhau giữa các văn bản."
              : "Đặt câu hỏi về nội dung, thời gian hoặc quan hệ giữa các văn bản đã lưu trữ."}
          </div>
        )}
        {messages.map((m, i) => (
          <div className={`ai-message ${m.role}`} key={i}>
            <b>{m.role === "user" ? "Bạn" : "Trợ lý AI"}</b>
            {m.role === "assistant" ? (
              <MarkdownText>{m.content}</MarkdownText>
            ) : (
              <p>{m.content}</p>
            )}
            {m.role === "assistant" && (
              <>
                {m.confidence && (
                  <small className={`ai-confidence ${m.confidence}`}>
                    {CONFIDENCE_LABELS[m.confidence]}
                  </small>
                )}
                {m.sources?.length > 0 && (
                  <details className="ai-sources" open={m.confidence === "low"}>
                    <summary>Văn bản nguồn ({m.sources.length})</summary>
                    {m.sources.map((src, j) => (
                      <div className="ai-source" key={j}>
                        <div className="ai-source-title">
                          <b>
                            [{j + 1}] {src.file_name}
                          </b>
                          {src.document_id && (
                            <button onClick={() => openSource(src)}>
                              Mở file
                            </button>
                          )}
                        </div>
                        <small>
                          {src.category}
                          {src.page ? ` · trang ${src.page}` : ""} · điểm phù
                          hợp {src.score}
                        </small>
                        <p>{src.excerpt}</p>
                      </div>
                    ))}
                  </details>
                )}
              </>
            )}
          </div>
        ))}
        {busy && (
          <div className="ai-message assistant busy">
            <b>Trợ lý AI</b>
            <p>Đang phân tích và đối chiếu nguồn...</p>
          </div>
        )}
        <div ref={bottom} />
      </div>
      {error && <div className="form-error">{error}</div>}
      <form className="ai-input" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            analysis
              ? "Ví dụ: Hai văn bản này khác nhau về thời hạn nào?"
              : "Ví dụ: Văn bản nào quy định thời hạn nộp kế hoạch năm học?"
          }
          disabled={busy}
        />
        <button className="primary" disabled={busy || !input.trim()}>
          {busy ? "Đang xử lý..." : analysis ? "Phân tích" : "Tra cứu bằng AI"}
        </button>
      </form>
    </section>
  );
}
function Docs({
  rows,
  q,
  setQ,
  load,
  call,
  token,
  deps,
  emailConfig,
  permissions,
  archive,
  original,
}) {
  const [action, setAction] = useState(null),
    can = (code) => permissions.includes(code),
    phrase = normalizeExactSearch(q),
    visibleRows = phrase ? rows.filter(d => normalizeExactSearch([d.symbol,d.title,d.summary,d.issuing_agency,d.file_name,d.ocr_text].join(" ")).includes(phrase)) : rows;
  async function done() {
    load();
    setAction(null);
  }
  async function download(d) {
    let r = await fetch(
      `${API}/documents/${d.id}/file${original ? "?original=true" : ""}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!r.ok) return;
    let url = URL.createObjectURL(await r.blob()),
      a = document.createElement("a");
    a.href = url;
    a.download = d.file_name || "van-ban.pdf";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      {archive ? (
        <ArchiveWorkspace
          rows={visibleRows}
          call={call}
          permissions={permissions}
          download={download}
          view={(d) => setAction({ document: d, type: "VIEW" })}
          rename={
            can("RENAME")
              ? (d) => setAction({ document: d, type: "RENAME" })
              : null
          }
          remove={
            can("DELETE")
              ? (d) => setAction({ document: d, type: "DELETE" })
              : null
          }
          act={(document, type) => setAction({ document, type })}
        />
      ) : (
        <section className="panel">
          <div className="tools">
            <div>
              <Search />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Tìm số, trích yếu hoặc nội dung OCR..."
              />
            </div>
          </div>
          <Table
            rows={visibleRows}
            act={(document, type) => setAction({ document, type })}
            download={download}
            permissions={permissions}
          />
        </section>
      )}
      {action &&
        (action.type === "VIEW" ? (
          <ViewDocumentDialog
            action={action}
            token={token}
            original={original}
            close={() => setAction(null)}
          />
        ) : action.type === "OUT_NUMBER" ? (
          <NumberPlacementDialog action={action} token={token} close={() => setAction(null)} done={done} />
        ) : action.type === "PERSONAL_SIGN" ? (
          <MultiPagePlacement
            mode="sign"
            action={action}
            call={call}
            token={token}
            close={() => setAction(null)}
            done={done}
          />
        ) : action.type === "SEAL_SIGN" ? (
          <MultiPagePlacement
            mode="seal"
            action={action}
            call={call}
            token={token}
            close={() => setAction(null)}
            done={done}
          />
        ) : action.type === "RENAME" ? (
          <RenameDialog
            action={action}
            call={call}
            close={() => setAction(null)}
            done={done}
          />
        ) : ["ARCHIVE_APPROVE", "ARCHIVE_RETURN", "ARCHIVE_RESUBMIT"].includes(action.type) ? (
          <ArchiveReviewDialog action={action} call={call} close={() => setAction(null)} done={done} />
        ) : action.type === "IN_REVIEW" ? (
          <IncomingReviewDialog action={action} call={call} deps={deps} close={() => setAction(null)} done={done} />
        ) : action.type === "IN_EDIT" ? (
          <EditReceivedDialog
            action={action}
            call={call}
            token={token}
            close={() => setAction(null)}
            done={done}
          />
        ) : action.type === "OUT_EDIT" ? (
          <EditOutgoingDialog
            action={action}
            call={call}
            deps={deps}
            close={() => setAction(null)}
            done={done}
          />
        ) : ["INTERNAL_SUBMIT", "INTERNAL_APPROVE"].includes(action.type) ? (
          <InternalApprovalDialog
            action={action}
            call={call}
            close={() => setAction(null)}
            done={done}
          />
        ) : action.type.startsWith("IN_") &&
          action.type !== "INTERNAL_EMAIL" ? (
          <IncomingWorkflowDialog
            action={action}
            call={call}
            deps={deps}
            close={() => setAction(null)}
            done={done}
          />
        ) : action.type.startsWith("OUT_") ||
          action.type === "BGH_APPROVE" ||
          action.type === "INTERNAL_EMAIL" ? (
          <OutgoingWorkflowDialog
            action={action}
            call={call}
            emailConfig={emailConfig}
            close={() => setAction(null)}
            done={done}
          />
        ) : (
          <ActionDialog
            action={action}
            call={call}
            deps={deps}
            close={() => setAction(null)}
            done={done}
          />
        ))}
    </>
  );
}
function DirectArchiveUpload({ token, direct, close, saved }) {
  const pdfTitle = usePdfTitle();
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  async function submit(e){e.preventDefault();setBusy(true);setError("");try{const r=await fetch(`${API}/archive/uploads`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:new FormData(e.currentTarget)}),j=await r.json();if(!r.ok)throw Error(j.detail||"Không thể gửi hồ sơ");saved();}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <div className="modal action-modal"><form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={e=>{if(pdfTitle.reading){e.preventDefault();e.stopPropagation();}}} onSubmit={submit}><h2>{direct?"Tải file vào lưu trữ":"Gửi hồ sơ vào lưu trữ"}</h2><p>{direct?"Chọn đúng thư mục và năm. Hệ thống kiểm tra số lớn nhất đã có rồi cấp số kế tiếp trong đúng sổ năm đó; file được lưu ngay và OCR.":"Hồ sơ sẽ chờ Văn thư kiểm tra. Khi duyệt, hệ thống tự lấy số tiếp theo và đưa file vào đúng thư mục."}</p><div className="grid">
    <label>Thư mục <span className="req">*</span><select name="folder" required><option value="">-- Chọn thư mục --</option>{ARCHIVE_TYPES.map(x=><option key={x}>{x}</option>)}</select></label>
    <label>Năm lưu trữ <span className="req">*</span><input name="archive_year" type="number" min="1900" max={new Date().getFullYear()+1} defaultValue={new Date().getFullYear()} required /></label>
    <label className="wide">Tên văn bản / trích yếu <small>(tự nhận diện khi chọn file, có thể chỉnh sửa)</small><input name="title" placeholder="Chọn file để nhận diện tên hoặc nhập thủ công" /></label>
    <label className="wide">File PDF, DOC hoặc DOCX <span className="req">*</span><input name="file" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required /></label>
  </div>{pdfTitle.message&&<p role="status">{pdfTitle.message}</p>}{error&&<div className="form-error">{error}</div>}<div className="end"><button type="button" onClick={close} disabled={busy}>Hủy</button><button className="primary" disabled={busy || pdfTitle.reading}>{busy?"Đang tải lên...":direct?"Tải lên và lưu ngay":"Gửi Văn thư duyệt"}</button></div></form></div>;
}
function ArchiveReviewDialog({ action, call, close, done }) {
  const pdfTitle = usePdfTitle();
  const d=action.document,[busy,setBusy]=useState(false),[error,setError]=useState("");
  async function submit(e){e.preventDefault();setBusy(true);setError("");try{if(action.type==="ARCHIVE_RESUBMIT")await call(`/archive/uploads/${d.id}/resubmit`,{method:"POST",body:new FormData(e.currentTarget)});else await call(`/archive/uploads/${d.id}/review`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision:action.type==="ARCHIVE_APPROVE"?"APPROVE":"RETURN",note:new FormData(e.currentTarget).get("note")})});done();}catch(e){setError(e.message)}finally{setBusy(false)}}
  const resubmit=action.type==="ARCHIVE_RESUBMIT";
  return <div className="modal action-modal"><form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={e=>{if(pdfTitle.reading){e.preventDefault();e.stopPropagation();}}} onSubmit={submit}><h2>{resubmit?"Nộp lại hồ sơ":action.type==="ARCHIVE_APPROVE"?"Duyệt hồ sơ lưu trữ":"Trả lại hồ sơ"}</h2><p><b>{d.file_name}</b><br/>{d.title} · Phiên bản {d.revision}</p>{resubmit?<div className="grid"><label className="wide">Tên hồ sơ<input name="title" defaultValue={d.title}/></label><label>Ngày văn bản<input name="issued_date" type="date" defaultValue={d.issued_date||""}/></label><label className="wide">PDF, DOC hoặc DOCX mới <span className="req">*</span><input name="file" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required/></label></div>:<label>{action.type==="ARCHIVE_APPROVE"?"Ý kiến duyệt":"Lý do trả lại"} <span className="req">*</span><textarea name="note" required autoFocus/></label>}{pdfTitle.message&&<p role="status">{pdfTitle.message}</p>}{error&&<div className="form-error">{error}</div>}<div className="end"><button type="button" onClick={close} disabled={busy}>Hủy</button><button className={action.type==="ARCHIVE_RETURN"?"danger":"primary"} disabled={busy || pdfTitle.reading}>{busy?"Đang xử lý...":resubmit?"Gửi lại Văn thư":action.type==="ARCHIVE_APPROVE"?"Duyệt và lưu":"Xác nhận trả lại"}</button></div></form></div>;
}
function DocumentRegisterExport() {
  const currentYear=new Date().getFullYear(),[year,setYear]=useState(currentYear),[busy,setBusy]=useState(false),[error,setError]=useState("");
  async function download(){setBusy(true);setError("");try{const response=await fetch(`${API}/register/export?year=${year}`,{headers:{Authorization:`Bearer ${localStorage.token}`}});if(!response.ok)throw Error((await response.json()).detail||"Không thể xuất sổ số hiệu");const url=URL.createObjectURL(await response.blob()),link=document.createElement("a");link.href=url;link.download=`so-dang-ky-so-van-ban-${year}.xlsx`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <section className="panel document-register-export"><div><span className="register-icon"><FileText/></span><div><h3>Sổ đăng ký số văn bản</h3><p>Xuất Excel theo mẫu của Trường, tách sheet Công văn đến, Công văn đi, Quyết định, Thông báo, Kế hoạch và Báo cáo.</p></div></div><div className="register-export-actions"><label>Năm sổ<input type="number" min="1900" max={currentYear+1} value={year} onChange={e=>setYear(Number(e.target.value))}/></label><button className="primary" onClick={download} disabled={busy||year<1900||year>currentYear+1}><Download/>{busy?"Đang tạo sổ...":"Xuất sổ Excel"}</button></div>{error&&<p className="form-error">{error}</p>}</section>;
}
function ArchiveWorkspace({ rows, permissions, download, view, rename, remove }) {
  const [sort,setSort]=useState("number-asc");
  const archiveDate=d=>new Date(d.issued_date||(d.archive_year?`${d.archive_year}-01-01`:d.received_date||d.created_at));
  const sorted=rows.filter(d=>d.status==="ARCHIVED").sort((a,b)=>
    sort==="number-asc"?(a.number??Number.MAX_SAFE_INTEGER)-(b.number??Number.MAX_SAFE_INTEGER):
    sort==="number-desc"?(b.number??-1)-(a.number??-1):
    sort==="date-asc"?archiveDate(a)-archiveDate(b):archiveDate(b)-archiveDate(a));
  return <>
    {permissions.includes("ARCHIVE")&&<DocumentRegisterExport/>}
    <div className="panel archive-heading">
      <label>Sắp xếp kho
        <select value={sort} onChange={e=>setSort(e.target.value)}>
          <option value="number-asc">Số văn bản tăng dần</option>
          <option value="number-desc">Số văn bản giảm dần</option>
          <option value="date-desc">Ngày mới nhất</option>
          <option value="date-asc">Ngày cũ nhất</option>
        </select>
      </label>
    </div>
    <ArchiveTree rows={sorted} download={download} view={view} rename={rename} remove={remove}/>
  </>;
}
function ReportTrackingPage({ call }) {
  const [tracking,setTracking]=useState([]),[error,setError]=useState(""),[loading,setLoading]=useState(true);
  useEffect(()=>{let active=true;call("/reports/tracking").then(rows=>active&&setTracking(rows)).catch(e=>active&&setError(e.message)).finally(()=>active&&setLoading(false));return()=>{active=false}},[]);
  return <section className="panel report-tracking"><h3>Theo dõi báo cáo đơn vị</h3><p>Cảnh báo xuất hiện trước hạn một ngày; email tự gửi theo mẫu đã cấu hình đến các đơn vị chưa nộp.</p>{error&&<p className="form-error">{error}</p>}{loading?<p className="archive-muted">Đang tải tiến độ...</p>:!tracking.length?<p className="archive-muted">Chưa có đợt báo cáo được giao.</p>:tracking.map(item=><article className={item.warning?"warning":""} key={`${item.document_id}-${item.revision}`}><header><div><b>{item.symbol||"Chưa cấp số"} · {item.title}</b><small>Hạn: {item.deadline?item.deadline.split("-").reverse().join("/"):"Không đặt"}</small></div><strong>Đã nhận {item.received_count}/{item.total}</strong></header><div className="report-unit-columns"><p><b>Đã gửi</b>{item.received.length?item.received.map(x=><span key={x.department_id}>✓ {x.name}</span>):<span>Chưa có đơn vị gửi</span>}</p><p><b>Chưa gửi</b>{item.missing.length?item.missing.map(x=><span key={x.department_id}>⚠ {x.name}</span>):<span>Đã nhận đủ</span>}</p></div></article>)}</section>;
}
function ArchiveFiles({ files, download, view, rename, remove }) {
  return (
    <div className="tree-files">
      {files.length ? (
        files.map((d) => (
          <div className="tree-file-row" key={d.id}>
            <button onClick={() => view(d)}>
              <FileText />
              <span>
                <b>{d.file_name || d.title}</b>
                <small>{d.symbol || d.title} · tải lên {new Date(d.created_at).toLocaleDateString("vi-VN")}</small>
              </span>
              <em>Xem hồ sơ</em>
            </button>
            <button onClick={() => download(d)}>Tải xuống</button>
            {rename && <button onClick={() => rename(d)}>Đổi tên</button>}
            {remove && (
              <button className="danger-link" onClick={() => remove(d)}>
                Xóa
              </button>
            )}
          </div>
        ))
      ) : (
        <small>Chưa có file</small>
      )}
    </div>
  );
}
function ArchiveTree({ rows, download, view, rename, remove }) {
  const types = ARCHIVE_TYPES;
  let years = { [new Date().getFullYear()]: {} };
  rows.forEach((d) => {
    let year = d.archive_year || new Date(
        d.issued_date || d.received_date || d.created_at,
      ).getFullYear(),
      type =
        d.doc_type === "CÔNG VĂN"
          ? d.direction === "IN"
            ? "CÔNG VĂN ĐẾN"
            : "CÔNG VĂN ĐI"
          : d.doc_type;
    if (!years[year]) years[year] = {};
    (years[year][type] ??= []).push(d);
  });
  let ys = Object.keys(years).sort((a, b) => b - a);
  return (
    <section className="panel archive-panel">
      {!ys.length ? (
        <div className="empty">Chưa có văn bản lưu trữ</div>
      ) : (
        ys.map((year) => (
          <details className="tree-year" key={year} open>
            <summary>
              <Archive />
              Năm {year}
              <b>{Object.values(years[year]).flat().length} file</b>
            </summary>
            <div className="tree-types">
              {types.map((type) => {
                let files = years[year][type] || [];
                return (
                  <details
                    className="tree-type"
                    key={type}
                    open={files.length > 0}
                  >
                    <summary>
                      <span>📁</span>
                      {type}
                      <b>{files.length}</b>
                    </summary>
                    <ArchiveFiles
                      files={files}
                      download={download}
                      view={view}
                      rename={rename}
                      remove={remove}
                    />
                  </details>
                );
              })}
            </div>
          </details>
        ))
      )}
    </section>
  );
}
function OfficeOpinionFields() {
  const [note, setNote] = useState("");
  return (
    <div className="office-opinion-layout">
      <div>
        <label>
          Ý kiến xử lý <span className="req">*</span>
          <textarea
            name="note"
            required
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Nhập ý kiến của Chánh Văn phòng"
            autoFocus
          />
        </label>
        <p>
          Hệ thống tự tạo phiếu A4, ký số mô phỏng và ghép làm trang đầu tiên
          của công văn.
        </p>
      </div>
      <div className="a4-opinion-preview">
        <div className="a4-school">
          TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG TP. HỒ CHÍ MINH
        </div>
        <h3>PHIẾU Ý KIẾN XỬ LÝ CÔNG VĂN ĐẾN</h3>
        <div className="a4-note-box">
          <b>Ý KIẾN CỦA CHÁNH VĂN PHÒNG</b>
          <p>{note || "Nội dung ý kiến sẽ hiển thị tại đây..."}</p>
          <div className="a4-sign">
            <strong>ĐÃ KÝ SỐ - GIẢ LẬP</strong>
            <small>CHÁNH VĂN PHÒNG</small>
          </div>
        </div>
        <small>Phiếu này sẽ được ghép trước trang 1 của công văn gốc.</small>
      </div>
    </div>
  );
}
function IncomingWorkflowDialog({ action, call, deps, close, done }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  let t = action.type,
    d = action.document;
  const titles = {
    IN_NUMBER: "Vào số công văn đến",
    IN_OFFICE: "Ý kiến Chánh Văn phòng",
    IN_SEND_BGH: "Gửi Ban Giám hiệu",
    IN_BGH: "BGH duyệt hoặc từ chối",
    IN_FORWARD: "Chuyển đơn vị xử lý",
  };
  const labels = {
    IN_NUMBER: "Xác nhận",
    IN_OFFICE: "Xác nhận & ký số",
    IN_SEND_BGH: "Xác nhận gửi BGH",
    IN_BGH: "Xác nhận quyết định",
    IN_FORWARD: "Xác nhận chuyển đơn vị",
  };
  const busyLabels = {
    IN_NUMBER: "Đang xử lý...",
    IN_OFFICE: "Đang tạo và ký phiếu...",
    IN_SEND_BGH: "Đang gửi BGH...",
    IN_BGH: "Đang xử lý quyết định...",
    IN_FORWARD: "Đang chuyển đơn vị...",
  };
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let raw = new FormData(e.currentTarget),
        path = "",
        body = raw;
      if (t === "IN_NUMBER") {
        path = "incoming-number";
        if (!raw.get("number")) raw.delete("number");
      }
      if (t === "IN_OFFICE") path = "office-opinion";
      if (t === "IN_SEND_BGH") {
        path = "send-bgh";
        body = undefined;
      }
      if (t === "IN_BGH") path = "bgh-decision";
      if (t === "IN_FORWARD") {
        path = "forward";
        let selected = [
          ...e.currentTarget.querySelectorAll('input[name="dep"]:checked'),
        ].map((x) => Number(x.value));
        raw.set("department_ids", JSON.stringify(selected));
        raw.set(
          "emails",
          JSON.stringify(
            (raw.get("email_list") || "")
              .split(/[,;\n]/)
              .map((x) => x.trim())
              .filter(Boolean),
          ),
        );
        raw.delete("email_list");
        raw.delete("dep");
      }
      await call(`/documents/${d.id}/${path}`, { method: "POST", body });
      done();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className={`modal action-modal ${t === "IN_OFFICE" ? "office-opinion-modal" : ""}`}
    >
      <form onSubmit={submit}>
        <h2>{titles[t]}</h2>
        {t === "IN_NUMBER" && (
          <>
            <label>
              Năm sổ văn bản
              <input
                name="year"
                type="number"
                defaultValue={new Date().getFullYear()}
                required
              />
            </label>
            <label>
              Số đến (để trống để lấy số kế tiếp)
              <input name="number" type="number" min="1" />
            </label>
            <p>Sổ số được tách riêng theo năm và loại {d.doc_type}.</p>
          </>
        )}
        {t === "IN_OFFICE" && <OfficeOpinionFields />}
        {t === "IN_SEND_BGH" && (
          <p>
            Phiếu ý kiến đã được ký số. Xác nhận chuyển toàn bộ hồ sơ đến Ban
            Giám hiệu?
          </p>
        )}
        {t === "IN_BGH" && (
          <>
            <label>
              Quyết định
              <select name="decision">
                <option value="APPROVE">Duyệt</option>
                <option value="REJECT">Từ chối</option>
              </select>
            </label>
            <label>
              Ý kiến BGH bắt buộc
              <textarea
                name="note"
                required
                placeholder="Nhập ý kiến duyệt hoặc lý do từ chối"
              />
            </label>
          </>
        )}
        {t === "IN_FORWARD" && (
          <>
            <label>Đơn vị được phân công (bắt buộc)</label>
            <div className="dep-list">
              {schoolUnits(deps).map((x) => (
                <label key={x.id}>
                  <input type="checkbox" name="dep" value={x.id} />
                  {x.name}
                </label>
              ))}
            </div>
            <label>
              Email đơn vị (phân cách bằng dấu phẩy)
              <textarea name="email_list" placeholder="donvi@dhv.edu.vn" />
            </label>
            <label>
              Ghi chú chuyển xử lý
              <textarea name="note" />
            </label>
          </>
        )}
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close} disabled={busy}>
            Hủy
          </button>
          <button className="primary" disabled={busy}>
            {busy ? busyLabels[t] : labels[t]}
          </button>
        </div>
      </form>
    </div>
  );
}
function SignatureConfig({ initial = "" }) {
  const [value, setValue] = useState(initial);
  return (
    <div className="signature-config">
      <label>
        Chữ ký email mặc định <span className="req">*</span>
      </label>
      <RichTextEditor
        name="signature_html"
        value={value}
        onChange={setValue}
        required
        placeholder="Ví dụ: Trân trọng, họ tên, chức vụ, logo..."
        minHeight={130}
        imageMaxWidth={100}
      />
      <small>
        Hỗ trợ ảnh/logo tối đa 1 MB, chữ đậm, nghiêng, cỡ chữ, danh sách và thụt
        lề.
      </small>
    </div>
  );
}
function htmlHasContent(value) {
  let box = document.createElement("div");
  box.innerHTML = value || "";
  return Boolean(box.textContent.trim() || box.querySelector("img"));
}
function RichTextEditor({
  name,
  value,
  onChange,
  placeholder,
  minHeight = 150,
  required = false,
  imageMaxWidth = 480,
}) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== value)
      ref.current.innerHTML = value || "";
  }, [value]);
  function command(cmd, arg = null) {
    ref.current?.focus();
    document.execCommand(cmd, false, arg);
    onChange(ref.current?.innerHTML || "");
  }
  function image(e) {
    let file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 1024 * 1024) {
      alert("Ảnh tối đa 1 MB");
      e.target.value = "";
      return;
    }
    let reader = new FileReader();
    reader.onload = () => {
      let source = reader.result,
        picture = new Image();
      picture.onload = () => {
        command("insertImage", source);
        let inserted = [...(ref.current?.querySelectorAll("img") || [])]
          .reverse()
          .find((x) => x.src === source);
        if (inserted) {
          let width = Math.min(picture.naturalWidth, imageMaxWidth),
            height = Math.round(
              (width * picture.naturalHeight) / picture.naturalWidth,
            );
          inserted.setAttribute("width", width);
          inserted.setAttribute("height", height);
          inserted.style.width = `${width}px`;
          inserted.style.height = "auto";
          inserted.style.maxWidth = "100%";
          onChange(ref.current.innerHTML);
        }
      };
      picture.src = source;
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  }
  return (
    <div
      className={`rich-editor ${imageMaxWidth <= 180 ? "signature-editor" : ""}`}
    >
      <div className="rich-toolbar">
        <select
          aria-label="Cỡ chữ"
          defaultValue="3"
          onChange={(e) => command("fontSize", e.target.value)}
        >
          <option value="2">Nhỏ</option>
          <option value="3">Bình thường</option>
          <option value="4">Lớn</option>
          <option value="5">Rất lớn</option>
        </select>
        <button type="button" onClick={() => command("bold")} title="In đậm">
          <b>B</b>
        </button>
        <button
          type="button"
          onClick={() => command("italic")}
          title="In nghiêng"
        >
          <i>I</i>
        </button>
        <button
          type="button"
          onClick={() => command("underline")}
          title="Gạch chân"
        >
          <u>U</u>
        </button>
        <button
          type="button"
          onClick={() => command("insertUnorderedList")}
          title="Danh sách"
        >
          • List
        </button>
        <button
          type="button"
          onClick={() => command("outdent")}
          title="Giảm thụt lề"
        >
          ⇤
        </button>
        <button
          type="button"
          onClick={() => command("indent")}
          title="Tăng thụt lề"
        >
          ⇥
        </button>
        <label className="rich-image">
          Ảnh/logo (tối đa {imageMaxWidth}px)
          <input
            type="file"
            accept="image/png,image/jpeg,image/gif"
            onChange={image}
          />
        </label>
        <button type="button" onClick={() => command("removeFormat")}>
          Xóa định dạng
        </button>
      </div>
      <div
        ref={ref}
        className="rich-content"
        contentEditable
        data-placeholder={placeholder}
        style={{ minHeight }}
        onInput={(e) => onChange(e.currentTarget.innerHTML)}
        onBlur={(e) => onChange(e.currentTarget.innerHTML)}
      />
      <input type="hidden" name={name} value={value} />
      {required && !htmlHasContent(value) && (
        <small className="rich-required">Trường này là bắt buộc</small>
      )}
    </div>
  );
}
function OutgoingWorkflowDialog({ action, call, emailConfig, close, done }) {
  const [busy, setBusy] = useState(false),
    [draft, setDraft] = useState(null),
    [error, setError] = useState(""),
    [content, setContent] = useState(""),
    [subject, setSubject] = useState(action.document.title),
    [signature, setSignature] = useState(emailConfig?.signature_html || "");
  let t = action.type,
    d = action.document,
    isInternal = t === "INTERNAL_EMAIL",
    mailing = ["OUT_EMAIL", "INTERNAL_EMAIL"].includes(t);
  async function submit(e) {
    e.preventDefault();
    if (mailing && !htmlHasContent(content)) {
      setError("Tiêu đề và nội dung là bắt buộc");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let body = new FormData(e.currentTarget),
        path =
          ["OUT_SUBMIT_APPROVAL", "OUT_SUBMIT_SIGN"].includes(t)
            ? "outgoing-submit"
            : t === "BGH_APPROVE"
              ? "outgoing-bgh-approve"
            : t === "OUT_RETURN"
              ? "outgoing-return"
              : isInternal
                ? "internal-email"
                : "outgoing-email";
      if (t === "OUT_SUBMIT_APPROVAL") body.set("bgh_action", "APPROVE");
      if (t === "OUT_SUBMIT_SIGN") body.set("bgh_action", "SIGN");
      if (mailing) {
        setDraft(await prepareGmail(() => call(`/documents/${d.id}/${path}`, { method: "POST", body })));
      } else {
        await call(`/documents/${d.id}/${path}`, { method: "POST", body });
        done();
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className={`modal action-modal ${mailing ? "email-compose-modal" : ""}`}
    >
      <form onSubmit={submit}>
        <h2>
          {t === "OUT_SUBMIT_APPROVAL"
            ? "Gửi BGH duyệt"
            : t === "OUT_SUBMIT_SIGN"
              ? "Gửi BGH duyệt và ký số"
            : t === "BGH_APPROVE"
              ? "BGH duyệt văn bản"
            : t === "OUT_RETURN"
              ? "Trả lại công văn đi"
              : isInternal
                ? "Phát hành văn bản nội bộ"
                : "Gửi công văn qua email"}
        </h2>
        {t === "OUT_SUBMIT_APPROVAL" && <p>Văn bản đã có chữ ký số của lãnh đạo đơn vị. BGH sẽ duyệt và không cần ký lại.</p>}
        {t === "OUT_SUBMIT_SIGN" && <p>Văn bản chưa có chữ ký số. BGH sẽ duyệt và ký số, sau đó chuyển Văn thư.</p>}
        {t === "BGH_APPROVE" && <>
          <p>Xác nhận duyệt văn bản đã được lãnh đạo đơn vị ký và chuyển về Văn thư.</p>
          <label>Ý kiến duyệt <span className="req">*</span><textarea name="note" required autoFocus placeholder="Nhập ý kiến của BGH" /></label>
        </>}
        {t === "OUT_RETURN" && (
          <label>
            Lý do trả lại <span className="req">*</span>
            <textarea
              name="note"
              required
              autoFocus
              placeholder="Nhập nội dung cần chỉnh sửa"
            />
          </label>
        )}
        {mailing && (
          <>
            <EmailTemplates onApply={template => {
              setSubject(template.subject);
              setContent(template.content.split("\n\n").map(p => "<p>" + p.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>") + "</p>").join(""));
            }} />
            <label>
              Email người nhận <span className="req">*</span>
              <textarea
                name="emails"
                required
                autoFocus
                placeholder="email1@domain.vn, email2@domain.vn"
              />
            </label>
            <label>
              Tiêu đề <span className="req">*</span>
              <input name="subject" required value={subject} onChange={e => setSubject(e.target.value)} />
            </label>
            <label>
              Nội dung <span className="req">*</span>
            </label>
            <RichTextEditor
              name="content_html"
              value={content}
              onChange={setContent}
              required
              placeholder="Nhập nội dung email..."
            />
            <label>
              Chữ ký (không bắt buộc)
            </label>
            <RichTextEditor
              name="signature_html"
              value={signature}
              onChange={setSignature}
              placeholder="Chữ ký được lấy từ cấu hình hệ thống..."
              minHeight={110}
              imageMaxWidth={100}
            />
            <p className="email-hint">
              Gmail sẽ mở để bạn chỉnh sửa và tự gửi. Tải PDF rồi đính kèm trong Gmail.
            </p>
          </>
        )}
        <GmailDraft draft={draft} onConfirm={async () => {
          setBusy(true);
          try { await call(`/documents/${d.id}/gmail-confirm`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({revision:draft.document.revision})}); done(); }
          catch(e) {setError(e.message);} finally {setBusy(false);}
        }} />
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close} disabled={busy}>
            Hủy
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Đang xử lý..." : t === "BGH_APPROVE" ? "Xác nhận duyệt" : t === "OUT_RETURN" ? "Xác nhận trả lại" : t === "OUT_SUBMIT_APPROVAL" ? "Gửi BGH duyệt" : t === "OUT_SUBMIT_SIGN" ? "Gửi BGH ký số" : "Mở Gmail"}
          </button>
        </div>
      </form>
    </div>
  );
}
function usePdfTitle() {
  const [message, setMessage] = useState("");
  const [reading, setReading] = useState(false);
  const request = useRef(null);
  useEffect(() => () => request.current?.abort(), []);
  async function onChangeCapture(e) {
    const input = e.target;
    if (input.name !== "file" || input.type !== "file") return;
    request.current?.abort();
    const file = input.files?.[0];
    setMessage("");
    setReading(false);
    if (!file) return;
    const form = input.form;
    const title = form.elements.namedItem("title");
    if (!title) return;
    const previousTitle = title.value;
    let edited = false;
    const markEdited = () => { edited = true; };
    title.addEventListener("input", markEdited);
    const controller = new AbortController();
    request.current = controller;
    setReading(true);
    setMessage("Đang đọc văn bản và nhận diện tên bằng AI...");
    try {
      const body = new FormData();
      body.set("file", file);
      const result = await requestPdfTitle(`${API}/documents/analyze-title`, {
        method: "POST", body, signal: controller.signal,
        headers: { Authorization: `Bearer ${localStorage.token}` },
      });
      if (controller.signal.aborted || !form.isConnected) return;
      if (!edited && title.value === previousTitle) {
        title.value = result.title;
        title.dispatchEvent(new Event("input", { bubbles: true }));
        title.dispatchEvent(new Event("change", { bubbles: true }));
        setMessage(`Đã điền tên từ nội dung văn bản: ${result.title}. Bạn có thể sửa trước khi lưu.`);
      } else {
        setMessage(`AI nhận diện: ${result.title}. Giữ nguyên trích yếu bạn đang nhập.`);
      }
    } catch (error) {
      if (!controller.signal.aborted) setMessage(`${error instanceof TypeError ? "Không kết nối được máy chủ nhận diện. Vui lòng chọn lại tệp để thử lại" : error.message}. Bạn có thể nhập trích yếu thủ công.`);
    } finally {
      title.removeEventListener("input", markEdited);
      if (request.current === controller) setReading(false);
    }
  }
  return { message, reading, onChangeCapture };
}

function EditOutgoingDialog({ action, call, deps, close, done }) {
  const pdfTitle = usePdfTitle();
  const d = action.document,
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await call(`/documents/${d.id}/edit-outgoing`, {
        method: "POST",
        body: new FormData(e.currentTarget),
      });
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal action-modal">
      <form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={(e) => { if (pdfTitle.reading) { e.preventDefault(); e.stopPropagation(); } }} onSubmit={submit} onChange={() => setDirty(true)}>
        <h2>Sửa công văn đi</h2>
        <p>Tên file PDF được tạo tự động từ số ký hiệu và trích yếu.</p>
        <div className="grid">
          <label>Ngày ban hành <span className="req">*</span><input type="date" name="issued_date" defaultValue={d.issued_date || new Date().toLocaleDateString("en-CA")} required /></label>
          <label>
            Đơn vị tiếp nhận <span className="req">*</span>
            {d.doc_type !== "CÔNG VĂN" ? <select name="issuing_agency" defaultValue={d.issuing_agency} required>{schoolUnits(deps).map(unit => <option key={unit.id}>{unit.name}</option>)}</select> : <input name="issuing_agency" defaultValue={d.issuing_agency || ""} required />}
          </label>
          <label className="wide">
            Thay PDF, DOC hoặc DOCX (không bắt buộc vì đã có file)
            <input name="file" type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" />
          </label>
            <label className="wide">
            Trích yếu <span className="req">*</span>
            <input name="title" defaultValue={d.title} required />
          </label>
          <label className="wide">
            Tóm tắt <small>(không bắt buộc)</small>
            <textarea name="summary" defaultValue={d.summary || ""} />
          </label>

        </div>
        {error && <div className="form-error">{error}</div>}
        {pdfTitle.message && <p role="status">{pdfTitle.message}</p>}
        <div className="end">
          <button type="button" onClick={close}>
            Hủy
          </button>
          <button className="primary" disabled={busy || pdfTitle.reading || !dirty}>
            {busy ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
        </div>
      </form>
    </div>
  );
}
function ReservationReviewDialog({ action, call, deps, close, done }) {
  const [note,setNote]=useState(""),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const d=action.document, user=JSON.parse(localStorage.user || "null");
  if (action.type==="RESERVATION_EDIT") return <ReserveNumber direction={d.direction} deps={deps} user={user} token={localStorage.token} existing={d} close={close} saved={done}/>;
  async function decide(decision) {
    setBusy(true); setError("");
    try {await call(`/documents/${d.id}/reservation-decision`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,revision:d.revision,note})});done();}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <div className="modal action-modal"><form role="dialog" aria-modal="true" aria-labelledby="reservation-review-title" onSubmit={e=>e.preventDefault()}><h2 id="reservation-review-title">{action.type==="RESERVATION_DELETE" ? "Xoá yêu cầu xin số" : "Duyệt yêu cầu xin số trước"}</h2>
    <p>{d.title} · {d.doc_type} · {d.issuing_agency}</p><p>Ngày phát hành: {d.issued_date || "Chưa có"}</p><p style={{whiteSpace:"pre-wrap"}}>{d.summary}</p>
    <label>Ý kiến / lý do từ chối<textarea value={note} onChange={e=>setNote(e.target.value)}/></label>
    {error&&<p role="alert">{error}</p>}
    <div className="end"><button type="button" onClick={close} disabled={busy}>Đóng</button>
    {action.type==="RESERVATION_DELETE" ? <button type="button" onClick={()=>decide("DELETE")} disabled={busy}>Xác nhận xoá</button> : <><button type="button" onClick={()=>decide("REJECT")} disabled={busy||!note.trim()}>Từ chối</button><button type="button" className="primary" onClick={()=>decide("APPROVE")} disabled={busy}>Duyệt và cấp số</button></>}
    </div></form></div>;
}
function ActionDialog({ action, call, deps, close, done }) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (action.type.startsWith("RESERVATION_")) return <ReservationReviewDialog action={action} call={call} deps={deps} close={close} done={done}/>;
  if (action.type === "ATTACH_RESERVED")
    return (
      <AttachReservedDialog
        action={action}
        call={call}
        deps={deps}
        close={close}
        done={done}
      />
    );
  const labels = {
    SUBMIT: "Trình văn bản",
    APPROVE: "Duyệt văn bản",
    SEAL_SIGN: "Đóng dấu văn bản",
    ARCHIVE: "Lưu trữ và OCR văn bản",
    DELETE: "Xóa văn bản",
  };
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await call(`/documents/${action.document.id}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: action.type,
          comment,
          department_ids: [],
        }),
      });
      done();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  let deleting = action.type === "DELETE";
  return (
    <div
      className="modal action-modal"
      onMouseDown={(e) => e.target === e.currentTarget && !busy && close()}
    >
      <form onSubmit={submit}>
        <h2>{labels[action.type] || "Xác nhận thao tác"}</h2>
        <p>
          {action.type === "ARCHIVE"
            ? "Hệ thống sẽ OCR toàn bộ PDF và khóa hồ sơ sau khi lưu trữ."
            : deleting
              ? "Văn bản sẽ bị ẩn khỏi hệ thống. Quản trị viên vẫn có thể khôi phục sau đó."
              : "Bạn có chắc chắn muốn thực hiện thao tác này?"}
        </p>
        <label>
          {deleting ? "Lý do xóa (bắt buộc)" : "Ý kiến xử lý"}
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            required={deleting}
            placeholder={
              deleting
                ? "Nhập lý do xóa văn bản"
                : "Nhập ý kiến (không bắt buộc)"
            }
            autoFocus
          />
        </label>
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close} disabled={busy}>
            Hủy
          </button>
          <button className={deleting ? "danger" : "primary"} disabled={busy}>
            {busy ? "Đang xử lý..." : deleting ? "Xóa văn bản" : "Xác nhận"}
          </button>
        </div>
      </form>
    </div>
  );
}
function SigningStudio({ action, call, token, close, done }) {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [pos, setPos] = useState({ x: 55, y: 68 });
  const [page, setPage] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let controller = new AbortController();
    async function loadPdf() {
      setLoading(true);
      setError("");
      try {
        if (file) {
          objectUrl = URL.createObjectURL(file);
        } else if (action.document.file_name) {
          let r = await fetch(`${API}/documents/${action.document.id}/file`, {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          });
          if (!r.ok)
            throw Error(
              r.status === 404
                ? "Không tìm thấy PDF đã lưu"
                : "Không thể tải PDF đã lưu",
            );
          objectUrl = URL.createObjectURL(await r.blob());
        }
        setUrl(objectUrl);
      } catch (err) {
        if (err.name !== "AbortError") setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadPdf();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [file, action.document.id, action.document.file_name, token]);
  function move(e) {
    if (!dragging) return;
    let r = e.currentTarget.getBoundingClientRect();
    setPos({
      x: Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.max(0, Math.min(100, ((e.clientY - r.top) / r.height) * 100)),
    });
  }
  async function sign() {
    if (!url) {
      setError("Văn bản chưa có tệp PDF để ký");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let f = new FormData();
      if (file) f.set("file", file);
      f.set("page", page);
      f.set("x_percent", Math.round(pos.x));
      f.set("y_percent", Math.round(pos.y));
      await call(`/documents/${action.document.id}/digital-sign`, {
        method: "POST",
        body: f,
      });
      done();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal signing-modal">
      <section className="signing-studio">
        <header>
          <div>
            <h2>Ký số văn bản</h2>
            <p>{action.document.title}</p>
          </div>
          <button onClick={close} disabled={busy}>
            Đóng
          </button>
        </header>
        <div className="signing-toolbar">
          <span>Để thay PDF, DOC hoặc DOCX, sửa văn bản ở bước bản nháp trước khi ký.</span>
          <label>
            Trang ký
            <input
              type="number"
              min="1"
              value={page}
              onChange={(e) =>
                setPage(Math.max(1, Number(e.target.value) || 1))
              }
            />
          </label>
          <span>
            Vị trí: {Math.round(pos.x)}% × {Math.round(pos.y)}%
          </span>
        </div>
        <div
          className="pdf-stage"
          onPointerMove={move}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
        >
          {loading ? (
            <div className="pdf-placeholder">
              <FileText />
              <b>Đang tải PDF đã lưu...</b>
            </div>
          ) : url ? (
            <object
              data={`${url}#page=${page}&toolbar=0`}
              type="application/pdf"
            >
              Không thể hiển thị PDF
            </object>
          ) : (
            <div className="pdf-placeholder">
              <FileText />
              <b>Văn bản chưa có PDF</b>
              <span>Hãy bổ sung PDF, DOC hoặc DOCX ở bước sửa văn bản</span>
            </div>
          )}
          {url && !loading && (
            <div
              className="signature-ellipse"
              style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              onPointerDown={(e) => {
                e.preventDefault();
                setDragging(true);
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
            >
              <b>ĐÃ KÝ SỐ</b>
              <small>Đại học Hùng Vương</small>
            </div>
          )}
        </div>
        {error && <div className="form-error">{error}</div>}
        <footer>
          <span>
            Hệ thống ký trên bản PDF đã lưu.
          </span>
          <div className="end">
            <button onClick={close} disabled={busy}>
              Hủy
            </button>
            <button
              className="primary"
              onClick={sign}
              disabled={busy || loading || !url}
            >
              {busy ? "Đang ký..." : "Xác nhận ký số"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
function SealStudio({ action, call, token, close, done }) {
  const [url, setUrl] = useState("");
  const [pos, setPos] = useState({ x: 48, y: 68 });
  const [page, setPage] = useState(1);
  const [type, setType] = useState("SCHOOL");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let controller = new AbortController();
    async function loadPdf() {
      try {
        let r = await fetch(`${API}/documents/${action.document.id}/file`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!r.ok) throw Error("Không thể tải PDF đã lưu");
        objectUrl = URL.createObjectURL(await r.blob());
        setUrl(objectUrl);
      } catch (err) {
        if (err.name !== "AbortError") setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadPdf();
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [action.document.id, token]);
  function move(e) {
    if (!dragging) return;
    let r = e.currentTarget.getBoundingClientRect();
    setPos({
      x: Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.max(0, Math.min(100, ((e.clientY - r.top) / r.height) * 100)),
    });
  }
  async function seal() {
    setBusy(true);
    setError("");
    try {
      let f = new FormData();
      f.set("seal_type", type);
      f.set("page", page);
      f.set("x_percent", Math.round(pos.x));
      f.set("y_percent", Math.round(pos.y));
      await call(`/documents/${action.document.id}/digital-seal`, {
        method: "POST",
        body: f,
      });
      done();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal signing-modal">
      <section className="signing-studio">
        <header>
          <div>
            <h2>Đóng dấu văn bản</h2>
            <p>{action.document.title}</p>
          </div>
          <button onClick={close} disabled={busy}>
            Đóng
          </button>
        </header>
        <div className="signing-toolbar">
          <label>
            Loại con dấu
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="SCHOOL">Dấu Trường</option>
              <option value="OFFICE">Dấu Văn phòng</option>
            </select>
          </label>
          <label>
            Trang đóng dấu
            <input
              type="number"
              min="1"
              value={page}
              onChange={(e) =>
                setPage(Math.max(1, Number(e.target.value) || 1))
              }
            />
          </label>
          <span>
            Vị trí: {Math.round(pos.x)}% × {Math.round(pos.y)}%
          </span>
        </div>
        <div
          className="pdf-stage"
          onPointerMove={move}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
        >
          {loading ? (
            <div className="pdf-placeholder">
              <FileText />
              <b>Đang tải PDF đã lưu...</b>
            </div>
          ) : url ? (
            <object
              data={`${url}#page=${page}&toolbar=0`}
              type="application/pdf"
            >
              Không thể hiển thị PDF
            </object>
          ) : (
            <div className="pdf-placeholder">
              <FileText />
              <b>Văn bản chưa có PDF</b>
            </div>
          )}
          {url && !loading && (
            <div
              className="seal-stamp"
              style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              onPointerDown={(e) => {
                e.preventDefault();
                setDragging(true);
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
            >
              <span>
                {type === "SCHOOL" ? "TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG" : "VĂN PHÒNG"}
              </span>
              <b>GIẢ LẬP</b>
              <small>TP. HỒ CHÍ MINH</small>
            </div>
          )}
        </div>
        {error && <div className="form-error">{error}</div>}
        <footer>
          <span>
            Con dấu mô phỏng có chữ “GIẢ LẬP”, không phải mẫu dấu pháp lý.
          </span>
          <div className="end">
            <button onClick={close} disabled={busy}>
              Hủy
            </button>
            <button
              className="primary"
              onClick={seal}
              disabled={busy || loading || !url}
            >
              {busy ? "Đang đóng dấu..." : "Xác nhận đóng dấu"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
function ViewDocumentDialog({ action, token, original = false, close }) {
  const d = action.document,
    [url, setUrl] = useState(""),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    let objectUrl = "",
      controller = new AbortController();
    fetch(`${API}/documents/${d.id}/file${original ? "?original=true" : ""}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw Error(body.detail || "Không thể tải hồ sơ");
        }
        return r.blob();
      })
      .then((b) => {
        objectUrl = URL.createObjectURL(b);
        setUrl(objectUrl);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [d.id, d.updated_at, token, original]);
  let hasOpinion = [
      "OFFICE_OPINION_COMPLETED",
      "PENDING_BGH",
      "BGH_APPROVED",
      "BGH_REJECTED",
      "DEPARTMENT_REVIEW",
      "REVIEW_CHANGES",
      "REVIEW_READY",
      "FORWARDED",
      "ARCHIVED",
    ].includes(d.status),
    description =
      original && d.direction === "IN"
        ? "Bản lưu trữ chỉ gồm văn bản gốc đã tiếp nhận, không kèm phiếu ý kiến."
        : d.direction === "IN"
          ? hasOpinion
            ? "Hồ sơ hiện tại gồm phiếu ý kiến A4 đã ký số ở trang đầu và công văn gốc ở các trang sau."
            : "Hồ sơ hiện tại chỉ gồm công văn gốc; chưa có phiếu ý kiến của Chánh Văn phòng."
          : d.sealed
            ? "Văn bản hiện tại đã được ký số và đóng dấu."
            : d.signed_personal
              ? "Văn bản hiện tại đã được ký số."
              : "Văn bản hiện tại chưa ký số.";
  return (
    <div className="modal document-view-modal">
      <section>
        <header>
          <div>
            <h2>
              {original && d.direction === "IN"
                ? "Xem văn bản gốc lưu trữ"
                : "Xem hồ sơ văn bản"}
            </h2>
            <p>
              {d.symbol || "Chưa cấp số"} · {d.status}
            </p>
          </div>
          <button onClick={close}>Đóng</button>
        </header>
        <div className="view-document-meta">
          <b>{d.title}</b>
          <span>
            {d.issuing_agency || "Chưa có đơn vị ban hành"}
            {d.issued_date ? ` · ${d.issued_date}` : ""}
          </span>
          <p>{description}</p>
        </div>
        <div className="view-document-pdf">
          {loading ? (
            <div className="preview-empty">Đang tải hồ sơ...</div>
          ) : error ? (
            <div className="form-error">{error}</div>
          ) : url ? (
            <object data={`${url}#toolbar=1`} type="application/pdf">
              <a href={url} target="_blank" rel="noreferrer">
                Mở PDF trong tab mới
              </a>
            </object>
          ) : (
            <div className="preview-empty">Không có PDF để hiển thị</div>
          )}
        </div>
      </section>
    </div>
  );
}
function RenameDialog({ action, call, close, done }) {
  const [name, setName] = useState(action.document.file_name || ""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await call(`/documents/${action.document.id}/rename-file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal action-modal">
      <form onSubmit={submit}>
        <h2>Đổi tên file</h2>
        <label>
          Tên file mới
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoFocus
          />
        </label>
        <p>Hệ thống tự giữ phần mở rộng hiện tại nếu bạn không nhập.</p>
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close}>
            Hủy
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Đang đổi tên..." : "Lưu tên mới"}
          </button>
        </div>
      </form>
    </div>
  );
}
function EditReceivedDialog({ action, call, token, close, done }) {
  const pdfTitle = usePdfTitle();
  const d = action.document,
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false),
    [error, setError] = useState(""),
    [originalUrl, setOriginalUrl] = useState(""),
    [replacementUrl, setReplacementUrl] = useState(""),
    [loading, setLoading] = useState(!!d.file_name);
  useEffect(() => {
    if (!d.file_name) {
      setLoading(false);
      return;
    }
    let url = "",
      controller = new AbortController();
    fetch(`${API}/documents/${d.id}/file`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((r) => {
        if (!r.ok) throw Error("Không thể tải file hiện tại");
        return r.blob();
      })
      .then((b) => {
        url = URL.createObjectURL(b);
        setOriginalUrl(url);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => setLoading(false));
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [d.id, d.file_name, d.updated_at, token]);
  useEffect(
    () => () => {
      if (replacementUrl) URL.revokeObjectURL(replacementUrl);
    },
    [replacementUrl],
  );
  async function previewReplacement(e) {
    const f = e.target.files[0];
    setReplacementUrl("");
    setDirty(true);
    if (!f) return;
    if (!/\.docx?$/i.test(f.name)) {
      setReplacementUrl(URL.createObjectURL(f));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.set("file", f);
      const r = await fetch(API + "/documents/preview-upload", {
        method: "POST", headers: { Authorization: `Bearer ${localStorage.token}` }, body,
      });
      if (!r.ok) { const j = await r.json(); throw Error(j.detail || "Không xem trước được Word"); }
      if (e.target.files[0] === f) setReplacementUrl(URL.createObjectURL(await r.blob()));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let body = new FormData(e.currentTarget);
      body.set("doc_type", "CÔNG VĂN");
      await call(`/documents/${d.id}/edit-received`, { method: "POST", body });
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  let previewUrl = replacementUrl || originalUrl;
  return (
    <div className="modal action-modal edit-document-modal">
      <form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={(e) => { if (pdfTitle.reading) { e.preventDefault(); e.stopPropagation(); } }} onSubmit={submit} onChange={() => setDirty(true)}>
        <h2>Sửa công văn đến</h2>
        <p>Tên file PDF được tạo tự động từ số ký hiệu và trích yếu.</p>
        <div className="edit-document-layout">
          <div className="grid">
            <label>
              Loại văn bản
              <input value="CÔNG VĂN ĐẾN" disabled />
            </label>
            <label>
              Ngày ban hành <span className="req">*</span>
              <input
                name="issued_date"
                type="date"
                defaultValue={d.issued_date || ""}
                required
              />
            </label>
            <label className="wide">
              Thay file PDF, DOC hoặc DOCX (không bắt buộc vì đã có file)
              <input
                name="file"
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={previewReplacement}
              />
            </label>
            <label className="wide">
              Trích yếu <span className="req">*</span>
              <input name="title" defaultValue={d.title} required autoFocus />
            </label>
            <label className="wide">
              Đơn vị ban hành <span className="req">*</span>
              <input
                name="issuing_agency"
                defaultValue={d.issuing_agency || ""}
                required
              />
            </label>
            <label className="wide">
              Tóm tắt <small>(không bắt buộc)</small>
              <textarea name="summary" defaultValue={d.summary || ""} />
            </label>

          </div>
          <section className="edit-file-preview">
            <b>
              {replacementUrl ? "Xem trước PDF thay thế" : "File hiện tại"}:{" "}
              {d.file_name || "Chưa có file"}
            </b>
            {loading && !replacementUrl ? (
              <div className="preview-empty">Đang tải file...</div>
            ) : previewUrl ? (
              <object data={`${previewUrl}#toolbar=1`} type="application/pdf">
                <a href={previewUrl} target="_blank" rel="noreferrer">
                  Mở file để kiểm tra
                </a>
              </object>
            ) : (
              <div className="preview-empty">
                Văn bản chưa có PDF để xem trước
              </div>
            )}
          </section>
        </div>
        {error && <div className="form-error">{error}</div>}
        {pdfTitle.message && <p role="status">{pdfTitle.message}</p>}
        <div className="end">
          <button type="button" onClick={close} disabled={busy}>
            Hủy
          </button>
          <button className="primary" disabled={busy || loading || pdfTitle.reading || !dirty}>
            {busy ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
        </div>
      </form>
    </div>
  );
}
function ReserveNumber({ direction, deps, user, token, close, saved, existing }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    canChooseDepartment = ["ADMIN", "CLERK", "OFFICE_HEAD"].includes(user.role),
    department = deps.find(dep => dep.id === user.department_id);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let f = new FormData(e.currentTarget);
      f.set("direction", direction);
      if (!f.get("issued_date")) f.delete("issued_date");
      if (existing) f.set("request_id", existing.id);
      let r = await fetch(API + "/reserve-number", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: f,
        }),
        j = await r.json();
      if (!r.ok) {
        const labels = {issued_date:"Ngày phát hành", department_id:"Đơn vị yêu cầu", title:"Trích yếu", reason:"Lý do xin số", doc_type:"Loại văn bản"};
        const message = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail)
          ? j.detail.map(item => {
              const field = labels[item.loc?.[item.loc.length-1]] || "Thông tin yêu cầu";
              return field + (item.type === "missing" ? ": chưa được nhập" : ": không hợp lệ, vui lòng kiểm tra lại");
            }).join("; ")
          : "Không thể trình xin số, vui lòng thử lại";
        throw Error(message);
      }
      saved(j);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal action-modal">
      <form onSubmit={submit}>
        <h2>
          Xin số{" "}
          {direction === "OUT"
              ? "công văn đi"
              : "văn bản nội bộ"}{" "}
          trước
        </h2>
        {existing && <p style={{whiteSpace:"pre-wrap"}}>{existing.summary}</p>}
        <div className="grid">
          <label>
            Ngày xin số trước
            <input type="date" value={new Date().toLocaleDateString("en-CA")} readOnly />
            <small>Tự động ghi nhận khi tạo xin số.</small>
          </label>
          <label>
              Ngày phát hành
              <input name="issued_date" type="date" defaultValue={existing?.issued_date || ""} />
            </label>
          <label>
            Loại văn bản{" "}
              <select name="doc_type" required defaultValue={existing?.doc_type || ""}>
                <option value="">-- Chọn loại --</option>
                {direction === "OUT" && <option value="CÔNG VĂN">Công văn đi</option>}
                {DOCUMENT_TYPES.map(kind => <option key={kind}>{kind}</option>)}
              </select>
          </label>
          <label className="wide">
            Trích yếu dự kiến <span className="req">*</span>
            <input name="title" required defaultValue={existing?.title || ""} />
          </label>
          <label className="wide">
            Đơn vị yêu cầu
            {canChooseDepartment ? (
              <select name="department_id" required defaultValue={existing?.department_id || ""}>
                <option value="">-- Chọn đơn vị yêu cầu --</option>
                {deps.map(dep => <option key={dep.id} value={dep.id}>{dep.name}</option>)}
              </select>
            ) : <input value={department?.name || "Tài khoản chưa được gán đơn vị"} readOnly />}
          </label>
          <label className="wide">
            Lý do xin số trước <span className="req">*</span>
            <textarea name="reason" required defaultValue={existing?.summary?.split("\nLý do từ chối:")[0].replace(/^Lý do xin số trước: /, "") || ""} />
          </label>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close}>
            Hủy
          </button>
          <button className="primary" disabled={busy || (!canChooseDepartment && !department)}>
            {busy ? "Đang trình..." : existing ? "Trình duyệt lại" : "Trình Văn thư duyệt"}
          </button>
        </div>
      </form>
    </div>
  );
}
function AttachReservedDialog({ action, call, deps, close, done }) {
  const pdfTitle = usePdfTitle();
  const d = action.document,
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await call(`/documents/${d.id}/attach-reserved`, {
        method: "POST",
        body: new FormData(e.currentTarget),
      });
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal action-modal">
      <form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={(e) => { if (pdfTitle.reading) { e.preventDefault(); e.stopPropagation(); } }} onSubmit={submit}>
        <h2>Bổ sung văn bản cho số {d.symbol}</h2>
        <div className="grid">
          <label>
            Ngày xin số trước
            <input type="date" value={new Date(d.created_at + (/[Zz]|[+-]\d{2}:\d{2}$/.test(d.created_at) ? "" : "Z")).toLocaleDateString("en-CA")} readOnly />
          </label>
          <label className="wide">
            File PDF, DOC hoặc DOCX <span className="req">*</span>
            <input
              name="file"
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              required
            />
          </label>
            <label className="wide">
            Trích yếu <span className="req">*</span>
            <input name="title" defaultValue={d.title} required />
          </label>
          <label>
            Ngày phát hành <span className="req">*</span>
            <input name="issued_date" type="date" defaultValue={d.issued_date || ""} required />
          </label>
          <label>
            {d.direction === "OUT" ? "Đơn vị tiếp nhận" : "Đơn vị phát hành"}{" "}
            <span className="req">*</span>
            {d.direction === "INTERNAL" ? (
              <select
                name="issuing_agency"
                defaultValue={d.issuing_agency || ""}
                required
              >
                <option value="">-- Chọn đơn vị --</option>
                {schoolUnits(deps).map((unit) => (
                  <option key={unit.id}>{unit.name}</option>
                ))}
              </select>
            ) : (
              <input
                name="issuing_agency"
                defaultValue={d.issuing_agency || ""}
                required
              />
            )}
          </label>

        </div>
        <p>Số đã giữ nguyên và sẽ được ghép vào tên file sau khi tải lên.</p>
        {error && <div className="form-error">{error}</div>}
        {pdfTitle.message && <p role="status">{pdfTitle.message}</p>}
        <div className="end">
          <button type="button" onClick={close}>
            Hủy
          </button>
          <button className="primary" disabled={busy || pdfTitle.reading}>
            {busy ? "Đang bổ sung..." : "Bổ sung văn bản"}
          </button>
        </div>
      </form>
    </div>
  );
}
function NumberPlacementDialog({ action, token, close, done }) {
  const [field,setField]=useState("number"), [regions,setRegions]=useState({}), [image,setImage]=useState(""), [preview,setPreview]=useState(""), [error,setError]=useState(""), [busy,setBusy]=useState(true), [manual,setManual]=useState(false);
  const start=useRef(null), imageRef=useRef(null);
  useEffect(()=>{let url;const controller=new AbortController();async function autoPreview(){setBusy(true);setError("");try{const r=await fetch(`${API}/documents/${action.document.id}/outgoing-number-preview`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body:new FormData(),signal:controller.signal});if(!r.ok){const j=await r.json();throw Error(typeof j.detail==="string"?j.detail:"Không thể tự nhận diện vị trí")};url=URL.createObjectURL(await r.blob());setPreview(url)}catch(e){if(e.name!=="AbortError"){setManual(true);setError(e.message);try{const page=await fetch(`${API}/documents/${action.document.id}/pages/1/preview`,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal});if(!page.ok)throw Error("Không tải được trang đầu");url=URL.createObjectURL(await page.blob());setImage(url)}catch(loadError){if(loadError.name!=="AbortError")setError(loadError.message)}}}finally{setBusy(false)}}autoPreview();return()=>{controller.abort();if(url)URL.revokeObjectURL(url)}},[action.document.id,token]);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview)},[preview]);
  function point(e){const r=imageRef.current.getBoundingClientRect();return {x:Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100)),y:Math.max(0,Math.min(100,(e.clientY-r.top)/r.height*100))}}
  function move(e){if(!start.current)return;const p=point(e),s=start.current;setRegions(old=>({...old,[field]:{x:Math.min(s.x,p.x),y:Math.min(s.y,p.y),width:Math.abs(p.x-s.x),height:Math.abs(p.y-s.y)}}));setPreview("");}
  async function submit(confirm){setBusy(true);setError("");try{const body=new FormData();if(manual)body.set("placement",JSON.stringify(regions));const r=await fetch(`${API}/documents/${action.document.id}/outgoing-number${confirm ? "" : "-preview"}`,{method:"POST",headers:{Authorization:`Bearer ${token}`},body});if(!r.ok){const j=await r.json();throw Error(typeof j.detail==="string"?j.detail:"Chọn đủ hai vùng số và ngày")}if(confirm)done();else{if(preview)URL.revokeObjectURL(preview);setPreview(URL.createObjectURL(await r.blob()))}}catch(e){setError(e.message)}finally{setBusy(false)}}
  return <div className="modal"><section style={{width:"min(1000px,95vw)",maxHeight:"94vh",overflow:"auto",background:"white",padding:24}}>
    <h2>Điền số và ngày trên văn bản</h2>
    <p>{manual ? "PDF này không nhận diện được tự động. Kéo khoanh phần số (ví dụ 588) và phần từ “ngày” đến hết năm." : "Hệ thống đã tự nhận diện vị trí số và ngày trên trang đầu. Kiểm tra bản xem trước rồi xác nhận."}</p>
    {manual && <div className="actions"><button disabled={busy} onClick={()=>{setField("number");setPreview("")}}>1. Chọn vùng số {regions.number ? "✓" : ""}</button><button disabled={busy} onClick={()=>{setField("date");setPreview("")}}>2. Chọn vùng ngày {regions.date ? "✓" : ""}</button></div>}
    <p>{busy ? "Đang tự nhận diện và điền thử..." : preview ? "Bản xem trước (số chính thức được chốt khi xác nhận)." : `Đang chọn vùng ${field === "number" ? "số" : "ngày"}.`}</p>
    {preview ? <img src={preview} style={{width:"100%"}} alt="Xem trước số và ngày trên trang đầu"/> : <div ref={imageRef} style={{position:"relative",touchAction:"none",cursor:"crosshair"}} onPointerDown={e=>{if(!image||busy)return;e.currentTarget.setPointerCapture(e.pointerId);start.current=point(e)}} onPointerMove={move} onPointerUp={e=>{move(e);start.current=null}} onPointerCancel={()=>{start.current=null}}>
      {image && <img src={image} draggable={false} style={{width:"100%",display:"block",pointerEvents:"none"}} alt="Trang đầu văn bản"/>}
      {Object.entries(regions).map(([key,r])=><div key={key} style={{position:"absolute",pointerEvents:"none",left:r.x+"%",top:r.y+"%",width:r.width+"%",height:r.height+"%",border:`2px solid ${key==="number"?"#1967d2":"#bd3c22"}`,background:"#1967d220"}}/>)}
    </div>}
    {error && <p role="alert">{error}</p>}
    <div className="end"><button onClick={close} disabled={busy}>Hủy</button>{manual && <button disabled={busy||!regions.number||!regions.date} onClick={()=>submit(false)}>Xem trước</button>}<button disabled={busy||!preview} onClick={()=>submit(true)}>Xác nhận vào số và ngày</button></div>
  </section></div>;
}
function MultiPagePlacement({ mode, action, call, token, close, done }) {
  const [pages, setPages] = useState([]),
    [placement, setPlacement] = useState({ page: 1, x: 55, y: action.document.status === "PENDING_OUT_BGH_SIGN" ? 82 : 68 }),
    [sealType, setSealType] = useState("SCHOOL"),
    [dragging, setDragging] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [approvalNote, setApprovalNote] = useState("");
  const bghSigning = mode === "sign" && action.document.status === "PENDING_OUT_BGH_SIGN";
  useEffect(() => {
    let urls = [],
      controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        let suffix = "";
        let metaRes = await fetch(
          `${API}/documents/${action.document.id}/preview-info${suffix}`,
          {
            headers: { Authorization: `Bearer ${token}` },
            signal: controller.signal,
          },
        );
        if (!metaRes.ok) throw Error("Không thể đọc thông tin PDF");
        let meta = await metaRes.json();
        if (mode === "sign") {
          let sig = await fetch(
            `${API}/documents/${action.document.id}/digital-signature`,
            {
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            },
          ).then((r) => (r.ok ? r.json() : null));
          if (sig?.signed && action.document.status !== "PENDING_OUT_BGH_SIGN")
            setPlacement({
              page: sig.page,
              x: sig.x_percent,
              y: sig.y_percent,
            });
        }
        let loaded = await Promise.all(
          meta.pages.map(async (p) => {
            let r = await fetch(
              `${API}/documents/${action.document.id}/pages/${p.page}/preview${suffix}`,
              {
                headers: { Authorization: `Bearer ${token}` },
                signal: controller.signal,
              },
            );
            if (!r.ok) throw Error(`Không thể tải trang ${p.page}`);
            let url = URL.createObjectURL(await r.blob());
            urls.push(url);
            return { ...p, url };
          }),
        );
        setPages(loaded);
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        setLoading(false);
      }
    }
    load();
    return () => {
      controller.abort();
      urls.forEach(URL.revokeObjectURL);
    };
  }, [mode, action.document.id, token]);
  function place(e, page) {
    let r = e.currentTarget.getBoundingClientRect();
    setPlacement({
      page,
      x: Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.max(0, Math.min(100, ((e.clientY - r.top) / r.height) * 100)),
    });
  }
  function start(e, page) {
    e.preventDefault();
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
    place(e, page);
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      let f = new FormData();
      f.set("page", placement.page);
      f.set("x_percent", placement.x.toFixed(6));
      f.set("y_percent", placement.y.toFixed(6));
      if (mode === "seal") f.set("seal_type", sealType);
      if (bghSigning) f.set("note", approvalNote);
      await call(
        `/documents/${action.document.id}/${mode === "sign" ? "digital-sign" : "digital-seal"}`,
        { method: "POST", body: f },
      );
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal signing-modal">
      <section className="signing-studio multi-page-studio">
        <header>
          <div>
            <h2>{mode === "sign" ? "Ký số văn bản" : "Đóng dấu văn bản"}</h2>
            <p>{action.document.title}</p>
          </div>
          <button onClick={close} disabled={busy}>
            Đóng
          </button>
        </header>
        <div className="signing-toolbar">
          {bghSigning && <label>Ý kiến duyệt <span className="req">*</span><textarea value={approvalNote} onChange={e=>setApprovalNote(e.target.value)} placeholder="Nhập ý kiến của BGH trước khi ký số" /></label>}
          {mode === "seal" && (
            <label>
              Loại con dấu
              <select
                value={sealType}
                onChange={(e) => setSealType(e.target.value)}
              >
                <option value="SCHOOL">Dấu Trường</option>
                <option value="OFFICE">Dấu Văn phòng</option>
              </select>
            </label>
          )}
          <strong>
            Cuộn đến trang cần {mode === "sign" ? "ký" : "đóng dấu"}, sau đó
            nhấn hoặc kéo để đặt vị trí
          </strong>
          <span>
            Trang {placement.page} · {Math.round(placement.x)}% ×{" "}
            {Math.round(placement.y)}%
          </span>
        </div>
        <div className="pdf-scroll">
          {loading ? (
            <div className="pdf-placeholder">
              <FileText />
              <b>Đang tải toàn bộ PDF...</b>
            </div>
          ) : (
            pages.map((p) => (
              <div className="page-wrap" key={p.page}>
                <small>
                  Trang {p.page} / {pages.length}
                </small>
                <div
                  className="pdf-page"
                  style={{ aspectRatio: `${p.width}/${p.height}` }}
                  onPointerDown={(e) => start(e, p.page)}
                  onPointerMove={(e) => dragging && place(e, p.page)}
                  onPointerUp={() => setDragging(false)}
                  onPointerCancel={() => setDragging(false)}
                >
                  <img src={p.url} alt={`Trang ${p.page}`} />
                  {placement.page === p.page &&
                    (mode === "sign" ? (
                      <div
                        className="signature-ellipse"
                        style={{
                          left: `${placement.x}%`,
                          top: `${placement.y}%`,
                        }}
                      >
                        <b>ĐÃ KÝ SỐ</b>
                        <small>Đại học Hùng Vương</small>
                      </div>
                    ) : (
                      <div
                        className="seal-stamp"
                        style={{
                          left: `${placement.x}%`,
                          top: `${placement.y}%`,
                        }}
                      >
                        <span>
                          {sealType === "SCHOOL"
                            ? "TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG"
                            : "VĂN PHÒNG"}
                        </span>
                        <b>GIẢ LẬP</b>
                        <small>TP. HỒ CHÍ MINH</small>
                      </div>
                    ))}
                </div>
              </div>
            ))
          )}
        </div>
        {error && <div className="form-error">{error}</div>}
        <footer>
          <span>
            Vị trí được tính riêng theo trang, không phụ thuộc khoảng cuộn.
          </span>
          <div className="end">
            <button onClick={close} disabled={busy}>
              Hủy
            </button>
            <button
              className="primary"
              onClick={confirm}
              disabled={busy || loading || !pages.length || (bghSigning && !approvalNote.trim())}
            >
              {busy
                ? "Đang xử lý..."
                : mode === "sign"
                  ? bghSigning ? "Duyệt và ký số" : "Xác nhận ký số"
                  : "Xác nhận đóng dấu"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
function PlacementStudio({ mode, action, call, token, close, done }) {
  const [url, setUrl] = useState(""),
    [pos, setPos] = useState({ x: 55, y: 68 }),
    [page, setPage] = useState(1),
    [sealType, setSealType] = useState("SCHOOL"),
    [dragging, setDragging] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  useEffect(() => {
    let objectUrl = "",
      controller = new AbortController();
    setLoading(true);
    setError("");
    fetch(
      `${API}/documents/${action.document.id}/pages/${page}/preview`,
      {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      },
    )
      .then(async (r) => {
        if (!r.ok)
          throw Error(
            r.status === 404
              ? "Trang PDF không tồn tại"
              : "Không thể tải trang PDF",
          );
        objectUrl = URL.createObjectURL(await r.blob());
        setUrl(objectUrl);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setUrl("");
          setError(e.message);
        }
      })
      .finally(() => setLoading(false));
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [action.document.id, page, token, mode]);
  useEffect(() => {
    if (mode !== "sign") return;
    fetch(`${API}/documents/${action.document.id}/digital-signature`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((x) => {
        if (x?.signed) {
          setPos({ x: x.x_percent, y: x.y_percent });
          setPage(x.page);
        }
      });
  }, [mode, action.document.id, token]);
  function place(e) {
    let r = e.currentTarget.getBoundingClientRect();
    setPos({
      x: Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)),
      y: Math.max(0, Math.min(100, ((e.clientY - r.top) / r.height) * 100)),
    });
  }
  function start(e) {
    e.preventDefault();
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
    place(e);
  }
  function move(e) {
    if (dragging) place(e);
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      let f = new FormData();
      f.set("page", page);
      f.set("x_percent", Math.round(pos.x));
      f.set("y_percent", Math.round(pos.y));
      if (mode === "seal") f.set("seal_type", sealType);
      await call(
        `/documents/${action.document.id}/${mode === "sign" ? "digital-sign" : "digital-seal"}`,
        { method: "POST", body: f },
      );
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal signing-modal">
      <section className="signing-studio">
        <header>
          <div>
            <h2>{mode === "sign" ? "Ký số văn bản" : "Đóng dấu văn bản"}</h2>
            <p>{action.document.title}</p>
          </div>
          <button onClick={close} disabled={busy}>
            Đóng
          </button>
        </header>
        <div className="signing-toolbar">
          {mode === "seal" && (
            <label>
              Loại con dấu
              <select
                value={sealType}
                onChange={(e) => setSealType(e.target.value)}
              >
                <option value="SCHOOL">Dấu Trường</option>
                <option value="OFFICE">Dấu Văn phòng</option>
              </select>
            </label>
          )}
          <label>
            Trang {mode === "sign" ? "ký" : "đóng dấu"}
            <input
              type="number"
              min="1"
              value={page}
              onChange={(e) =>
                setPage(Math.max(1, Number(e.target.value) || 1))
              }
            />
          </label>
          <span>
            Vị trí: {Math.round(pos.x)}% × {Math.round(pos.y)}%
          </span>
        </div>
        <div
          className="pdf-stage exact-preview"
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
        >
          {loading ? (
            <div className="pdf-placeholder">
              <FileText />
              <b>Đang render trang PDF...</b>
            </div>
          ) : url ? (
            <img src={url} alt={`Trang PDF ${page}`} />
          ) : (
            <div className="pdf-placeholder">
              <FileText />
              <b>Không thể hiển thị trang PDF</b>
            </div>
          )}
          {url &&
            !loading &&
            (mode === "sign" ? (
              <div
                className="signature-ellipse"
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              >
                <b>ĐÃ KÝ SỐ</b>
                <small>Đại học Hùng Vương</small>
              </div>
            ) : (
              <div
                className="seal-stamp"
                style={{ left: `${pos.x}%`, top: `${pos.y}%` }}
              >
                <span>
                  {sealType === "SCHOOL"
                    ? "TRƯỜNG ĐẠI HỌC HÙNG VƯƠNG"
                    : "VĂN PHÒNG"}
                </span>
                <b>GIẢ LẬP</b>
                <small>TP. HỒ CHÍ MINH</small>
              </div>
            ))}
        </div>
        {error && <div className="form-error">{error}</div>}
        <footer>
          <span>Nhấn hoặc kéo trực tiếp trên trang để đặt đúng vị trí.</span>
          <div className="end">
            <button onClick={close} disabled={busy}>
              Hủy
            </button>
            <button
              className="primary"
              onClick={confirm}
              disabled={busy || loading || !url}
            >
              {busy
                ? "Đang xử lý..."
                : mode === "sign"
                  ? "Xác nhận ký số"
                  : "Xác nhận đóng dấu"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
function InternalApprovalDialog({ action, call, close, done }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    approving = action.type === "INTERNAL_APPROVE";
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await call(
        `/documents/${action.document.id}/${approving ? "internal-approve" : "internal-submit"}`,
        {
          method: "POST",
          body: approving ? new FormData(e.currentTarget) : undefined,
        },
      );
      done();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      className="modal action-modal"
      onMouseDown={(e) => e.target === e.currentTarget && !busy && close()}
    >
      <form onSubmit={submit}>
        <h2>
          {approving
            ? "Phê duyệt văn bản nội bộ"
            : "Trình Chánh Văn phòng phê duyệt"}
        </h2>
        <p>
          {approving
            ? "Xác nhận văn bản đủ điều kiện để chuyển sang bước đóng dấu và phát hành?"
            : "Văn bản đã được cấp số. Xác nhận trình Chánh Văn phòng xem xét, phê duyệt trước khi đóng dấu?"}
        </p>
        {approving && (
          <label>
            Ý kiến phê duyệt
            <textarea
              name="note"
              placeholder="Nhập ý kiến (không bắt buộc)"
              autoFocus
            />
          </label>
        )}
        {error && <div className="form-error">{error}</div>}
        <div className="end">
          <button type="button" onClick={close} disabled={busy}>
            Hủy
          </button>
          <button className="primary" disabled={busy}>
            {busy
              ? "Đang xử lý..."
              : approving
                ? "Xác nhận phê duyệt"
                : "Xác nhận trình duyệt"}
          </button>
        </div>
      </form>
    </div>
  );
}
function IncomingRowActions({ d, act, permissions }) {
  const [busy, setBusy] = useState(false),
    can = (code) => permissions.includes(code);
  async function takeNumber() {
    if (busy) return;
    setBusy(true);
    try {
      let r = await fetch(`${API}/documents/${d.id}/incoming-number`, {
          method: "POST",
          headers: { Authorization: `Bearer ${localStorage.token}` },
          body: new FormData(),
        }),
        j = await r.json();
      if (!r.ok) throw Error(j.detail || "Không thể lấy số");
      location.reload();
    } catch (e) {
      alert(e.message);
      setBusy(false);
    }
  }
  async function attach(e) {
    let file = e.target.files[0];
    if (!file) return;
    let f = new FormData();
    f.set("file", file);
    let r = await fetch(`${API}/documents/${d.id}/attach-reserved`, {
      method: "POST",
      headers: { Authorization: `Bearer ${localStorage.token}` },
      body: f,
    });
    if (r.ok) location.reload();
    else alert((await r.json()).detail || "Không thể bổ sung văn bản");
  }
  let controls =
    d.status === "RESERVED_INCOMING" && can("EDIT") ? (
      <label className="attach-button">
        Bổ sung PDF / DOC / DOCX
        <input type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={attach} />
      </label>
    ) : d.status === "RECEIVED" ? (
      <>
        {can("EDIT") && (
          <button onClick={() => act(d, "IN_EDIT")} disabled={busy}>
            Sửa
          </button>
        )}
        {can("ASSIGN_NUMBER") && (
          <button onClick={takeNumber} disabled={busy}>
            {busy ? "Đang lấy số..." : "Lấy số"}
          </button>
        )}
      </>
    ) : d.status === "NUMBERED" ? (
      <>
        {can("EDIT") && (
          <button onClick={() => act(d, "IN_EDIT")} disabled={busy}>
            Sửa
          </button>
        )}
        {can("OFFICE_OPINION") && (
          <button onClick={() => act(d, "IN_REVIEW")}>Giao việc / phản hồi</button>
        )}
      </>
    ) : !["DELETED", "RESERVED_INCOMING"].includes(d.status) ? (
      <>
        <button onClick={() => act(d, "IN_REVIEW")}>Giao việc / phản hồi</button>
        {["REVIEW_READY", "FORWARDED"].includes(d.status) && can("ARCHIVE") && <button onClick={() => act(d, "ARCHIVE")}>{d.status === "REVIEW_READY" ? "Lưu không gửi mail" : "Lưu trữ + OCR"}</button>}
      </>
    ) : null;
  return (
    <>
      {controls}
      {can("DELETE") && (
        <button
          className="danger-link"
          onClick={() => act(d, "DELETE")}
          disabled={busy}
        >
          Xóa
        </button>
      )}
    </>
  );
}
function OutgoingRowActions({ d, act, permissions }) {
  const [busy, setBusy] = useState(false),
    can = (code) => permissions.includes(code);
  const role = JSON.parse(localStorage.user || "null")?.role;
  const unitSigner = ["ADMIN", "DEPARTMENT", "DEPARTMENT_HEAD", "OFFICE_HEAD"].includes(role);
  const bghSigner = ["ADMIN", "BGH"].includes(role);
  let controls =
    d.status === "RESERVED_OUTGOING" && can("EDIT") ? (
      <button onClick={() => act(d, "ATTACH_RESERVED")}>Bổ sung PDF / DOC / DOCX</button>
    ) : ["DRAFT", "RETURNED"].includes(d.status) && can("EDIT") ? (
      <>
        <button onClick={() => act(d, "OUT_EDIT")}>Sửa</button>
        {unitSigner && can("SIGN") && <button onClick={() => act(d, "PERSONAL_SIGN")}>Trưởng đơn vị ký</button>}
        <button onClick={() => act(d, "OUT_SUBMIT_SIGN")}>Gửi BGH ký số</button>
      </>
    ) : d.status === "PENDING_OFFICE_SIGN" && unitSigner && can("SIGN") ? (
      <button onClick={() => act(d, "PERSONAL_SIGN")}>Trưởng đơn vị ký</button>
    ) : ["UNIT_SIGNED", "OFFICE_SIGNED"].includes(d.status) && can("EDIT") ? (
      <button onClick={() => act(d, "OUT_SUBMIT_APPROVAL")}>Gửi BGH duyệt</button>
    ) : d.status === "PENDING_OUT_BGH_APPROVAL" && bghSigner ? (
      <>
        <button onClick={() => act(d, "BGH_APPROVE")}>Duyệt</button>
        <button onClick={() => act(d, "OUT_RETURN")}>Trả lại</button>
      </>
    ) : d.status === "PENDING_OUT_BGH_SIGN" && bghSigner && can("SIGN") ? (
      <>
        <button onClick={() => act(d, "PERSONAL_SIGN")}>Duyệt và ký số</button>
        <button onClick={() => act(d, "OUT_RETURN")}>Trả lại</button>
      </>
    ) : d.status === "READY_FOR_CLERK" && can("ASSIGN_NUMBER") ? (
      <button onClick={() => act(d, "OUT_NUMBER")} disabled={busy}>
        Vào số và ngày
      </button>
    ) : d.status === "OUT_NUMBERED" && can("SEAL") ? (
      <button onClick={() => act(d, "SEAL_SIGN")}>Đóng dấu</button>
    ) : d.status === "SEALED" ? (
      <>
        {can("EMAIL") && <button onClick={() => act(d, "OUT_EMAIL")}>Gửi mail</button>}
        {can("ARCHIVE") && <button onClick={() => act(d, "ARCHIVE")}>Lưu không gửi mail</button>}
      </>
    ) : d.status === "EMAILED" && can("ARCHIVE") ? (
      <button onClick={() => act(d, "ARCHIVE")}>Lưu trữ + OCR</button>
    ) : null;
  return (
    <>
      {controls}
      {can("DELETE") && (
        <button
          className="danger-link"
          onClick={() => act(d, "DELETE")}
          disabled={busy}
        >
          Xóa
        </button>
      )}
    </>
  );
}
function InternalRowActions({ d, act, permissions }) {
  const [busy, setBusy] = useState(false),
    can = (code) => permissions.includes(code);
  async function takeNumber() {
    setBusy(true);
    try {
      let r = await fetch(`${API}/documents/${d.id}/internal-number`, {
          method: "POST",
          headers: { Authorization: `Bearer ${localStorage.token}` },
        }),
        j = await r.json();
      if (!r.ok) throw Error(j.detail || "Không thể cấp số");
      location.reload();
    } catch (e) {
      alert(e.message);
      setBusy(false);
    }
  }
  let controls =
    d.status === "RESERVED_INTERNAL" && can("EDIT") ? (
      <button onClick={() => act(d, "ATTACH_RESERVED")}>Bổ sung PDF / DOC / DOCX</button>
    ) : d.status === "DRAFT" && can("ASSIGN_NUMBER") ? (
      <button onClick={takeNumber} disabled={busy}>
        {busy ? "Đang cấp số..." : "Cấp số"}
      </button>
    ) : d.status === "INTERNAL_NUMBERED" && can("EDIT") ? (
      <button onClick={() => act(d, "INTERNAL_SUBMIT")}>Trình Chánh VP</button>
    ) : d.status === "PENDING_INTERNAL_APPROVAL" && can("INTERNAL_APPROVE") ? (
      <button onClick={() => act(d, "INTERNAL_APPROVE")}>Phê duyệt</button>
    ) : d.status === "INTERNAL_APPROVED" && can("SEAL") ? (
      <button onClick={() => act(d, "SEAL_SIGN")}>Đóng dấu</button>
    ) : d.status === "INTERNAL_SEALED" ? (
      <>
        {can("EMAIL") && <button onClick={() => act(d, "INTERNAL_EMAIL")}>Gửi mail</button>}
        {can("ARCHIVE") && <button onClick={() => act(d, "ARCHIVE")}>Lưu không gửi mail</button>}
      </>
    ) : d.status === "INTERNAL_PUBLISHED" && can("ARCHIVE") ? (
      <button onClick={() => act(d, "ARCHIVE")}>Lưu trữ + OCR</button>
    ) : null;
  return (
    <>
      {controls}
      {can("DELETE") && (
        <button className="danger-link" onClick={() => act(d, "DELETE")}>
          Xóa
        </button>
      )}
    </>
  );
}
function Table({ rows, act, download, permissions = [] }) {
  return (
    <div className="table">
      <div className="tr head">
        <span>SỐ / KÝ HIỆU</span>
        <span>TRÍCH YẾU</span>
        <span>LOẠI</span>
        <span>TRẠNG THÁI</span>
        <span>THAO TÁC</span>
      </div>
      {rows.map((d) => (
        <div className="tr" key={d.id}>
          <span>
            <b>{d.symbol || "Chưa cấp số"}</b>
            {d.direction === "IN" && d.received_date && <small>{new Date(d.received_date + "T00:00:00").toLocaleDateString("vi-VN")}</small>}
            <small>
              {d.direction === "IN"
                ? "Văn bản đến"
                : d.direction === "OUT"
                  ? "Văn bản đi"
                  : "Văn bản nội bộ"}
            </small>
          </span>
          <span>
            {d.title}
            <small>{d.issuing_agency}</small>
            {d.reserved && (
              <>
                <small>Ngày xin số trước: {new Date(d.created_at + (/[Zz]|[+-]\d{2}:\d{2}$/.test(d.created_at) ? "" : "Z")).toLocaleDateString("vi-VN")}</small>
                {d.direction !== "IN" && <small>Ngày phát hành: {d.issued_date ? new Date(d.issued_date + "T00:00:00").toLocaleDateString("vi-VN") : "Chưa có"}</small>}
              </>
            )}
          </span>
          <span>{d.doc_type}</span>
          <span>
            <em>{{RESERVATION_PENDING:"Xin số chờ Văn thư duyệt", RESERVATION_REJECTED:"Xin số bị từ chối", DRAFT:"Bản nháp", RETURNED:"BGH trả lại đơn vị", UNIT_SIGNED:"Lãnh đạo đơn vị đã ký", PENDING_OUT_BGH_APPROVAL:"Chờ BGH duyệt", PENDING_OUT_BGH_SIGN:"Chờ BGH duyệt và ký", READY_FOR_CLERK:"Đã ký duyệt — chờ Văn thư", OUT_NUMBERED:"Đã vào số", SEALED:"Đã đóng dấu", EMAILED:"Đã gửi"}[d.status] || d.status}</em>
            {d.direction === "OUT" && <small>Phiên bản {d.revision || 1}</small>}
          </span>
          <span className="actions">
            {act && d.status==="RESERVATION_PENDING" && JSON.parse(localStorage.user || "null")?.role==="CLERK" && <button onClick={()=>act(d,"RESERVATION_REVIEW")}>Duyệt / Từ chối xin số</button>}
            {act && d.status==="RESERVATION_REJECTED" && JSON.parse(localStorage.user || "null")?.id===d.owner_id && <><button onClick={()=>act(d,"RESERVATION_EDIT")}>Chỉnh sửa và trình lại</button><button onClick={()=>act(d,"RESERVATION_DELETE")}>Xoá yêu cầu</button></>}
            {act && d.file_name && (
              <button onClick={() => act(d, "VIEW")}>Xem</button>
            )}
            {act &&
              (d.direction === "IN" ? (
                <IncomingRowActions d={d} act={act} permissions={permissions} />
              ) : d.direction === "OUT" ? (
                <OutgoingRowActions d={d} act={act} permissions={permissions} />
              ) : (
                <InternalRowActions d={d} act={act} permissions={permissions} />
              ))}
            {download && d.file_name && (
              <button onClick={() => download(d)}>Tải PDF</button>
            )}
          </span>
        </div>
      ))}
      {!rows.length && <div className="empty">Chưa có văn bản phù hợp</div>}
    </div>
  );
}
function Create({ direction, deps, token, close, saved }) {
  const pdfTitle = usePdfTitle();
  const [kind, setKind] = useState("CÔNG VĂN");
  const [saving, setSaving] = useState(false),
    office = deps.find(
      (x) => x.code === "VP" || x.name.toLowerCase().includes("văn phòng"),
    ),
    internal = direction === "OUT" && kind !== "CÔNG VĂN";
  async function go(e) {
    e.preventDefault();
    setSaving(true);
    try {
      let f = new FormData(e.target);
      f.set("direction", direction);
      f.set("doc_type", direction === "OUT" ? kind : "CÔNG VĂN");
      if (office) f.set("department_id", office.id);
      let r = await fetch(API + "/documents", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: f,
      });
      let j = await r
        .json()
        .catch(() => ({ detail: "Máy chủ trả về dữ liệu không hợp lệ" }));
      if (!r.ok) throw Error(j.detail || `Không thể lưu văn bản (${r.status})`);
      saved(j);
    } catch (err) {
      alert(`Lưu văn bản thất bại: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="modal">
      <form onChangeCapture={pdfTitle.onChangeCapture} onSubmitCapture={(e) => { if (pdfTitle.reading) { e.preventDefault(); e.stopPropagation(); } }} onSubmit={go}>
        <h2>
          {direction === "IN"
            ? "Tiếp nhận công văn đến"
            : direction === "OUT"
              ? "Tạo công văn đi"
              : "Tạo công văn nội bộ"}
        </h2>
        <div className="grid">
          <label>
            Loại văn bản <span className="req">*</span>
            {direction === "OUT" ? (
              <select value={kind} onChange={(e) => setKind(e.target.value)} name="doc_type">
                <option value="CÔNG VĂN">Công văn đi</option>
                {DOCUMENT_TYPES.map(kind => <option key={kind}>{kind}</option>)}
              </select>
            ) : <input value="CÔNG VĂN ĐẾN" disabled />}
          </label>
          <label>Ngày ban hành <span className="req">*</span>
            <input type="date" name="issued_date" defaultValue={new Date().toLocaleDateString("en-CA")} required />
          </label>
          <label className="wide">
            File PDF, DOC hoặc DOCX <span className="req">*</span>
            <input
              type="file"
              name="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              required
            />
          </label>
            <label className="wide">
            Trích yếu <span className="req">*</span>
            <input name="title" required />
          </label>
          <label>
            {internal
              ? "Đơn vị tiếp nhận trong trường"
              : direction === "IN"
                ? "Đơn vị ban hành"
                : "Đơn vị tiếp nhận"}{" "}
            <span className="req">*</span>
            {internal ? (
              <select name="issuing_agency" required>
                <option value="">-- Chọn đơn vị --</option>
                {schoolUnits(deps).map((unit) => (
                  <option key={unit.id}>{unit.name}</option>
                ))}
              </select>
            ) : (
              <input name="issuing_agency" required />
            )}
          </label>
          <label>
            {direction === "OUT" ? "Đơn vị soạn thảo" : "Đơn vị xử lý"} <span className="req">*</span>
            <input value={direction === "OUT" ? deps.find(d => d.id === JSON.parse(localStorage.user || "null")?.department_id)?.name || "Chưa gán đơn vị" : "Văn phòng Trường"} disabled />
            <input
              type="hidden"
              name="department_id"
              value={office?.id || ""}
            />
          </label>
          <label className="wide">
            Tóm tắt <small>(không bắt buộc)</small>
            <textarea name="summary" />
          </label>

        </div>
        {pdfTitle.message && <p role="status">{pdfTitle.message}</p>}
        <div className="end">
          <button type="button" onClick={close} disabled={saving}>
            Hủy
          </button>
          <button className="primary" disabled={saving || pdfTitle.reading}>
            {saving ? "Đang lưu..." : "Lưu văn bản"}
          </button>
        </div>
      </form>
    </div>
  );
}
function PermissionEditor({ roles, onMessage }) {
  const [values, setValues] = useState({});
  useEffect(
    () =>
      setValues(
        Object.fromEntries(
          (roles || []).map((r) => [
            r.code,
            (r.permission_options || [])
              .filter((p) => p.enabled)
              .map((p) => p.code),
          ]),
        ),
      ),
    [roles],
  );
  async function save(role) {
    let r = await fetch(API + "/config/permissions", {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${localStorage.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          role: role.code,
          permissions: values[role.code] || [],
        }),
      }),
      j = await r.json().catch(() => ({}));
    onMessage(
      r.ok
        ? `Đã lưu phân quyền ${role.name}`
        : j.detail || "Không thể lưu phân quyền",
    );
  }
  function toggle(role, code) {
    setValues((v) => ({
      ...v,
      [role]: v[role]?.includes(code)
        ? v[role].filter((x) => x !== code)
        : [...(v[role] || []), code],
    }));
  }
  return (
    <div className="permission-editor">
      {(roles || []).map((role) => (
        <article key={role.code}>
          <header>
            <div>
              <b>{role.name}</b>
              <small>{role.code}</small>
            </div>
            <button onClick={() => save(role)} disabled={role.code === "ADMIN"}>
              {role.code === "ADMIN" ? "Đã khóa" : "Lưu quyền"}
            </button>
          </header>
          <div>
            {(role.permission_options || []).map((p) => (
              <label key={p.code}>
                <input
                  type="checkbox"
                  checked={(values[role.code] || []).includes(p.code)}
                  disabled={role.code === "ADMIN"}
                  onChange={() => toggle(role.code, p.code)}
                />
                <span>{p.name}</span>
              </label>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}
function DepartmentEmails({ departments }) {
  const [message,setMessage]=useState('');
  async function save(e,id){e.preventDefault();const email=new FormData(e.currentTarget).get('email');try{const r=await fetch(`${API}/config/departments/${id}/email`,{method:'PUT',headers:{Authorization:`Bearer ${localStorage.token}`,'Content-Type':'application/json'},body:JSON.stringify({email})});const j=await r.json();if(!r.ok)throw Error(j.detail);setMessage('Đã lưu email đơn vị.');}catch(e){setMessage(e.message);}}
  return <section className="panel"><h3>Email các phòng ban</h3><p>Địa chỉ nhận email báo việc theo đơn vị, dùng chung cho các công văn.</p>{message&&<p role="status">{message}</p>}{schoolUnits(departments).map(d=><form key={d.id} onSubmit={e=>save(e,d.id)} style={{display:'flex',gap:12,alignItems:'center',marginBottom:12}}><label style={{flex:1}}>{d.name}</label><input aria-label={`Email ${d.name}`} name="email" type="email" defaultValue={d.email || ''} placeholder="Email đơn vị"/><button type="submit">Lưu</button></form>)}</section>;
}
function CreateUnitAccount({ departments }) {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState("");
  async function submit(e) {
    e.preventDefault(); const form=e.currentTarget; setBusy(true); setMessage("");
    try {
      const body=Object.fromEntries(new FormData(form)); body.department_id=Number(body.department_id);
      const r=await fetch(`${API}/config/users`, {method:"POST", headers:{Authorization:`Bearer ${localStorage.token}`, "Content-Type":"application/json"},body:JSON.stringify(body)});
      const j=await r.json(); if(!r.ok) throw Error(typeof j.detail === "string" ? j.detail : "Kiểm tra thông tin tài khoản");
      location.reload();
    } catch(e) {setMessage(e.message);} finally {setBusy(false);}
  }
  return <form onSubmit={submit} className="create-unit-account">
    <div className="create-unit-heading"><div><h4>Cấp tài khoản đơn vị</h4><p>Tạo tài khoản cho chuyên viên hoặc lãnh đạo của một đơn vị trong trường.</p></div></div>
    <div className="create-unit-fields">
      <label><span>Tên đăng nhập <i>*</i></span><input name="username" required autoComplete="off" placeholder="Ví dụ: phong_dao_tao" /></label>
      <label><span>Họ tên <i>*</i></span><input name="full_name" required placeholder="Nhập họ và tên" /></label>
      <label><span>Mật khẩu ban đầu <i>*</i></span><input name="password" type="password" minLength={8} required autoComplete="new-password" placeholder="Tối thiểu 8 ký tự" /></label>
      <label><span>Vai trò <i>*</i></span><select name="role"><option value="DEPARTMENT">Chuyên viên đơn vị — soạn thảo</option><option value="DEPARTMENT_HEAD">Lãnh đạo đơn vị — ký số</option></select></label>
      <label className="create-unit-department"><span>Đơn vị <i>*</i></span><select name="department_id" required><option value="">-- Chọn đơn vị --</option>{departments.filter(d=>d.code!=="BGH").map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
    </div>
    <div className="create-unit-actions"><button className="primary" disabled={busy}>{busy ? "Đang tạo..." : "Tạo tài khoản"}</button></div>
    {message && <p className="form-error" role="alert">{message}</p>}
  </form>;
}
function ConfigUserRow({ user, roles, departments, onSave }) {
  const locked=user.username==="admin",[role,setRole]=useState(user.role),[departmentId,setDepartmentId]=useState(String(user.department_id || ""));
  const options=role==="BGH"||locked?departments.filter(d=>d.code==="BGH"):schoolUnits(departments);
  function changeRole(e){const next=e.target.value;setRole(next);if(next==="BGH")setDepartmentId(String(departments.find(d=>d.code==="BGH")?.id || ""));else if(["OFFICE_HEAD","CLERK"].includes(next))setDepartmentId(String(departments.find(d=>d.code==="VP")?.id || ""));else if(departments.find(d=>String(d.id)===departmentId)?.code==="BGH")setDepartmentId("");}
  return <form className={locked?"is-locked":""} onSubmit={e=>onSave(e,user)}>
    <b className="config-username">{user.username}</b>
    <input aria-label={`Họ tên ${user.username}`} name="full_name" defaultValue={user.full_name} required disabled={locked}/>
    <select aria-label={`Vai trò ${user.username}`} name="role" value={role} onChange={changeRole} disabled={locked}>{(roles||[]).filter(r=>r.code!=="ADMIN"||locked).map(r=><option key={r.code} value={r.code}>{r.name}</option>)}</select>
    <select aria-label={`Đơn vị ${user.username}`} name="department_id" value={departmentId} onChange={e=>setDepartmentId(e.target.value)} disabled={locked}><option value="">Không gán đơn vị</option>{options.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
    <label className="check"><input name="active" type="checkbox" defaultChecked={user.active} disabled={locked}/><span>Hoạt động</span></label>
    <button disabled={locked}>Lưu</button>
  </form>;
}
function Config({ c }) {
  const [activity, setActivity] = useState([]),
    [message, setMessage] = useState(""),
    [reindexing, setReindexing] = useState(false),
    headers = {
      Authorization: `Bearer ${localStorage.token}`,
      "Content-Type": "application/json",
    };
  useEffect(() => {
    fetch(API + "/activity", {
      headers: { Authorization: `Bearer ${localStorage.token}` },
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setActivity);
  }, []);
  async function reindex() {
    setReindexing(true);
    try {
      let r = await fetch(API + "/ai/reindex", {
          method: "POST",
          headers: { Authorization: `Bearer ${localStorage.token}` },
        }),
        j = await r.json();
      setMessage(
        r.ok
          ? `Đã đồng bộ lại chỉ mục AI: ${j.db?.documents ?? j.scanned_files ?? 0} văn bản`
          : j.detail || "Không thể đồng bộ chỉ mục AI",
      );
    } catch (err) {
      setMessage(err.message);
    } finally {
      setReindexing(false);
    }
  }
  async function saveUser(e, user) {
    e.preventDefault();
    let body = Object.fromEntries(new FormData(e.currentTarget));
    body.department_id = body.department_id ? Number(body.department_id) : null;
    body.active = body.active === "on";
    let r = await fetch(`${API}/config/users/${user.id}`, {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
    });
    setMessage(r.ok ? "Đã cập nhật người dùng" : (await r.json()).detail);
  }
  async function saveEmail(e) {
    e.preventDefault();
    let body = Object.fromEntries(new FormData(e.currentTarget));
    if (!htmlHasContent(body.signature_html)) {
      setMessage("Chữ ký email là bắt buộc");
      return;
    }
    body.smtp_port = Number(body.smtp_port);
    body.use_tls = body.use_tls === "on";
    body.enabled = body.enabled === "on";
    let r = await fetch(API + "/config/email", {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
    });
    setMessage(r.ok ? "Đã lưu cấu hình email" : (await r.json()).detail);
  }
  return (
    <div className="config-page">
      {message && <div className="config-message">{message}</div>}
      <section className="panel">
        <h3>Người dùng và vai trò</h3>
        <CreateUnitAccount departments={c.departments || []} />
        <p>Quản lý vai trò, đơn vị và trạng thái sử dụng của từng tài khoản.</p>
        <div className="config-users">
          <div className="config-users-head" aria-hidden="true">
            <span>Tài khoản</span>
            <span>Họ tên</span>
            <span>Vai trò</span>
            <span>Đơn vị</span>
            <span>Trạng thái</span>
            <span>Thao tác</span>
          </div>
          {(c.users || []).map(user=><ConfigUserRow key={user.id} user={user} roles={c.roles || []} departments={c.departments || []} onSave={saveUser}/>) }
        </div>
      </section>
      <section className="panel">
        <h3>Phân quyền theo vai trò</h3>
        <p>
          Bật hoặc tắt quyền có hiệu lực trực tiếp trên API. Quyền Admin được
          khóa để tránh mất quyền quản trị.
        </p>
        <PermissionEditor roles={c.roles || []} onMessage={setMessage} />
      </section>
      <section className="panel">
        <DepartmentEmails departments={c.departments || []} />
        <EmailTemplates />
        <h3>Cấu hình email</h3>
        <p>Gửi thư qua Gmail Web: <b>ngcphnglinhp6.7.2000@gmail.com</b>. Người dùng đăng nhập và tự bấm Gửi trong Gmail. Cấu hình SMTP bên dưới không được dùng cho thao tác này.</p>
        <form className="email-config" onSubmit={saveEmail}>
          <label>
            SMTP host
            <input name="smtp_host" defaultValue={c.email?.smtp_host || ""} />
          </label>
          <label>
            Cổng SMTP
            <input
              name="smtp_port"
              type="number"
              defaultValue={c.email?.smtp_port || 587}
            />
          </label>
          <label>
            Tài khoản SMTP
            <input name="username" defaultValue={c.email?.username || ""} />
          </label>
          <label>
            Tên người gửi
            <input
              name="sender_name"
              defaultValue={c.email?.sender_name || ""}
            />
          </label>
          <label>
            Email người gửi
            <input
              name="sender_email"
              type="email"
              defaultValue={c.email?.sender_email || ""}
            />
          </label>
          <label className="wide">
            Tiêu đề email nhắc hạn
            <input name="reminder_subject" defaultValue={c.email?.reminder_subject || "Nhắc hạn nộp báo cáo: {title}"} required />
          </label>
          <label className="wide">
            Nội dung email nhắc hạn
            <textarea name="reminder_html" defaultValue={c.email?.reminder_html || "<p>Đơn vị chưa nộp báo cáo cho hồ sơ <b>{title}</b>.</p><p>Hạn nộp: <b>{deadline}</b>.</p>"} required />
            <small>Dùng được: {"{title}"}, {"{symbol}"}, {"{deadline}"}, {"{missing_units}"}. Email tự gửi trước hạn một ngày.</small>
          </label>
          <SignatureConfig initial={c.email?.signature_html || ""} />
          <label className="check">
            <input
              name="use_tls"
              type="checkbox"
              defaultChecked={c.email?.use_tls !== false}
            />{" "}
            Sử dụng TLS
          </label>
          <label className="check">
            <input
              name="enabled"
              type="checkbox"
              defaultChecked={c.email?.enabled}
            />{" "}
            Bật gửi email
          </label>
          <button className="primary">Lưu cấu hình email</button>
        </form>
      </section>
      <section className="panel">
        <h3>Trợ lý AI</h3>
        <p>
          Đồng bộ lại chỉ mục tìm kiếm từ thư mục documents/ khi có văn bản mới
          hoặc thay đổi.
        </p>
        <button className="primary" onClick={reindex} disabled={reindexing}>
          {reindexing ? "Đang đồng bộ..." : "Đồng bộ lại chỉ mục"}
        </button>
      </section>
      <section className="panel">
        <h3>Activity log</h3>
        <div className="activity-table">
          <div className="activity-head">
            <b>THỜI GIAN</b>
            <b>NGƯỜI THỰC HIỆN</b>
            <b>THAO TÁC</b>
            <b>VĂN BẢN</b>
            <b>CHI TIẾT</b>
          </div>
          {activity.map((x) => (
            <div key={x.id}>
              <time>{new Date(x.created_at).toLocaleString("vi-VN")}</time>
              <span>
                <b>{x.full_name}</b>
                <small>
                  {x.username} · {x.role}
                </small>
              </span>
              <code>{ACTION_LABELS[x.action] || x.action}</code>
              <span>
                <b>{x.symbol || "Chưa cấp số"}</b>
                <small>{x.title}</small>
              </span>
              <span>{x.comment || "—"}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
createRoot(document.getElementById("root")).render(<App />);
