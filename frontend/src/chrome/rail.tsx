import type { WorkspaceView } from "../api/query";

function GraphIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="5" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="6" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="18" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M11 7L7 16M13 7l4 9" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

function BookIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 18h12" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

interface WorkspaceRailProps {
  view: WorkspaceView;
  onChange: (view: WorkspaceView) => void;
}

const ITEMS: { id: WorkspaceView; label: string; icon: typeof GraphIcon }[] = [
  { id: "graph", label: "Graph", icon: GraphIcon },
  { id: "overview", label: "Overview", icon: BookIcon },
];

export function WorkspaceRail({ view, onChange }: WorkspaceRailProps) {
  return (
    <aside className="hidden w-49 shrink-0 px-2.5 pt-4 pb-6 min-[880px]:block" aria-label="Workspace">
      <p className="mx-2.5 mb-2.5 text-[0.68rem] font-medium tracking-[0.08em] text-dim uppercase">Workspace</p>
      <nav className="grid gap-0.5">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const active = view === item.id;
          return (
            <button
              key={item.id}
              className={`grid grid-cols-[16px_1fr] items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-sm font-medium ${
                active ? "bg-elev text-ink" : "text-muted hover:bg-elev hover:text-ink"
              }`}
              onClick={() => onChange(item.id)}
              type="button"
            >
              <Icon />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
