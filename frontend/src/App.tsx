import { useState } from "react";

import { Composer, TemporalMark, ThinkField, WorkspaceRail } from "./chrome";
import { usePlaceSession, usePlaceSources, useWorkspace, type WorkspaceView } from "./query";
import { StreetView } from "./StreetView";
import { BriefView, EdgeTable, PlaceGraph, SourceGrid } from "./views";

const TABS: WorkspaceView[] = ["graph", "sources", "table", "overview"];

export default function App() {
  const { draft, setDraft, address, open, reset, place, isLoading, error } = usePlaceSession();
  const brief = place?.brief;
  const location = place?.location ?? null;
  const { view, sourceFocus, openSources, changeView } = useWorkspace(brief?.address);
  const sources = usePlaceSources(address, { query: "", category: null });
  const [markKey, setMarkKey] = useState(0);

  function goHome() {
    reset();
    setMarkKey((key) => key + 1);
  }

  return (
    <div className="flex h-full bg-bg">
      <main className="relative flex min-w-0 flex-1 flex-col">
        {!brief && !isLoading && !error ? <ThinkField /> : null}
        <header className="relative z-10 flex min-h-12 items-center gap-3 px-4 pt-3.5 min-[880px]:px-6 min-[880px]:pt-4">
          <TemporalMark onHome={goHome} replay={markKey} />
          {brief ? (
            <div className="ml-auto flex items-center gap-2">
              <div className="flex gap-0.5 min-[880px]:hidden" role="tablist" aria-label="Workspace">
                {TABS.map((item) => (
                  <button
                    key={item}
                    aria-selected={view === item}
                    className={`rounded-full px-2 py-1 text-xs font-medium capitalize ${
                      view === item ? "bg-elev text-ink" : "text-dim"
                    }`}
                    onClick={() => changeView(item)}
                    role="tab"
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
              <StreetView compact location={location} />
            </div>
          ) : null}
        </header>

        <div
          className={
            brief
              ? view === "graph"
                ? "relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden p-0"
                : "relative z-10 flex min-h-0 flex-1 flex-col overflow-auto px-5 py-2 min-[880px]:px-12"
              : "relative z-10 flex min-h-0 flex-1 flex-col overflow-auto px-5 min-[880px]:px-12"
          }
        >
          {!brief && !isLoading ? <div className="flex-1" /> : null}
          {isLoading ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 pb-[8vh] text-center">
              <h1 className="m-0 text-[clamp(2rem,5vw,3.75rem)] leading-none font-medium tracking-tight text-white">
                Reading the environment
              </h1>
              <p className="m-0 max-w-lg text-lg leading-relaxed text-muted">
                Pulling every signal we can from this location.
              </p>
            </div>
          ) : null}
          {brief && address && view === "graph" ? <PlaceGraph address={address} onOpenSources={openSources} /> : null}
          {brief && address && view === "sources" ? <SourceGrid address={address} focus={sourceFocus} /> : null}
          {brief && view === "table" ? <EdgeTable brief={brief} /> : null}
          {brief && view === "overview" ? <BriefView brief={brief} location={location} /> : null}
        </div>

        <div
          className={
            brief
              ? "relative z-10 flex justify-center px-4 pt-2 pb-7 min-[880px]:px-12 min-[880px]:pb-8"
              : "relative z-10 flex min-h-0 flex-1 flex-col px-4 pt-2 min-[880px]:px-12"
          }
        >
          <div className="flex justify-center">
            <Composer
              address={draft}
              docked={Boolean(brief)}
              error={error}
              isLoading={isLoading}
              onAddressChange={setDraft}
              onSubmit={open}
            />
          </div>
        </div>
      </main>

      {brief ? (
        <WorkspaceRail
          sourceCount={sources.data?.total ?? 0}
          view={view}
          onChange={changeView}
        />
      ) : null}
    </div>
  );
}
