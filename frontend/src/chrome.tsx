import { useEffect, useId, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from "react";

import { useAddressAutocomplete, type AddressSuggestion } from "./addressAutocomplete";
import type { WorkspaceView } from "./query";

const MARK = {
  word: "TEMPORAL",
  delay: 78,
  fuse: ["#22d3ee", "#38bdf8", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#f472b6"],
} as const;

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
      className="block border-0 bg-transparent px-1 py-0.5"
      onClick={onHome}
      type="button"
      aria-label="Home"
    >
      <span className="mark">
        {MARK.word.split("").map((letter, index) => (
          <span
            key={`${letter}-${index}`}
            className="mark-letter"
            style={
              {
                animationDelay: `${index * MARK.delay}ms`,
                "--fuse": MARK.fuse[index],
              } as CSSProperties
            }
          >
            {letter}
          </span>
        ))}
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

const EXAMPLE_ADDRESS = "501 O'Farrell St San Francisco CA 94102";

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
  const boxRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [listOpen, setListOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const { suggestions, consumeSession, resolveStreetAddress } = useAddressAutocomplete(
    address,
    listOpen && !isLoading,
  );
  const collectedQuery = useRef<{ label: string; query: Promise<string> } | null>(null);
  const showList = listOpen && suggestions.length > 0;

  useEffect(() => {
    if (!docked) {
      inputRef.current?.focus();
    }
  }, [docked]);

  useEffect(() => {
    if (!address.trim()) {
      collectedQuery.current = null;
    }
  }, [address]);

  useEffect(() => {
    setHighlight(-1);
  }, [suggestions]);

  useEffect(() => {
    if (!listOpen) {
      return;
    }

    function onPointerDown(event: PointerEvent) {
      if (boxRef.current?.contains(event.target as Node)) {
        return;
      }
      setListOpen(false);
      setHighlight(-1);
    }

    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [listOpen]);

  function fill(suggestion: AddressSuggestion) {
    const label = suggestion.text;
    setListOpen(false);
    setHighlight(-1);
    onAddressChange(label);
    inputRef.current?.focus();
    collectedQuery.current = {
      label,
      query: resolveStreetAddress(suggestion).then((resolved) => {
        consumeSession();
        return resolved;
      }),
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isLoading) {
      return;
    }
    const collected = collectedQuery.current;
    if (collected && collected.label === address.trim()) {
      onSubmit(await collected.query);
      return;
    }
    onSubmit(address);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && listOpen) {
      event.preventDefault();
      setListOpen(false);
      setHighlight(-1);
      return;
    }
    if (event.key === "ArrowDown" && suggestions.length > 0) {
      event.preventDefault();
      setListOpen(true);
      setHighlight((index) => (index + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp" && suggestions.length > 0) {
      event.preventDefault();
      setListOpen(true);
      setHighlight((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
      return;
    }
    if (event.key === "Enter" && showList && highlight >= 0 && suggestions[highlight]) {
      event.preventDefault();
      fill(suggestions[highlight]);
    }
  }

  return (
    <div className={`w-full ${docked ? "max-w-xl" : "mx-auto max-w-lg"}`}>
      <div className="relative" ref={boxRef}>
        <form
          className="flex items-center gap-3 rounded-full border border-white/8 bg-elev py-1.5 pr-1.5 pl-4 focus-within:border-white/16"
          onSubmit={handleSubmit}
        >
          <span className="text-dim">
            <SearchIcon size={16} />
          </span>
          <label className="sr-only" htmlFor="address-search">
            Address
          </label>
          <input
            id="address-search"
            ref={inputRef}
            className="min-w-0 flex-1 bg-transparent py-2 text-[0.9375rem] text-white outline-none placeholder:text-dim"
            name="place-query"
            role="combobox"
            aria-autocomplete="list"
            aria-controls={listId}
            aria-expanded={showList}
            aria-activedescendant={highlight >= 0 ? `${listId}-${highlight}` : undefined}
            onChange={(event) => {
              collectedQuery.current = null;
              setListOpen(true);
              onAddressChange(event.target.value);
            }}
            onKeyDown={handleKeyDown}
            placeholder="An address, a block, a site"
            type="text"
            value={address}
            autoComplete="off"
          />
          <button
            className="grid size-9 shrink-0 place-items-center rounded-full bg-white text-bg disabled:bg-hover disabled:text-dim"
            disabled={isLoading || address.trim().length === 0}
            type="submit"
            aria-label={isLoading ? "Working" : "Build brief"}
          >
            <ArrowUpIcon />
          </button>
        </form>
        {showList ? (
          <ul
            id={listId}
            className={`absolute right-0 left-0 z-20 max-h-64 overflow-auto rounded-2xl border border-white/8 bg-elev py-1 ${
              docked ? "bottom-[calc(100%+8px)]" : "top-[calc(100%+8px)]"
            }`}
            role="listbox"
          >
            {suggestions.map((suggestion, index) => {
              const active = index === highlight;
              return (
                <li key={suggestion.id} role="presentation">
                  <button
                    id={`${listId}-${index}`}
                    className={`flex w-full flex-col items-start gap-0.5 px-4 py-2 text-left ${
                      active ? "bg-hover text-ink" : "text-muted hover:bg-hover hover:text-ink"
                    }`}
                    onClick={() => fill(suggestion)}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setHighlight(index)}
                    role="option"
                    aria-selected={active}
                    type="button"
                  >
                    <span className="text-sm text-ink">{suggestion.mainText}</span>
                    {suggestion.secondaryText ? (
                      <span className="text-xs text-dim">{suggestion.secondaryText}</span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
      {error ? (
        <p className="mt-2.5 px-4 text-center text-[0.82rem] text-danger" role="alert">
          {error}
        </p>
      ) : isLoading ? (
        <p className="mt-2.5 px-4 text-center text-[0.82rem] text-muted" aria-live="polite">
          Reading the environment
        </p>
      ) : !docked ? (
        <button
          className="mx-auto mt-3 block border-0 bg-transparent text-xs text-dim hover:text-muted"
          onClick={() => onAddressChange(EXAMPLE_ADDRESS)}
          type="button"
        >
          Try an example
        </button>
      ) : null}
    </div>
  );
}

const THINK_COLS = 48;
const THINK_ROWS = 16;
const THINK_WAVE_MS = 6800;

function thinkStop(row: number) {
  const t = row / Math.max(1, THINK_ROWS - 1);
  return {
    fuse: dimRgb(mixFuse(t), 0.5 - t * 0.26),
    peak: (0.34 - t * 0.14).toFixed(3),
  };
}

function mixFuse(t: number): string {
  const stops = MARK.fuse.length - 1;
  const x = Math.min(1, Math.max(0, t)) * stops;
  const index = Math.min(stops - 1, Math.floor(x));
  const frac = x - index;
  const from = hexRgb(MARK.fuse[index]);
  const to = hexRgb(MARK.fuse[index + 1]);
  return `rgb(${from.map((value, channel) => Math.round(value + (to[channel] - value) * frac)).join(",")})`;
}

function dimRgb(rgb: string, amount: number): string {
  const values = rgb.match(/\d+/g)?.map(Number) ?? [128, 128, 128];
  return `rgb(${values.map((value) => Math.round(value * amount + 28 * (1 - amount))).join(",")})`;
}

function hexRgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16)) as [number, number, number];
}

export function ThinkField() {
  return (
    <div className="think-field" aria-hidden>
      {Array.from({ length: THINK_COLS * THINK_ROWS }, (_, index) => {
        const column = index % THINK_COLS;
        const row = Math.floor(index / THINK_COLS);
        const stop = thinkStop(row);
        return (
          <i
            key={index}
            style={
              {
                animationDelay: `${row * 200 + column * 3 - THINK_WAVE_MS}ms`,
                "--fuse": stop.fuse,
                "--peak": stop.peak,
              } as CSSProperties
            }
          />
        );
      })}
    </div>
  );
}

interface WorkspaceRailProps {
  view: WorkspaceView;
  sourceCount: number;
  onChange: (view: WorkspaceView) => void;
}

const ITEMS: { id: WorkspaceView; label: string; icon: typeof GraphIcon }[] = [
  { id: "graph", label: "Graph", icon: GraphIcon },
  { id: "sources", label: "Sources", icon: GlobeIcon },
  { id: "table", label: "Table", icon: TableIcon },
  { id: "overview", label: "Overview", icon: BookIcon },
];

export function WorkspaceRail({ view, sourceCount, onChange }: WorkspaceRailProps) {
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
