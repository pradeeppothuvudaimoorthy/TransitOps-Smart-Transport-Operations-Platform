"use client";

import { useMemo, useState, useEffect } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db } from "./firebase";

type Page = "Dashboard" | "Vehicles" | "Drivers" | "Trip Dispatch" | "Maintenance" | "Fuel & Expenses" | "Reports" | "Settings";

const nav: { label: Page; icon: string }[] = [
  { label: "Dashboard", icon: "▦" }, { label: "Vehicles", icon: "▰" },
  { label: "Drivers", icon: "♙" }, { label: "Trip Dispatch", icon: "↗" },
  { label: "Maintenance", icon: "◇" }, { label: "Fuel & Expenses", icon: "◫" },
  { label: "Reports", icon: "⌁" }, { label: "Settings", icon: "⚙" },
];

const statusData = [
  ["On trip", 42, "#4f46e5"], ["Available", 31, "#10b981"],
  ["Maintenance", 15, "#f59e0b"], ["Inactive", 12, "#cbd5e1"],
] as const;

const trips = [
  ["TRP-2048", "Bengaluru → Chennai", "TN 02 AB 4581", "Arjun Kumar", "In transit", "6h 20m"],
  ["TRP-2047", "Hyderabad → Pune", "KA 51 MJ 9034", "Naveen Rao", "Loading", "8h 45m"],
  ["TRP-2046", "Mumbai → Surat", "MH 04 JK 1128", "Rakesh Patil", "Delivered", "—"],
  ["TRP-2045", "Kochi → Coimbatore", "KL 07 CQ 6342", "Faisal Ali", "Delayed", "2h 10m"],
];

const fleet = [
  ["TN 02 AB 4581", "Tata Prima 5530.S", "Heavy Truck", "On trip", "92%", "Chennai Hub"],
  ["KA 51 MJ 9034", "Ashok Leyland 4825", "Container", "Available", "88%", "Bengaluru Hub"],
  ["MH 04 JK 1128", "BharatBenz 4228R", "Heavy Truck", "Maintenance", "64%", "Mumbai Hub"],
  ["KL 07 CQ 6342", "Eicher Pro 3015", "Medium Truck", "On trip", "86%", "Kochi Hub"],
  ["TS 09 HR 2217", "Tata Ultra T.16", "Medium Truck", "Available", "95%", "Hyderabad Hub"],
];

const drivers = [
  ["AK", "Arjun Kumar", "12 years", "94", "On trip", "DL-04201801452"],
  ["NR", "Naveen Rao", "8 years", "91", "Available", "KA-05201900842"],
  ["RP", "Rakesh Patil", "10 years", "88", "Resting", "MH-14201601967"],
  ["FA", "Faisal Ali", "7 years", "96", "On trip", "KL-07202000381"],
];

function Status({ children }: { children: string }) {
  const key = children.toLowerCase().replace(" ", "-");
  return <span className={`status ${key}`}><i />{children}</span>;
}

function Sparkline({ bars, green = false }: { bars: number[]; green?: boolean }) {
  return <div className={`spark ${green ? "green" : ""}`}>{bars.map((h, i) => <i key={i} style={{ height: `${h}%` }} />)}</div>;
}

function Header({ page, setMobileOpen }: { page: Page; setMobileOpen: (v: boolean) => void }) {
  return <header className="topbar">
    <button className="mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation">☰</button>
    <div className="search"><span>⌕</span><input aria-label="Global search" placeholder="Search vehicles, drivers, trips..."/><kbd>⌘ K</kbd></div>
    <div className="top-actions"><button className="icon-button" aria-label="Help">?</button><button className="icon-button notification" aria-label="Notifications">♢<b>3</b></button><div className="divider"/><div className="profile"><div className="avatar">PK</div><div><strong>Pradeep Kumar</strong><small>Fleet Administrator</small></div><span>⌄</span></div></div>
  </header>;
}

