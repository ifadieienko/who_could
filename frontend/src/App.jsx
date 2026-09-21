import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { session } from './session';
import { AdminPanel } from './AdminPanel.jsx';
import { CustomerPickup } from './CustomerPickup.jsx';
import { DeviceIntake } from './DeviceIntake.jsx';
import { MasterBoard } from './MasterBoard.jsx';
import { Warehouse } from './Warehouse.jsx';
import { Badge } from './components/Badge.jsx';
import { Button } from './components/Button.jsx';
import { Field } from './components/Field.jsx';
import { Tabs } from './components/Tabs.jsx';

const emptyJob = { title: '', description: '', category: '', work_mode: 'online', duration: 'short', location: '', budget_type: 'fixed', budget_min: '', budget_max: '', currency: 'USD', deadline: '', skills: '' };
const labels = { online: 'Онлайн', offline: 'Офлайн', hybrid: 'Гибрид', one_day: 'Один день', short: 'До месяца', long: 'Долгосрочно', fixed: 'Фиксированная', hourly: 'Почасовая', negotiable: 'Договорная', open: 'Открыто', in_progress: 'В работе', closed: 'Закрыто', sent: 'Отправлен', accepted: 'Принят', declined: 'Отклонён' };
const budget = (job) => job.budget_type === 'negotiable' ? 'Договорная цена' : `${job.budget_min || 0}${job.budget_max ? `–${job.budget_max}` : '+'} ${job.currency}`;

