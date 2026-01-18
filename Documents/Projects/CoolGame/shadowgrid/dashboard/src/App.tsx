import { useState } from 'react';
import { Activity, ShieldAlert, Users, Zap } from 'lucide-react';
import { CaseList } from './components/CaseList';
import { CaseDetail } from './components/CaseDetail';
import { SpectatorView } from './components/SpectatorView';
import MatchHistory from './components/MatchHistory';
import type { Case } from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);

  return (
    <div className="min-h-screen bg-background text-foreground font-sans">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 border-r border-border bg-card p-6 z-20">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-primary">
            <ShieldAlert className="h-5 w-5 text-primary-foreground" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">ShadowGrid</h1>
        </div>

        <nav className="space-y-1">
          <NavItem
            icon={<Activity />}
            label="Overview"
            active={activeTab === 'overview' && !selectedCase}
            onClick={() => { setActiveTab('overview'); setSelectedCase(null); }}
          />
          <NavItem
            icon={<ShieldAlert />}
            label="Cases"
            active={activeTab === 'cases' || !!selectedCase}
            badge={3}
            onClick={() => { setActiveTab('cases'); setSelectedCase(null); }}
          />
          <NavItem
            icon={<Users />}
            label="Players"
            active={activeTab === 'players'}
            onClick={() => { setActiveTab('players'); setSelectedCase(null); }}
          />
          <NavItem
            icon={<Zap />}
            label="Live Feed"
            active={activeTab === 'live'}
            onClick={() => { setActiveTab('live'); setSelectedCase(null); }}
          />
          <NavItem
            icon={<Activity />}
            label="Match History"
            active={activeTab === 'history'}
            onClick={() => { setActiveTab('history'); setSelectedCase(null); }}
          />
        </nav>
      </aside>

      {/* Main Content */}
      <main className="pl-64 min-h-screen">
        {selectedCase ? (
          <CaseDetail caseData={selectedCase} onClose={() => setSelectedCase(null)} />
        ) : activeTab === 'cases' ? (
          <CaseList onSelectCase={setSelectedCase} />
        ) : activeTab === 'live' ? (
          <SpectatorView />
        ) : activeTab === 'history' ? (
          <MatchHistory />
        ) : (
          <OverviewView />
        )}
      </main>
    </div>
  );
}

function OverviewView() {
  return (
    <div className="p-8 animate-in fade-in duration-500">
      <header className="mb-8">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">System status and activity overview.</p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-6 mb-8">
        <StatCard label="Active Players" value="124" change="+12%" />
        <StatCard label="Flagged Users" value="8" change="+2" isWarning />
        <StatCard label="Banned Today" value="3" />
        <StatCard label="System Load" value="45%" change="-5%" />
      </div>

      {/* Recent Alerts */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border p-4 flex justify-between items-center">
          <h3 className="font-semibold">Recent Alerts</h3>
          <button className="text-xs text-primary hover:underline">View All</button>
        </div>
        <div className="divide-y divide-border">
          <AlertItem
            user="User_992"
            reason="Speed Violation (Tier 1)"
            time="2m ago"
            severity="high"
          />
          <AlertItem
            user="ProGamer_X"
            reason="Wall Clip Anomaly"
            time="5m ago"
            severity="medium"
          />
          <AlertItem
            user="NoobMaster69"
            reason="Input Macro Detected"
            time="12m ago"
            severity="low"
          />
        </div>
      </div>
    </div>
  )
}

function NavItem({ icon, label, active, badge, onClick }: any) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-sm font-medium transition-colors ${active
        ? 'bg-primary/10 text-primary'
        : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
    >
      <div className="flex items-center gap-3">
        <span className="h-4 w-4">{icon}</span>
        <span>{label}</span>
      </div>
      {badge && (
        <span className="flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-destructive px-1 text-xs font-bold text-destructive-foreground">
          {badge}
        </span>
      )}
    </button>
  );
}

function StatCard({ label, value, change, isWarning }: any) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 hover:border-primary/50 transition-colors">
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-2xl font-bold">{value}</span>
        {change && (
          <span className={`text-xs font-medium ${isWarning || change.startsWith('-') ? 'text-destructive' : 'text-green-500'
            }`}>
            {change}
          </span>
        )}
      </div>
    </div>
  );
}

function AlertItem({ user, reason, time, severity }: any) {
  const colors = {
    high: 'text-destructive border-destructive/20 bg-destructive/10',
    medium: 'text-yellow-500 border-yellow-500/20 bg-yellow-500/10',
    low: 'text-blue-500 border-blue-500/20 bg-blue-500/10',
  };

  return (
    <div className="flex items-center justify-between p-4 hover:bg-secondary/50 transition-colors cursor-pointer group">
      <div className="flex items-center gap-4">
        <div className={`flex h-8 w-8 items-center justify-center rounded-full border text-xs font-bold uppercase ${colors[severity as keyof typeof colors]}`}>
          {severity[0]}
        </div>
        <div>
          <p className="font-medium group-hover:text-primary transition-colors">{user}</p>
          <p className="text-sm text-muted-foreground">{reason}</p>
        </div>
      </div>
      <div className="text-sm text-muted-foreground">{time}</div>
    </div>
  );
}