function Sidebar({ active, setActive, open, close }: { active: Page; setActive: (p: Page) => void; open: boolean; close: () => void }) {
  return <><aside className={`sidebar ${open ? "open" : ""}`}>
    <div className="brand"><div className="brandmark"><i/><i/><i/></div><div><strong>Transit<span>Ops</span></strong><small>Smart Transport</small></div><button onClick={close} aria-label="Close navigation">×</button></div>
    <div className="workspace"><div className="company">NL</div><div><strong>Nexora Logistics</strong><small>Enterprise workspace</small></div><span>⌄</span></div>
    <p className="nav-label">OPERATIONS</p>
    <nav>{nav.slice(0, 6).map(n => <button key={n.label} className={active === n.label ? "active" : ""} onClick={() => { setActive(n.label); close(); }}><span>{n.icon}</span>{n.label}{n.label === "Trip Dispatch" && <b>8</b>}</button>)}</nav>
    <p className="nav-label">INSIGHTS & ADMIN</p>
    <nav>{nav.slice(6).map(n => <button key={n.label} className={active === n.label ? "active" : ""} onClick={() => { setActive(n.label); close(); }}><span>{n.icon}</span>{n.label}</button>)}</nav>
    <div className="assistant-card"><span className="ai-icon">✦</span><strong>AI Fleet Assistant</strong><p>Ask about fleet health, costs or upcoming risks.</p><button onClick={() => alert("AI Fleet Assistant opened")}>Ask Transit AI <span>→</span></button></div>
    <div className="sidebar-foot"><span>?</span><div><strong>Need help?</strong><small>View documentation</small></div><span>↗</span></div>
  </aside>{open && <button className="overlay" aria-label="Close navigation" onClick={close}/>}</>;
}

function PageIntro({ title, desc, action, onAction }: { title: string; desc: string; action?: string; onAction?: () => void }) {
  return <div className="page-intro"><div><div className="breadcrumb">TransitOps <span>/</span> {title}</div><h1>{title}</h1><p>{desc}</p></div>{action && <button className="primary" onClick={onAction}><span>＋</span>{action}</button>}</div>;
}

const DEFAULT_KPIS = {
  active_vehicles: 54,
  available_vehicles: 40,
  vehicles_in_maintenance: 15,
  drivers_available: 96,
  trips_today: 12,
  active_trips: 62,
  pending_trips: 8,
  total_fuel_cost: 1840000,
  total_maintenance_cost: 1300000,
  total_revenue: 4820000,
  fleet_health_score: 89,
  fleet_utilization: 82.4
};

function formatLakhs(val: number) {
  if (val >= 100000) {
    return `₹ ${(val / 100000).toFixed(1)}L`;
  }
  return `₹ ${val.toLocaleString("en-IN")}`;
}

