import { useEffect, useRef, type FormEvent } from "react";

import type { WorkspaceView } from "./query";

const MARK = ["T", "E", "M", "P", "O", "R", "A", "L"] as const;
const CORE = 4;

function fuseDelay(index: number): number {
  return 40 + Math.abs(index - CORE) * 70;
}

export function TemporalMark({
  onHome,
  replay = 0,
}: {
  onHome: () => void;
  replay?: number;
}) {
  return (
    <button
      key={replay}
      className="border-0 bg-transparent px-1 py-1"
      onClick={onHome}
      type="button"
      aria-label="Home"
    >
      <span className="mark">
        {MARK.map((letter, index) => (
          <span
            key={`${letter}-${index}`}
            className={index === CORE ? "mark-letter mark-letter-core" : "mark-letter"}
            style={{ animationDelay: `${fuseDelay(index)}ms` }}
          >
            {letter}
          </span>
        ))}
        <span className="mark-plume mark-plume-west" aria-hidden />
        <span className="mark-plume mark-plume-east" aria-hidden />
      </span>
    </button>
  );
}

interface IconProps {
  size?: number;
}

export function SearchIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function PlusIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function ArrowUpIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 19V6M6 11l6-6 6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function GraphIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="5" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="6" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="18" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M11 7L7 16M13 7l4 9" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function GlobeIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 12h16M12 4c2.5 2.8 3.8 5.8 3.8 8S14.5 17.2 12 20C9.5 17.2 8.2 14.2 8.2 12S9.5 6.8 12 4Z" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function BookIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 18h12" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function TableIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 10h16M10 5v14" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function PanelIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 4.5v15" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

interface SidebarProps {
  history: string[];
  activeAddress: string | null;
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (address: string) => void;
  onFocusComposer: () => void;
  onHome: () => void;
  replay?: number;
}

