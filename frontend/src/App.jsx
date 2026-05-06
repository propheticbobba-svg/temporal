import BriefView from "./components/BriefView.jsx";
import SearchView from "./components/SearchView.jsx";
import { useBrief } from "./hooks/useBrief.js";
import styles from "./App.module.css";

function App() {
  const {
    submitAddress,
    brief,
    location,
    isLoading,
    loadingStep,
    error,
    reset,
  } = useBrief();

  return (
    <main className={styles.shell} data-has-brief={Boolean(brief)}>
      <SearchView
        compact={isLoading || Boolean(brief)}
        error={error}
        isLoading={isLoading}
        loadingStep={loadingStep}
        onReset={reset}
        onSubmit={submitAddress}
      />
      {brief ? <BriefView brief={brief} location={location} /> : null}
    </main>
  );
}

export default App;