function Dashboard({ openDispatch }: { openDispatch: () => void }) {
  const [range, setRange] = useState("This month");
  const [kpi, setKpi] = useState(DEFAULT_KPIS);
  const [synced, setSynced] = useState(false);

  useEffect(() => {
    const unsub = onSnapshot(doc(db, "kpi_snapshots", "latest"), (docSnap) => {
      if (docSnap.exists()) {
        const data = docSnap.data();
        setKpi({
          active_vehicles: typeof data.active_vehicles === "number" ? data.active_vehicles : DEFAULT_KPIS.active_vehicles,
          available_vehicles: typeof data.available_vehicles === "number" ? data.available_vehicles : DEFAULT_KPIS.available_vehicles,
          vehicles_in_maintenance: typeof data.vehicles_in_maintenance === "number" ? data.vehicles_in_maintenance : DEFAULT_KPIS.vehicles_in_maintenance,
          drivers_available: typeof data.drivers_available === "number" ? data.drivers_available : DEFAULT_KPIS.drivers_available,
          trips_today: typeof data.trips_today === "number" ? data.trips_today : DEFAULT_KPIS.trips_today,
          active_trips: typeof data.active_trips === "number" ? data.active_trips : DEFAULT_KPIS.active_trips,
          pending_trips: typeof data.pending_trips === "number" ? data.pending_trips : DEFAULT_KPIS.pending_trips,
          total_fuel_cost: typeof data.total_fuel_cost === "number" ? data.total_fuel_cost : DEFAULT_KPIS.total_fuel_cost,
          total_maintenance_cost: typeof data.total_maintenance_cost === "number" ? data.total_maintenance_cost : DEFAULT_KPIS.total_maintenance_cost,
          total_revenue: typeof data.total_revenue === "number" ? data.total_revenue : DEFAULT_KPIS.total_revenue,
          fleet_health_score: typeof data.fleet_health_score === "number" ? data.fleet_health_score : DEFAULT_KPIS.fleet_health_score,
          fleet_utilization: typeof data.fleet_utilization === "number" ? data.fleet_utilization : DEFAULT_KPIS.fleet_utilization,
        });
        setSynced(true);
      }
    }, (err) => {
      console.warn("Firestore snapshot listener failed, using default mock data", err);
    });
    return () => unsub();
  }, []);

  const totalVehicles = kpi.active_vehicles + kpi.available_vehicles + kpi.vehicles_in_maintenance + 12;

  const currentStatusData = [
    ["On trip", Math.round((kpi.active_vehicles / totalVehicles) * 100), "#4f46e5"],
    ["Available", Math.round((kpi.available_vehicles / totalVehicles) * 100), "#10b981"],
    ["Maintenance", Math.round((kpi.vehicles_in_maintenance / totalVehicles) * 100), "#f59e0b"],
    ["Inactive", Math.round((12 / totalVehicles) * 100), "#cbd5e1"],
  ] as const;

  return <>
    <PageIntro title="Operations Overview" desc="Here’s what’s happening across your fleet today." action="New dispatch" onAction={openDispatch}/>
    <div className="notice">
      <span>✦</span>
      <div>
        <strong>{synced ? "Connected to Odoo via Firebase (Live)" : "Good morning, Pradeep — your fleet is running efficiently."}</strong>
        <p>{synced ? "Real-time synchronization active. Last update pulled live from Odoo." : "AI detected a 6.4% improvement in fleet utilization compared to last month."}</p>
      </div>
      <button>{synced ? "Connected" : "View insight →"}</button>
      <button className="close-notice">×</button>
    </div>
    <section className="kpi-grid">
      <article><div className="kpi-head"><span className="kpi-icon indigo">▰</span><em className="up">↗ 3.2%</em></div><strong>{totalVehicles}</strong><p>Total vehicles</p><div className="mini-row"><span><i className="dot green"/>{kpi.available_vehicles} available</span><span><i className="dot purple"/>{kpi.active_vehicles} on trip</span></div></article>
      <article><div className="kpi-head"><span className="kpi-icon emerald">↗</span><em className="up">↗ 8.1%</em></div><strong>{kpi.active_trips}</strong><p>Active trips</p><div className="mini-row"><span>{kpi.pending_trips} pending</span><span>94% on-time</span></div></article>
      <article><div className="kpi-head"><span className="kpi-icon amber">♙</span><em>– 1.4%</em></div><strong>{kpi.drivers_available}</strong><p>Drivers available</p><div className="mini-row"><span>18 on duty</span><span>6 on leave</span></div></article>
      <article className="health-card"><div className="kpi-head"><span className="kpi-icon blue">♡</span><em className="up">↗ 2.8%</em></div><strong>{kpi.fleet_health_score}<span>/100</span></strong><p>Fleet health score</p><div className="progress"><i style={{width:`${kpi.fleet_health_score}%`}}/></div></article>
    </section>
    <section className="dashboard-grid">
      <article className="panel revenue-panel"><div className="panel-head"><div><h2>Financial performance</h2><p>Revenue and operational expenses</p></div><select value={range} onChange={e => setRange(e.target.value)}><option>This month</option><option>Last 3 months</option><option>This year</option></select></div>
        <div className="finance-totals">
          <div><span>Revenue</span><strong>{formatLakhs(kpi.total_revenue)}</strong><em className="up">↗ 12.5%</em></div>
          <div><span>Operational cost</span><strong>{formatLakhs(kpi.total_fuel_cost + kpi.total_maintenance_cost)}</strong><em className="down">↘ 3.2%</em></div>
          <div><span>Net margin</span><strong>{formatLakhs(kpi.total_revenue - (kpi.total_fuel_cost + kpi.total_maintenance_cost))}</strong><em>34.9%</em></div>
        </div>
        <div className="chart"><div className="y-axis"><span>12L</span><span>9L</span><span>6L</span><span>3L</span><span>0</span></div><div className="plot"><i/><i/><i/><i/><svg viewBox="0 0 700 170" preserveAspectRatio="none"><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4f46e5" stopOpacity=".22"/><stop offset="100%" stopColor="#4f46e5" stopOpacity="0"/></linearGradient></defs><path className="area" d="M0 138 C60 126 85 104 145 112 S230 76 290 88 S390 54 440 72 S525 30 570 46 S650 20 700 18 L700 170 L0 170Z"/><path className="line" d="M0 138 C60 126 85 104 145 112 S230 76 290 88 S390 54 440 72 S525 30 570 46 S650 20 700 18"/><path className="cost-line" d="M0 150 C60 142 100 133 145 136 S230 117 290 124 S370 100 440 110 S510 89 570 98 S650 70 700 79"/></svg><div className="x-axis"><span>Week 1</span><span>Week 2</span><span>Week 3</span><span>Week 4</span></div></div></div>
      </article>
      <article className="panel vehicle-panel"><div className="panel-head"><div><h2>Vehicle status</h2><p>Live fleet distribution</p></div><button className="more">•••</button></div><div className="donut-wrap"><div className="donut"><div><strong>{totalVehicles}</strong><span>vehicles</span></div></div><div className="legend">{currentStatusData.map(([n,v,c])=><div key={n}><span><i style={{background:c}}/>{n}</span><strong>{v}%</strong></div>)}</div></div><button className="text-button">View all vehicles <span>→</span></button></article>
      <article className="panel trips-panel"><div className="panel-head"><div><h2>Active trips</h2><p>Live dispatch and delivery status</p></div><button className="text-button">View all <span>→</span></button></div><div className="table-wrap"><table><thead><tr><th>TRIP ID</th><th>ROUTE</th><th>VEHICLE</th><th>DRIVER</th><th>STATUS</th><th>ETA</th><th/></tr></thead><tbody>{trips.map(t=><tr key={t[0]}><td><b className="trip-id">{t[0]}</b></td><td><strong>{t[1]}</strong><small>General cargo · 18.4 t</small></td><td>{t[2]}</td><td><span className="driver-cell"><i>{t[3].split(" ").map(x=>x[0]).join("")}</i>{t[3]}</span></td><td><Status>{t[4]}</Status></td><td><strong>{t[5]}</strong></td><td><button className="more">•••</button></td></tr>)}</tbody></table></div></article>
      <article className="panel alerts-panel"><div className="panel-head"><div><h2>Alerts & attention</h2><p>Items requiring action</p></div><span className="alert-count">5 new</span></div><div className="alert-list"><div><span className="alert-icon red">!</span><p><strong>License expiring soon</strong><small>2 drivers within 14 days</small></p><time>Today</time></div><div><span className="alert-icon amber">◇</span><p><strong>Maintenance overdue</strong><small>MH 04 JK 1128 · 3 days</small></p><time>2h</time></div><div><span className="alert-icon blue">◫</span><p><strong>Fuel anomaly detected</strong><small>18% above average consumption</small></p><time>4h</time></div></div><button className="text-button full">Open alert center <span>→</span></button></article>
      <article className="panel efficiency-panel"><div className="panel-head"><div><h2>Fleet utilization</h2><p>Average across all vehicle types</p></div><span className="score">{kpi.fleet_utilization}%</span></div><div className="util-row"><span>Heavy trucks</span><div><i style={{width:`${Math.min(100, kpi.fleet_utilization + 5)}%`}}/></div><strong>{Math.min(100, Math.round(kpi.fleet_utilization + 5))}%</strong></div><div className="util-row"><span>Medium trucks</span><div><i style={{width:`${Math.min(100, kpi.fleet_utilization - 3)}%`}}/></div><strong>{Math.min(100, Math.round(kpi.fleet_utilization - 3))}%</strong></div><div className="util-row"><span>Light commercial</span><div><i style={{width:`${Math.min(100, kpi.fleet_utilization - 8)}%`}}/></div><strong>{Math.min(100, Math.round(kpi.fleet_utilization - 8))}%</strong></div><div className="util-foot"><span>Target: 85%</span><span className="up">↗ 6.4% vs last month</span></div></article>
    </section>
  </>;
}

