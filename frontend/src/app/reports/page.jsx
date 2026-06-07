"use client";

import Sidebar from "../../components/Sidebar";
import PageHeader from "../../components/PageHeader";
import { TrendingUp, Download } from "lucide-react";

const SUMMARY = [
  { label: "Tổng khách tuần",   value: "123",   delta: "+18% so với tuần trước", icon: "📊" },
  { label: "Nhận diện chính xác", value: "96.7%", delta: "+2.7% so với tuần trước", icon: "🎯" },
  { label: "Khách VIP",          value: "14",    delta: "+5% so với tuần trước",  icon: "⭐" },
  { label: "Thời gian TB/lượt",  value: "1h 38m",delta: "+4% so với tuần trước",  icon: "⏱" },
];

// Daily data T2–CN
const DAILY = [18, 21, 14, 16, 28, 24, 8];
const DAILY_LABELS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

// Hourly 8h–17h
const HOURLY = [2, 5, 8, 12, 15, 10, 13, 9, 7, 4];
const HOURLY_LABELS = ["8h","9h","10h","11h","12h","13h","14h","15h","16h","17h"];

function LineChart({ data, labels }) {
  const W = 480, H = 200, PAD = { t: 20, r: 10, b: 30, l: 30 };
  const max = Math.max(...data);
  const iW = W - PAD.l - PAD.r;
  const iH = H - PAD.t - PAD.b;
  const pts = data.map((v, i) => ({
    x: PAD.l + (i / (data.length - 1)) * iW,
    y: PAD.t + iH - (v / max) * iH,
  }));

  const pathD = pts.map((p, i) => {
    if (i === 0) return `M ${p.x} ${p.y}`;
    const cp = pts[i - 1];
    const mx = (cp.x + p.x) / 2;
    return `C ${mx} ${cp.y} ${mx} ${p.y} ${p.x} ${p.y}`;
  }).join(" ");

  const areaD = `${pathD} L ${pts[pts.length - 1].x} ${PAD.t + iH} L ${pts[0].x} ${PAD.t + iH} Z`;

  const yTicks = [0, max * 0.25, max * 0.5, max * 0.75, max].map((v) => Math.round(v));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* Y gridlines */}
      {yTicks.map((v, i) => {
        const y = PAD.t + iH - (v / max) * iH;
        return (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
            <text x={PAD.l - 4} y={y + 4} textAnchor="end" fontSize="9" fill="#94a3b8">{v}</text>
          </g>
        );
      })}
      {/* Area fill */}
      <path d={areaD} fill="rgba(16,185,129,0.12)" />
      {/* Line */}
      <path d={pathD} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {/* Dots */}
      {pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.5" fill="white" stroke="#10b981" strokeWidth="2" />
      ))}
      {/* X labels */}
      {pts.map((p, i) => (
        <text key={i} x={p.x} y={H - 6} textAnchor="middle" fontSize="10" fill="#94a3b8">
          {labels[i]}
        </text>
      ))}
    </svg>
  );
}

function BarChart({ data, labels }) {
  const W = 460, H = 200, PAD = { t: 20, r: 10, b: 30, l: 30 };
  const max = Math.max(...data);
  const iW = W - PAD.l - PAD.r;
  const iH = H - PAD.t - PAD.b;
  const bW = (iW / data.length) * 0.55;
  const gap = iW / data.length;

  const yTicks = [0, 4, 8, 12, 16];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {yTicks.map((v, i) => {
        const y = PAD.t + iH - (v / max) * iH;
        return (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
            <text x={PAD.l - 4} y={y + 4} textAnchor="end" fontSize="9" fill="#94a3b8">{v}</text>
          </g>
        );
      })}
      {data.map((v, i) => {
        const bH = (v / max) * iH;
        const x = PAD.l + i * gap + (gap - bW) / 2;
        const y = PAD.t + iH - bH;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bW} height={bH} rx="4" fill="#3b82f6" />
            <text x={x + bW / 2} y={H - 6} textAnchor="middle" fontSize="9" fill="#94a3b8">
              {labels[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function ReportsPage() {
  return (
    <main className="min-h-screen bg-slate-50 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1400px] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
        <Sidebar active="reports" />

        <div className="flex min-w-0 flex-col">
          <PageHeader
            title="Báo cáo & Thống kê"
            subtitle="Tổng hợp dữ liệu nhận diện và lưu lượng khách hàng."
          />

          <div className="flex-1 overflow-auto p-6">
            {/* Summary cards */}
            <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
              {SUMMARY.map((s) => (
                <div key={s.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs text-slate-400">{s.label}</span>
                    <TrendingUp className="h-4 w-4 text-slate-300" />
                  </div>
                  <p className="text-2xl font-bold text-slate-900">{s.value}</p>
                  <p className="mt-1 text-xs text-emerald-600">↗ {s.delta}</p>
                </div>
              ))}
            </div>

            {/* Charts */}
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-800">Lượt khách theo ngày</h3>
                  <button className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50">
                    <Download className="h-3.5 w-3.5" />
                    Xuất
                  </button>
                </div>
                <LineChart data={DAILY} labels={DAILY_LABELS} />
              </div>

              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-slate-800">Phân bố theo giờ (Hôm nay)</h3>
                </div>
                <BarChart data={HOURLY} labels={HOURLY_LABELS} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
