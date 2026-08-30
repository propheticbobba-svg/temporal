import { useState } from "react";

import { Composer, HomeIcon, Sidebar, TemporalMark, WorkspaceRail } from "./chrome";
import { usePlaceSession, usePlaceSources, useWorkspace, type WorkspaceView } from "./query";
import { StreetView } from "./StreetView";
import { BriefView, EdgeTable, PlaceGraph, SourceGrid } from "./views";

const TABS: WorkspaceView[] = ["graph", "sources", "table", "overview"];

export default function App() {
  const { draft, setDraft, address, history, open, reset, place, isLoading, error } = usePlaceSession();
  const brief = place?.brief;
  const location = place?.location ?? null;
  const { view, sourceFocus, openSources, changeView } = useWorkspace(brief?.address);
  const sources = usePlaceSources(address, { query: "", category: null });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [markKey, setMarkKey] = useState(0);

  function closeSidebar() {
    setSidebarOpen(false);
  }

  function goHome() {
    reset();
    closeSidebar();
    setMarkKey((key) => key + 1);
  }

  return (
    <div className="flex h-full bg-bg">
      <Sidebar
        activeAddress={brief?.address ?? null}
        collapsed={sidebarCollapsed}
        history={history}
        open={sidebarOpen}
        onFocusComposer={() => {
          document.getElementById("address-search")?.focus();
          closeSidebar();
        }}
        onNew={goHome}
        onHome={goHome}
        replay={markKey}
        onSelect={(value) => {
          open(value);
          closeSidebar();
        }}
        onToggle={() => {
          closeSidebar();
          setSidebarCollapsed((collapsed) => !collapsed);
        }}
      />

      {sidebarOpen ? (
        <button
          className="fixed inset-0 z-[15] border-0 bg-black/55 min-[880px]:hidden"
          onClick={closeSidebar}
          type="button"
          aria-label="Close menu"
        />
      ) : null}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-12 items-center gap-3 px-4 pt-3.5 min-[880px]:px-6 min-[880px]:pt-4">
          {sidebarCollapsed ? (
            <span className="hidden min-[880px]:inline">
              <TemporalMark onHome={goHome} replay={markKey} />
            </span>
          ) : null}
          <button
            className={`border-0 bg-transparent text-sm font-medium text-muted ${
              sidebarCollapsed ? "min-[880px]:inline" : "min-[880px]:hidden"
            }`}
            onClick={() => {
              if (sidebarCollapsed) {
                setSidebarCollapsed(false);
                return;
              }
              setSidebarOpen((openMenu) => !openMenu);
            }}
            type="button"
          >
            Places
          </button>
          {brief ? (
            <button
              className="inline-flex items-center gap-1.5 border-0 bg-transparent text-sm font-medium text-muted hover:text-ink"
              onClick={goHome}
              type="button"
            >
              <HomeIcon />
              Home
            </button>
          ) : null}
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
                ? "flex min-h-0 flex-1 flex-col overflow-hidden p-0"
                : "flex min-h-0 flex-1 flex-col overflow-auto px-5 py-2 min-[880px]:px-12"
              : "flex min-h-0 flex-1 flex-col overflow-auto px-5 min-[880px]:px-12"
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

        <div className={`flex justify-center px-4 pt-2 min-[880px]:px-12 ${brief ? "pb-7 min-[880px]:pb-8" : "pb-[18vh]"}`}>
          <Composer
            address={draft}
            docked={Boolean(brief)}
            error={error}
            isLoading={isLoading}
            onAddressChange={setDraft}
            onSubmit={open}
          />
        </div>
      </main>

      {brief ? (
        <WorkspaceRail
          sourceCount={sources.data?.total ?? 0}
          view={view}
          onChange={changeView}
          onHome={goHome}
        />
      ) : null}
    </div>
  );
}