function Vehicles() {
  const [query, setQuery] = useState("");
  const filtered = fleet.filter(v => v.join(" ").toLowerCase().includes(query.toLowerCase()));
  return <><PageIntro title="Vehicle Registry" desc="Manage your fleet, documents and vehicle health." action="Add vehicle" onAction={()=>alert("Add vehicle form opened")}/><div className="summary-strip"><div><span className="kpi-icon indigo">▰</span><p><strong>128</strong><small>Total fleet</small></p></div><div><span className="kpi-icon emerald">✓</span><p><strong>40</strong><small>Available</small></p></div><div><span className="kpi-icon amber">◇</span><p><strong>19</strong><small>Service due</small></p></div><div><span className="kpi-icon blue">♡</span><p><strong>89%</strong><small>Average health</small></p></div></div><section className="panel registry"><div className="toolbar"><div className="search table-search"><span>⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search registration, model or hub..."/></div><button className="filter">☷ Filters <b>2</b></button><button className="filter">↧ Export</button><div className="view-toggle"><button className="active">☷</button><button>▦</button></div></div><div className="table-wrap"><table><thead><tr><th>VEHICLE</th><th>TYPE</th><th>STATUS</th><th>HEALTH</th><th>LOCATION</th><th>LAST SERVICE</th><th/></tr></thead><tbody>{filtered.map((v,i)=><tr key={v[0]}><td><div className="vehicle-name"><span className="truck-icon">▰</span><p><strong>{v[0]}</strong><small>{v[1]}</small></p></div></td><td>{v[2]}</td><td><Status>{v[3]}</Status></td><td><div className="health"><span>{v[4]}</span><div><i style={{width:v[4], background:i===2?"#f59e0b":"#10b981"}}/></div></div></td><td>{v[5]}</td><td>{i===2?"06 Jul 2026":"28 Jun 2026"}</td><td><button className="more">•••</button></td></tr>)}</tbody></table></div><div className="pagination"><span>Showing 1–{filtered.length} of 128 vehicles</span><div><button>‹</button><button className="active">1</button><button>2</button><button>3</button><button>…</button><button>13</button><button>›</button></div></div></section></>;
}