export default function App() {
  const [tab, setTab] = useState('discover');
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState('login');
  const [auth, setAuth] = useState({ name: '', email: '', password: '' });
  const [jobs, setJobs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({ q: '', work_mode: '', duration: '' });
  const [searchQuery, setSearchQuery] = useState('');
  const [job, setJob] = useState(emptyJob);
  const [application, setApplication] = useState({ message: '', proposed_rate: '', estimated_time: '' });
  const [dashboard, setDashboard] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const requestSequence = useRef(0);
  const run = async (action, success) => { setLoading(true); setError(''); try { const result = await action(); if (success) setMessage(success); return result; } catch (e) { if (e.name !== 'AbortError') setError(e.message); } finally { setLoading(false); } };
  const loadDashboard = async () => { if (user) { const data = await run(api.dashboard); if (data) setDashboard(data); } };

  useEffect(() => { const timer = setTimeout(() => setSearchQuery(filters.q), 350); return () => clearTimeout(timer); }, [filters.q]);
  useEffect(() => {
    const controller = new AbortController();
    const sequence = ++requestSequence.current;
    run(() => api.jobs({ ...filters, q: searchQuery }, controller.signal)).then((data) => {
      if (data && sequence === requestSequence.current) {
        setJobs(data);
        setSelected((old) => data.find((item) => item.id === old?.id) || data[0] || null);
      }
    });
    return () => controller.abort();
  }, [searchQuery, filters.work_mode, filters.duration]);
  useEffect(() => {
    const clearUser = () => { setUser(null); setDashboard(null); setTab('discover'); };
    window.addEventListener('who-could:session-cleared', clearUser);
    if (session.getToken()) run(api.me).then((data) => data && setUser(data));
    return () => window.removeEventListener('who-could:session-cleared', clearUser);
  }, []);
  useEffect(() => { if (tab === 'dashboard') loadDashboard(); }, [tab, user]);

  const submitAuth = async (event) => { event.preventDefault(); const result = await run(() => authMode === 'login' ? api.login({ email: auth.email, password: auth.password }) : api.register(auth), 'Добро пожаловать!'); if (result) { session.setToken(result.token); setUser(result.user); } };
  const logout = () => session.clear();
  const submitJob = async (event) => { event.preventDefault(); const payload = { ...job, budget_min: job.budget_min ? Number(job.budget_min) : null, budget_max: job.budget_max ? Number(job.budget_max) : null, location: job.location || null, deadline: job.deadline || null, skills: job.skills || null }; const result = await run(() => api.createJob(payload), 'Задание опубликовано'); if (result) { setJob(emptyJob); setSelected(result); setJobs((items) => [result, ...items]); setTab('discover'); } };
  const submitApplication = async (event) => { event.preventDefault(); const result = await run(() => api.apply(selected.id, { ...application, proposed_rate: application.proposed_rate ? Number(application.proposed_rate) : null, estimated_time: application.estimated_time || null }), 'Отклик отправлен'); if (result) setApplication({ message: '', proposed_rate: '', estimated_time: '' }); };
  const changeApplication = async (id, status) => { if (await run(() => api.setApplicationStatus(id, status), 'Статус отклика обновлён')) loadDashboard(); };
  const changeJob = async (id, status) => { if (await run(() => api.setJobStatus(id, status), 'Статус задания обновлён')) loadDashboard(); };
  const isAdmin = Boolean(user?.roles?.some((role) => role.name === 'admin'));
  const isMaster = Boolean(isAdmin || user?.roles?.some((role) => role.name === 'master'));
  const navigation = [
    ['discover','Найти работу'],
    ['publish','Создать задание'],
    ['intake','Приём устройства'],
    ...(isMaster ? [['master','Мастер']] : []),
    ...(user ? [['pickup','Выдача клиенту']] : []),
    ['warehouse','Склад'],
    ['dashboard','Мои дела'],
    ...(isAdmin ? [['admin','Администрирование']] : []),
  ];

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">W</span><div><h1>Who could</h1><p>Люди помогают людям</p></div></div>
      <div className="hero-copy"><Badge tone="green">MVP · локальный запуск</Badge><h2>Найдите того, кто сможет.</h2><p>Один аккаунт для публикации своих задач и выполнения чужих.</p></div>
      <div className="metric-grid"><div><strong>{jobs.length}</strong><span>открытых задач</span></div><div><strong>2</strong><span>роли в одном</span></div></div>
      <div className="auth-panel">{user ? <div className="user-card"><span>Вы вошли как</span><strong>{user.name}</strong><small>{user.email}</small>{user.roles?.length > 0 && <small>Роли: {user.roles.map((role) => role.name).join(', ')}</small>}<Button variant="ghost" onClick={logout}>Выйти</Button></div> : <><Tabs items={[['login', 'Вход'], ['register', 'Регистрация']]} active={authMode} onChange={setAuthMode}/><form onSubmit={submitAuth}>{authMode === 'register' && <Field label="Имя"><input value={auth.name} onChange={(e) => setAuth({...auth, name:e.target.value})} required /></Field>}<Field label="Email"><input type="email" value={auth.email} onChange={(e) => setAuth({...auth, email:e.target.value})} required /></Field><Field label="Пароль"><input type="password" minLength="8" value={auth.password} onChange={(e) => setAuth({...auth, password:e.target.value})} required /></Field><Button disabled={loading}>{authMode === 'login' ? 'Войти' : 'Создать аккаунт'}</Button></form></>}</div>
    </aside>
    <section className="workspace">
      <header className="topbar"><Tabs items={navigation} active={tab} onChange={setTab}/><div className="status-line">{message && <span className="notice">{message}</span>}{error && <span className="error">{error}</span>}</div></header>
      {tab === 'discover' && <div className="discover-layout"><section className="job-list-pane"><div className="filters"><input placeholder="Поиск по задачам и навыкам" value={filters.q} onChange={(e)=>setFilters({...filters,q:e.target.value})}/><select value={filters.work_mode} onChange={(e)=>setFilters({...filters,work_mode:e.target.value})}><option value="">Любой формат</option><option value="online">Онлайн</option><option value="offline">Офлайн</option><option value="hybrid">Гибрид</option></select><select value={filters.duration} onChange={(e)=>setFilters({...filters,duration:e.target.value})}><option value="">Любой срок</option><option value="one_day">Один день</option><option value="short">До месяца</option><option value="long">Долгосрочно</option></select></div><div className="job-list">{jobs.map((item)=><button key={item.id} className={`job-row ${selected?.id===item.id?'selected':''}`} onClick={()=>setSelected(item)}><span><strong>{item.title}</strong><small>{item.category} · {item.owner_name}</small></span><span className="job-price">{budget(item)}</span></button>)}{!jobs.length && <p className="empty">Заданий пока нет. Создайте первое.</p>}</div></section><section className="details-pane">{selected ? <><div className="details-head"><div><p>{selected.location || 'Удалённо'}</p><h2>{selected.title}</h2><small>Заказчик: {selected.owner_name}</small></div><strong>{budget(selected)}</strong></div><div className="badge-row"><Badge tone="blue">{labels[selected.work_mode]}</Badge><Badge tone="green">{labels[selected.duration]}</Badge><Badge>{selected.applications_count} откликов</Badge></div><p className="description">{selected.description}</p>{selected.skills && <p><strong>Навыки:</strong> {selected.skills}</p>}<form className="apply-box" onSubmit={submitApplication}><h3>Откликнуться как исполнитель</h3>{!user && <p className="empty">Сначала войдите в аккаунт.</p>}<Field label="Сообщение"><textarea disabled={!user || selected.owner_id===user?.id} minLength="12" value={application.message} onChange={(e)=>setApplication({...application,message:e.target.value})} required /></Field><div className="two-columns"><Field label="Ваша ставка"><input disabled={!user} type="number" min="0" value={application.proposed_rate} onChange={(e)=>setApplication({...application,proposed_rate:e.target.value})}/></Field><Field label="Срок"><input disabled={!user} value={application.estimated_time} onChange={(e)=>setApplication({...application,estimated_time:e.target.value})}/></Field></div><Button disabled={!user || selected.owner_id===user?.id || loading}>Отправить отклик</Button></form></> : <p className="empty">Выберите задание.</p>}</section></div>}
      {tab === 'publish' && <form className="publish-form" onSubmit={submitJob}><div><p className="eyebrow">Новая возможность</p><h2>Опубликовать задание</h2></div>{!user && <p className="empty">Войдите, чтобы публиковать задания.</p>}<div className="two-columns"><Field label="Название"><input disabled={!user} minLength="6" value={job.title} onChange={(e)=>setJob({...job,title:e.target.value})} required/></Field><Field label="Категория"><input disabled={!user} value={job.category} onChange={(e)=>setJob({...job,category:e.target.value})} required/></Field></div><Field label="Описание"><textarea disabled={!user} minLength="20" value={job.description} onChange={(e)=>setJob({...job,description:e.target.value})} required/></Field><div className="four-columns"><Field label="Формат"><select value={job.work_mode} onChange={(e)=>setJob({...job,work_mode:e.target.value})}><option value="online">Онлайн</option><option value="offline">Офлайн</option><option value="hybrid">Гибрид</option></select></Field><Field label="Срок"><select value={job.duration} onChange={(e)=>setJob({...job,duration:e.target.value})}><option value="one_day">Один день</option><option value="short">До месяца</option><option value="long">Долгосрочно</option></select></Field><Field label="Оплата"><select value={job.budget_type} onChange={(e)=>setJob({...job,budget_type:e.target.value})}><option value="fixed">Фиксированная</option><option value="hourly">Почасовая</option><option value="negotiable">Договорная</option></select></Field><Field label="Валюта"><input maxLength="3" value={job.currency} onChange={(e)=>setJob({...job,currency:e.target.value.toUpperCase()})}/></Field></div><div className="four-columns"><Field label="Бюджет от"><input type="number" min="0" value={job.budget_min} onChange={(e)=>setJob({...job,budget_min:e.target.value})}/></Field><Field label="Бюджет до"><input type="number" min="0" value={job.budget_max} onChange={(e)=>setJob({...job,budget_max:e.target.value})}/></Field><Field label="Место"><input value={job.location} onChange={(e)=>setJob({...job,location:e.target.value})}/></Field><Field label="Дедлайн"><input type="date" value={job.deadline} onChange={(e)=>setJob({...job,deadline:e.target.value})}/></Field></div><Field label="Навыки"><input value={job.skills} onChange={(e)=>setJob({...job,skills:e.target.value})}/></Field><Button disabled={!user || loading}>Опубликовать</Button></form>}
      {tab === 'intake' && <DeviceIntake user={user}/>} 
      {tab === 'master' && isMaster && <MasterBoard user={user}/>} 
      {tab === 'pickup' && <CustomerPickup user={user}/>} 
      {tab === 'warehouse' && <Warehouse user={user}/>} 
      {tab === 'dashboard' && <Dashboard data={dashboard} user={user} onApplication={changeApplication} onJob={changeJob}/>}
      {tab === 'admin' && isAdmin && <AdminPanel currentUser={user} onCurrentUser={setUser}/>} 
    </section>
  </main>;
}

function Dashboard({ data, user, onApplication, onJob }) {
  if (!user) return <section className="publish-form"><h2>Мои дела</h2><p className="empty">Войдите, чтобы управлять заданиями и откликами.</p></section>;
  if (!data) return <p className="empty">Загрузка…</p>;
  return <div className="dashboard-grid"><section className="manage-card"><h2>Мои задания <span>{data.owned_jobs.length}</span></h2>{data.owned_jobs.map(job=><article key={job.id} className="manage-row"><div><strong>{job.title}</strong><small>{labels[job.status]} · {job.applications_count} откликов</small></div><select value={job.status} onChange={(e)=>onJob(job.id,e.target.value)}><option value="open">Открыто</option><option value="in_progress">В работе</option><option value="closed">Закрыто</option></select></article>)}</section><section className="manage-card"><h2>Входящие отклики <span>{data.received_applications.length}</span></h2>{data.received_applications.map(item=><article key={item.id} className="manage-row"><div><strong>{item.applicant_name} → {item.job_title}</strong><small>{item.message} · {item.proposed_rate || 'без ставки'}</small></div>{item.status==='sent'?<div className="action-row"><Button onClick={()=>onApplication(item.id,'accepted')}>Принять</Button><Button variant="secondary" onClick={()=>onApplication(item.id,'declined')}>Отклонить</Button></div>:<Badge>{labels[item.status]}</Badge>}</article>)}</section><section className="manage-card"><h2>Мои отклики <span>{data.sent_applications.length}</span></h2>{data.sent_applications.map(item=><article key={item.id} className="manage-row"><div><strong>{item.job_title}</strong><small>{item.message}</small></div><Badge tone={item.status==='accepted'?'green':'blue'}>{labels[item.status]}</Badge></article>)}</section></div>;
}
