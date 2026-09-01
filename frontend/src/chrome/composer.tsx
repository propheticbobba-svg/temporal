import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { useAddressAutocomplete, type AddressSuggestion } from "../maps/autocomplete";

const EXAMPLE_ADDRESS = "501 O'Farrell St San Francisco CA 94102";

interface IconProps {
  size?: number;
}

function SearchIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function ArrowUpIcon({ size = 16 }: IconProps) {
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
    if (!docked && !isLoading) {
      inputRef.current?.focus();
    }
  }, [docked, isLoading]);

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
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      setListOpen(false);
      setHighlight(-1);
      if (!isLoading && address.trim()) {
        event.currentTarget.form?.requestSubmit();
      }
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
            disabled={isLoading}
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
        <ThinkBeat />
      ) : !docked ? (
        <button
          className="mx-auto mt-3 block border-0 bg-transparent text-xs text-dim hover:text-muted"
          onClick={() => {
            setListOpen(false);
            setHighlight(-1);
            collectedQuery.current = null;
            onAddressChange(EXAMPLE_ADDRESS);
            inputRef.current?.focus();
          }}
          type="button"
        >
          Try an example
        </button>
      ) : null}
    </div>
  );
}

const THINK_BEATS = ["Reading the pin", "Opening public records", "Fusing the trails"] as const;

function ThinkBeat() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((current) => current + 1);
    }, 700);
    return () => window.clearInterval(timer);
  }, []);

  const line = THINK_BEATS[index % THINK_BEATS.length];
  return (
    <p key={line} className="think-beat mt-2.5 px-4 text-center text-[0.82rem] text-muted" aria-live="polite">
      {line}
    </p>
  );
}