function Drivers() {
  return <><PageIntro title="Driver Management" desc="Monitor driver availability, compliance and safety." action="Add driver" onAction={()=>alert("Add driver form opened")}/><div className="driver-grid">{drivers.map((d,i)=><article className="driver-card" key={d[1]}><div className="driver-top"><div className={`driver-avatar a${i}`}>{d[0]}</div><Status>{d[4]}</Status><button className="more">•••</button></div><h3>{d[1]}</h3><p>{d[5]}</p><div className="safety"><div><span>Safety score</span><strong>{d[3]}<small>/100</small></strong></div><div className="ring" style={{"--score":`${d[3]}%`} as React.CSSProperties}>{d[3]}</div></div><div className="driver-stats"><div><span>Experience</span><strong>{d[2]}</strong></div><div><span>Trips</span><strong>{124-i*17}</strong></div><div><span>On-time</span><strong>{96-i}%</strong></div></div><div className="license"><span>License validity</span><strong className={i===2?"warn":""}>{i===2?"Expires in 12 days":"Valid until May 2028"}</strong></div><button className="secondary full">View driver profile</button></article>)}</div></>;
}

function Dispatch() {
  const [step,setStep]=useState(1); const [vehicle,setVehicle]=useState(""); const [driver,setDriver]=useState(""); const [cargo,setCargo]=useState("");
  const valid = step===1?!!vehicle:step===2?!!driver:step===3?!!cargo:true;
  return <><PageIntro title="Create Dispatch" desc="Assign the right vehicle and driver with real-time operational validation."/><section className="dispatch-layout"><article className="panel wizard"><div className="steps">{["Vehicle","Driver","Cargo","Review","Confirm"].map((s,i)=><div key={s} className={step===i+1?"active":step>i+1?"done":""}><span>{step>i+1?"✓":i+1}</span><small>{s}</small>{i<4&&<i/>}</div>)}</div><div className="wizard-body">{step===1&&<><h2>Select a vehicle</h2><p>Only available and cargo-compatible vehicles are shown.</p><div className="option-list">{fleet.filter(v=>v[3]==="Available").map(v=><button key={v[0]} className={vehicle===v[0]?"selected":""} onClick={()=>setVehicle(v[0])}><span className="truck-icon">▰</span><div><strong>{v[0]}</strong><small>{v[1]} · {v[2]}</small></div><em>{v[4]} health</em><i>{vehicle===v[0]?"✓":""}</i></button>)}</div></>}{step===2&&<><h2>Choose a driver</h2><p>Recommended based on safety score, availability and route experience.</p><div className="option-list">{drivers.filter(d=>d[4]==="Available").map(d=><button key={d[1]} className={driver===d[1]?"selected":""} onClick={()=>setDriver(d[1])}><span className="driver-avatar small">{d[0]}</span><div><strong>{d[1]}</strong><small>{d[2]} · Safety score {d[3]}</small></div><em className="recommended">✦ AI recommended</em><i>{driver===d[1]?"✓":""}</i></button>)}</div></>}{step===3&&<><h2>Enter cargo details</h2><p>Add shipment information for safety and compliance checks.</p><div className="form-grid"><label>Cargo description<input value={cargo} onChange={e=>setCargo(e.target.value)} placeholder="e.g. Industrial equipment"/></label><label>Weight (tonnes)<input type="number" placeholder="18.4"/></label><label>Origin<input placeholder="Bengaluru Hub"/></label><label>Destination<input placeholder="Chennai Hub"/></label></div></>}{step===4&&<><h2>Review dispatch</h2><p>Confirm the assignment before dispatching.</p><div className="review-box"><div><span>Vehicle</span><strong>{vehicle}</strong></div><div><span>Driver</span><strong>{driver}</strong></div><div><span>Cargo</span><strong>{cargo}</strong></div><div><span>Validation</span><strong className="up">✓ All checks passed</strong></div></div></>}{step===5&&<div className="success-state"><span>✓</span><h2>Dispatch created successfully</h2><p>Trip TRP-2049 is ready and the driver has been notified.</p><button className="primary" onClick={()=>{setStep(1);setVehicle("");setDriver("");setCargo("")}}>Create another dispatch</button></div>}</div>{step<5&&<div className="wizard-foot"><button className="secondary" disabled={step===1} onClick={()=>setStep(step-1)}>← Back</button><span>{!valid&&"Complete this step to continue"}</span><button className="primary" disabled={!valid} onClick={()=>setStep(step+1)}>{step===4?"Confirm dispatch":"Continue →"}</button></div>}</article><aside className="dispatch-side"><div className="ai-recommend"><span>✦</span><h3>Smart assignment</h3><p>Transit AI checks vehicle capacity, maintenance risk, driver hours and route familiarity.</p><ul><li>Capacity compatibility</li><li>Driver compliance</li><li>Maintenance readiness</li><li>Route experience</li></ul></div><div className="panel validation"><h3>Live validation</h3><div><span className={vehicle?"ok":""}>{vehicle?"✓":"○"}</span> Vehicle selected</div><div><span className={driver?"ok":""}>{driver?"✓":"○"}</span> Driver assigned</div><div><span className={cargo?"ok":""}>{cargo?"✓":"○"}</span> Cargo recorded</div></div></aside></section></>;
}

