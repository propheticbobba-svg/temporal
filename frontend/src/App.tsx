import { useState } from "react";

import BriefView from "./components/BriefView";
import Composer from "./components/Composer";
import Sidebar from "./components/Sidebar";
import { useBrief } from "./hooks/useBrief";
import styles from "./App.module.css";

export default function App() {
  const { submitAddress, brief, location, isLoading, error, history, reset } = useBrief();
  const [address, setAddress] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const hasBrief = Boolean(brief);

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

      <main className={styles.stage} data-has-brief={hasBrief}>
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
        </header>

        <div className={styles.scroll}>
          {!hasBrief && !isLoading ? (
            <div className={styles.empty}>
              <h1>What place is this?</h1>
              <p>Open an address. We derive what the ground, the record, and the activity around it can tell us.</p>
            </div>
          ) : null}
          {isLoading && !hasBrief ? (
            <div className={styles.empty}>
              <h1>Reading the environment</h1>
              <p>Pulling every signal we can from this location.</p>
            </div>
          ) : null}
          {brief ? <BriefView brief={brief} location={location} /> : null}
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
    </div>
  );
}
