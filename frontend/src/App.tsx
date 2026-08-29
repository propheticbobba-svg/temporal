import { useEffect, useMemo, useState } from "react";

import PlaceGraph from "./components/PlaceGraph";
import BriefView from "./components/BriefView";
import Composer from "./components/Composer";
import EdgeTable from "./components/EdgeTable";
import Sidebar from "./components/Sidebar";
import SourceGrid from "./components/SourceGrid";
import StreetView360 from "./components/StreetView360";
import WorkspaceRail, { type WorkspaceView } from "./components/WorkspaceRail";
import { useBrief } from "./hooks/useBrief";
import { buildWorkspaceGraph, sourceCards } from "./lib/workspaceGraph";
import styles from "./App.module.css";

export default function App() {
  const { submitAddress, brief, location, isLoading, error, history, reset } = useBrief();
  const [address, setAddress] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("graph");
  const [sourceFocus, setSourceFocus] = useState<string | null>(null);

  const hasBrief = Boolean(brief);
  const graph = useMemo(() => (brief ? buildWorkspaceGraph(brief) : null), [brief]);
  const sources = useMemo(() => (brief ? sourceCards(brief) : []), [brief]);

  useEffect(() => {
    setWorkspaceView("graph");
    setSourceFocus(null);
  }, [brief?.address]);

  function openSources(focus?: string) {
    setSourceFocus(focus ?? null);
    setWorkspaceView("sources");
  }

  function changeView(view: WorkspaceView) {
    setSourceFocus(null);
    setWorkspaceView(view);
  }

  function focusComposer() {
    document.getElementById("address-search")?.focus();
    setSidebarOpen(false);
  }

  return (
    <div className={styles.app}>
      <Sidebar
        activeAddress={brief?.address ?? null}
        collapsed={sidebarCollapsed}
        history={history}
        open={sidebarOpen}
        onFocusComposer={focusComposer}
        onNew={() => {
          reset();
          setAddress("");
          setSidebarOpen(false);
        }}
        onSelect={(value) => {
          setAddress(value);
          setSidebarOpen(false);
          void submitAddress(value);
        }}
        onToggle={() => {
          setSidebarOpen(false);
          setSidebarCollapsed((collapsed) => !collapsed);
        }}
      />

      {sidebarOpen ? (
        <button
          className={styles.backdrop}
          onClick={() => setSidebarOpen(false)}
          type="button"
          aria-label="Close menu"
        />
      ) : null}

      <main className={styles.stage} data-has-brief={hasBrief} data-view={workspaceView}>
        <header className={styles.topbar}>
          <button
            className={styles.menu}
            data-collapsed={sidebarCollapsed}
            onClick={() => {
              if (sidebarCollapsed) {
                setSidebarCollapsed(false);
                return;
              }
              setSidebarOpen((open) => !open);
            }}
            type="button"
          >
            Places
          </button>
          {brief ? (
            <div className={styles.topActions}>
              <div className={styles.mobileTabs} role="tablist" aria-label="Workspace">
                {(["graph", "sources", "table", "overview"] as const).map((item) => (
                  <button
                    key={item}
                    aria-selected={workspaceView === item}
                    onClick={() => changeView(item)}
                    role="tab"
                    type="button"
                  >
                    {item}
                  </button>
                ))}
              </div>
              <StreetView360 compact location={location} />
            </div>
          ) : null}
        </header>

        <div className={styles.scroll}>
          {!hasBrief && !isLoading ? (
            <div className={styles.empty}>
              <h1>What place is this?</h1>
              <p>Open an address. We classify the place, then follow only the trails that belong to that type.</p>
            </div>
          ) : null}
          {isLoading && !hasBrief ? (
            <div className={styles.empty}>
              <h1>Reading the environment</h1>
              <p>Pulling every signal we can from this location.</p>
            </div>
          ) : null}
          {brief && workspaceView === "graph" && graph ? (
            <PlaceGraph graph={graph} onOpenSources={openSources} />
          ) : null}
          {brief && workspaceView === "sources" ? <SourceGrid cards={sources} focus={sourceFocus} /> : null}
          {brief && workspaceView === "table" ? <EdgeTable brief={brief} /> : null}
          {brief && workspaceView === "overview" ? (
            <BriefView brief={brief} location={location} />
          ) : null}
        </div>

        <div className={styles.composerSlot}>
          <Composer
            address={address}
            docked={hasBrief}
            error={error}
            isLoading={isLoading}
            onAddressChange={setAddress}
            onSubmit={submitAddress}
          />
        </div>
      </main>

      {brief ? (
        <WorkspaceRail
          sourceCount={sources.length}
          view={workspaceView}
          onChange={changeView}
        />
      ) : null}
    </div>
  );
}