function Maintenance() { return <><PageIntro title="Maintenance" desc="Plan preventive service and keep every vehicle road-ready." action="Schedule service" onAction={()=>alert("Service scheduler opened")}/><div className="maintenance-grid"><article className="panel calendar"><div className="panel-head"><div><h2>July 2026</h2><p>Maintenance calendar</p></div><div><button className="secondary">‹</button><button className="secondary">Today</button><button className="secondary">›</button></div></div><div className="week"><b>MON</b><b>TUE</b><b>WED</b><b>THU</b><b>FRI</b><b>SAT</b><b>SUN</b>{Array.from({length:35},(_,i)=><div key={i} className={(i===10||i===17||i===24)?"has-event":""}><span>{i<2?29+i:i-1}</span>{i===10&&<em className="event amber-event">MH 04 JK · Service</em>}{i===17&&<em className="event blue-event">KA 51 MJ · Inspection</em>}{i===24&&<em className="event green-event">TN 02 AB · Oil change</em>}</div>)}</div></article><aside className="panel service-list"><div className="panel-head"><div><h2>Upcoming service</h2><p>Next 14 days</p></div></div>{fleet.slice(0,4).map((v,i)=><div className="service-item" key={v[0]}><span className={`date-box d${i}`}><strong>{8+i*3}</strong><small>JUL</small></span><p><strong>{v[0]}</strong><small>{["Brake inspection","Periodic service","Engine diagnostics","Oil & filter change"][i]}</small></p><em>{i===0?"Overdue":"In "+(i*3+2)+" days"}</em></div>)}</aside><article className="panel cost-card"><div className="panel-head"><div><h2>Maintenance cost trend</h2><p>Last 6 months</p></div><strong>₹6.8L <small className="down">↘ 4.2%</small></strong></div><Sparkline bars={[42,55,48,70,62,82,73,66,58,64,51,57]} /></article><article className="panel timeline-card"><div className="panel-head"><div><h2>Recent maintenance</h2><p>Completed work orders</p></div><button className="text-button">View history →</button></div><div className="timeline"><div><i/><p><strong>Full service completed</strong><small>TN 02 AB 4581 · Nexora Workshop</small></p><time>06 Jul</time></div><div><i/><p><strong>Tyres replaced</strong><small>KL 07 CQ 6342 · ₹48,500</small></p><time>02 Jul</time></div><div><i/><p><strong>Brake inspection passed</strong><small>TS 09 HR 2217 · No issues found</small></p><time>29 Jun</time></div></div></article></div></> }