export function Sidebar({
  history,
  activeAddress,
  collapsed,
  open,
  onToggle,
  onNew,
  onSelect,
  onFocusComposer,
  onHome,
  replay = 0,
}: SidebarProps) {
  return (
    <aside
      className={[
        "w-[260px] shrink-0 flex-col px-3 pt-3.5 pb-6",
        open ? "fixed inset-y-0 left-0 z-20 flex bg-bg" : "hidden",
        "min-[880px]:static min-[880px]:flex",
        collapsed ? "min-[880px]:hidden" : "",
      ].join(" ")}
      aria-label="Navigation"
    >
      <div className="px-0.5 pb-5">
        <TemporalMark onHome={onHome} replay={replay} />
        <div className="mt-3 flex gap-0.5">
          <button
            className="grid size-8 place-items-center rounded-full text-muted hover:bg-hover hover:text-ink"
            onClick={onFocusComposer}
            type="button"
            aria-label="Search"
          >
            <SearchIcon />
          </button>
          <button
            className="grid size-8 place-items-center rounded-full text-muted hover:bg-hover hover:text-ink"
            onClick={onToggle}
            type="button"
            aria-label="Toggle sidebar"
          >
            <PanelIcon />
          </button>
        </div>
      </div>

      <nav className="grid gap-1">
        <button
          className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-left text-sm font-medium text-muted hover:bg-hover hover:text-ink"
          onClick={onNew}
          type="button"
        >
          <PlusIcon size={16} />
          New place
        </button>
      </nav>

      <div className="mt-7 min-h-0 overflow-auto">
        <p className="mx-3 mb-2 text-xs font-medium text-dim">Opened</p>
        {history.length === 0 ? (
          <p className="mx-2.5 text-[0.82rem] text-dim">No places yet</p>
        ) : (
          <ul className="m-0 list-none p-0">
            {history.map((item) => (
              <li key={item}>
                <button
                  className={`block w-full truncate rounded-xl px-3 py-2 text-left text-[0.8125rem] hover:bg-hover hover:text-ink ${
                    item === activeAddress ? "bg-elev text-ink" : "text-muted"
                  }`}
                  onClick={() => onSelect(item)}
                  type="button"
                >
                  {item}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}

const EXAMPLE_ADDRESS = "4600 Silver Hill Rd Washington DC 20233";

interface ComposerProps {
  address: string;
  docked: boolean;
  error: string | null;
  isLoading: boolean;
  onAddressChange: (value: string) => void;
  onSubmit: (address: string) => void;
}

export function Composer({
  address,
  docked,
  error,
  isLoading,
  onAddressChange,
  onSubmit,
}: ComposerProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!docked) {
      inputRef.current?.focus();
    }
  }, [docked]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isLoading) {
      onSubmit(address);
    }
  }

  return (
    <div className={`w-full ${docked ? "max-w-[760px]" : "max-w-[720px]"}`}>
      <form className="flex min-h-14 items-center gap-2 rounded-full bg-[#1a1a1a] py-2 pr-2 pl-3.5" onSubmit={handleSubmit}>
        <button
          className="grid size-9 shrink-0 place-items-center rounded-full text-muted hover:text-ink"
          onClick={() => onAddressChange(EXAMPLE_ADDRESS)}
          type="button"
          aria-label="Use example address"
        >
          <PlusIcon />
        </button>
        <label className="sr-only" htmlFor="address-search">
          Address
        </label>
        <input
          id="address-search"
          ref={inputRef}
          className="min-w-0 flex-1 bg-transparent px-1 py-2.5 text-[0.9375rem] text-white outline-none placeholder:text-dim"
          onChange={(event) => onAddressChange(event.target.value)}
          placeholder="An address, a block, a site"
          type="text"
          value={address}
          autoComplete="street-address"
        />
        <button
          className="grid size-9 shrink-0 place-items-center rounded-full bg-white text-bg disabled:bg-[#2c2c2c] disabled:text-dim"
          disabled={isLoading || address.trim().length === 0}
          type="submit"
          aria-label={isLoading ? "Working" : "Build brief"}
        >
          <ArrowUpIcon />
        </button>
      </form>
      {error ? (
        <p className="mt-2.5 px-4 text-center text-[0.82rem] text-danger" role="alert">
          {error}
        </p>
      ) : isLoading ? (
        <p className="mt-2.5 px-4 text-center text-[0.82rem] text-muted" aria-live="polite">
          Reading the environment
        </p>
      ) : null}
    </div>
  );
}

interface WorkspaceRailProps {
  view: WorkspaceView;
  sourceCount: number;
  onChange: (view: WorkspaceView) => void;
  onHome: () => void;
}

const ITEMS: { id: WorkspaceView; label: string; icon: typeof GraphIcon }[] = [
  { id: "graph", label: "Graph", icon: GraphIcon },
  { id: "sources", label: "Sources", icon: GlobeIcon },
  { id: "table", label: "Table", icon: TableIcon },
  { id: "overview", label: "Overview", icon: BookIcon },
];

export function HomeIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 11.2 12 4l8 7.2V20a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 20v-8.8Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M9.5 21.5v-7h5v7" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export function WorkspaceRail({ view, sourceCount, onChange, onHome }: WorkspaceRailProps) {
  return (
    <aside className="hidden w-49 shrink-0 px-2.5 pt-4 pb-6 min-[880px]:block" aria-label="Workspace">
      <button
        className="mb-4 flex w-full items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-sm font-medium text-muted hover:bg-elev hover:text-ink"
        onClick={onHome}
        type="button"
      >
        <HomeIcon />
        Home
      </button>
      <p className="mx-2.5 mb-2.5 text-[0.68rem] font-medium tracking-[0.08em] text-dim uppercase">Workspace</p>
      <nav className="grid gap-0.5">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const active = view === item.id;
          return (
            <button
              key={item.id}
              className={`grid grid-cols-[16px_1fr_auto] items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-sm font-medium ${
                active ? "bg-elev text-ink" : "text-muted hover:bg-elev hover:text-ink"
              }`}
              onClick={() => onChange(item.id)}
              type="button"
            >
              <Icon />
              <span>{item.label}</span>
              {item.id === "sources" ? <em className="text-xs not-italic text-dim">{sourceCount}</em> : null}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