function Expenses() { return <><PageIntro title="Fuel & Expenses" desc="Track operating costs, efficiency and spending anomalies." action="Add expense" onAction={()=>alert("Expense form opened")}/><section className="kpi-grid compact"><article><p>Fuel spend</p><strong>₹12.6L</strong><em className="down">↘ 2.4% this month</em><Sparkline green bars={[38,45,52,47,63,58,72,68,79]}/></article><article><p>Avg. efficiency</p><strong>4.8 km/L</strong><em className="up">↗ 0.3 km/L</em><Sparkline bars={[42,48,45,57,62,59,68,74,82]}/></article><article><p>Other expenses</p><strong>₹3.2L</strong><em>2.1% under budget</em><Sparkline bars={[60,45,54,41,49,35,43,31,38]}/></article><article><p>Cost per km</p><strong>₹24.80</strong><em className="down">↘ ₹1.20</em><Sparkline green bars={[82,77,69,71,62,58,55,49,46]}/></article></section><div className="two-col"><article className="panel"><div className="panel-head"><div><h2>Fuel consumption</h2><p>Litres consumed vs distance travelled</p></div><select><option>Last 6 months</option></select></div><div className="bar-chart">{[68,74,61,83,78,70].map((h,i)=><div key={i}><i style={{height:`${h}%`}}/><b style={{height:`${h-22}%`}}/><span>{["Feb","Mar","Apr","May","Jun","Jul"][i]}</span></div>)}</div></article><article className="panel categories"><div className="panel-head"><div><h2>Expense breakdown</h2><p>July 2026</p></div></div>{[["Fuel",62,"#4f46e5"],["Maintenance",18,"#10b981"],["Tolls",11,"#f59e0b"],["Insurance",6,"#3b82f6"],["Other",3,"#cbd5e1"]].map(x=><div key={x[0]}><span><i style={{background:x[2]}}/>{x[0]}</span><div><i style={{width:`${x[1]}%`,background:x[2]}}/></div><strong>{x[1]}%</strong></div>)}</article></div></> }

function Reports() { return <><PageIntro title="Reports & Analytics" desc="Turn operational data into clear, exportable decisions."/><div className="report-actions"><button className="filter">Calendar · Jul 2026</button><button className="filter">All hubs</button><button className="primary">↧ Export report</button></div><section className="insights"><article><span>✦</span><div><strong>₹2.1L savings opportunity</strong><p>Optimize 6 underutilized routes in the southern region.</p></div><button>Review →</button></article><article><span>✦</span><div><strong>Maintenance risk reduced</strong><p>Predictive servicing prevented an estimated 34 hours of downtime.</p></div><button>Details →</button></article></section><div className="report-grid"><article className="panel wide-report"><div className="panel-head"><div><h2>Operational performance</h2><p>Revenue, trips and utilization over time</p></div><div className="segmented"><button className="active">Revenue</button><button>Trips</button><button>Utilization</button></div></div><div className="report-chart"><div className="mountain m1"/><div className="mountain m2"/><div className="report-months"><span>Jan</span><span>Feb</span><span>Mar</span><span>Apr</span><span>May</span><span>Jun</span><span>Jul</span></div></div></article><article className="panel roi"><div className="panel-head"><div><h2>Fleet ROI</h2><p>Return on asset investment</p></div></div><div className="roi-ring"><div><strong>18.6%</strong><span>average ROI</span></div></div><div className="roi-row"><span>Top performer</span><strong>Heavy trucks · 24.8%</strong></div><div className="roi-row"><span>Needs attention</span><strong>Light commercial · 9.4%</strong></div></article></div></> }

function Settings() { const [saved,setSaved]=useState(false); return <><PageIntro title="Settings" desc="Configure your workspace, permissions and notifications."/><div className="settings-layout"><aside className="settings-nav">{["Organization profile","Roles & permissions","Notifications","Dispatch rules","Integrations","Security"].map((s,i)=><button className={i===0?"active":""} key={s}><span>{["▣","♙","♢","↗","⌁","◇"][i]}</span>{s}</button>)}</aside><article className="panel settings-form"><div className="panel-head"><div><h2>Organization profile</h2><p>Basic workspace and business information</p></div></div><div className="org-header"><div className="org-logo">NL</div><div><strong>Nexora Logistics</strong><p>PNG, JPG or SVG · Max 2 MB</p><button className="secondary">Change logo</button></div></div><div className="form-grid"><label>Organization name<input defaultValue="Nexora Logistics Pvt. Ltd."/></label><label>Workspace ID<input defaultValue="nexora-logistics" disabled/></label><label>Business email<input defaultValue="operations@nexoralogistics.in"/></label><label>Phone number<input defaultValue="+91 80 4567 8910"/></label><label>Head office<input defaultValue="Bengaluru, Karnataka"/></label><label>Time zone<select defaultValue="India"><option>India</option></select></label></div><div className="form-actions">{saved&&<span className="up">✓ Changes saved</span>}<button className="secondary">Cancel</button><button className="primary" onClick={()=>setSaved(true)}>Save changes</button></div></article></div></> }

export default function Home() {
  const [active,setActive]=useState<Page>("Dashboard"); const [mobileOpen,setMobileOpen]=useState(false);
  const content = useMemo(()=>({Dashboard:<Dashboard openDispatch={()=>setActive("Trip Dispatch")}/>,Vehicles:<Vehicles/>,Drivers:<Drivers/>,"Trip Dispatch":<Dispatch/>,Maintenance:<Maintenance/>,"Fuel & Expenses":<Expenses/>,Reports:<Reports/>,Settings:<Settings/>})[active],[active]);
  return <div className="app-shell"><Sidebar active={active} setActive={setActive} open={mobileOpen} close={()=>setMobileOpen(false)}/><div className="main-area"><Header page={active} setMobileOpen={setMobileOpen}/><main className="content">{content}</main><footer><span>© 2026 TransitOps</span><span>System status: <i/> All services operational</span><span>v2.4.0</span></footer></div></div>;
}
