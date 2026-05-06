import { useState } from "react";

import styles from "./SearchView.module.css";

const EXAMPLE_ADDRESS = "4809 N Ravenswood Ave 116 Chicago IL";

function SearchView({
  compact = false,
  error,
  isLoading,
  loadingStep,
  onReset,
  onSubmit,
}) {
  const [address, setAddress] = useState("");

  function handleSubmit(event) {
    event.preventDefault();

    if (isLoading) {
      return;
    }

    onSubmit(address);
  }

  function handleExampleClick() {
    setAddress(EXAMPLE_ADDRESS);
  }

  return (
    <section
      className={`${styles.search} ${compact ? styles.compact : ""}`}
      aria-label="Location search"
    >
      <div className={styles.kicker}>TEMPORAL PLACE INTELLIGENCE</div>
      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.label} htmlFor="address-search">
          Address
        </label>
        <div className={styles.inputRow}>
          <input
            id="address-search"
            className={styles.input}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="Enter a street address"
            type="text"
            value={address}
          />
          <button className={styles.button} disabled={isLoading} type="submit">
            {isLoading ? "QUERYING" : "BUILD BRIEF"}
          </button>
        </div>
      </form>
      {error ? (
        <p className={styles.error} role="alert">
          {error.message}
        </p>
      ) : null}
      {isLoading ? (
        <p className={styles.status} aria-live="polite">
          {loadingStep}
        </p>
      ) : (
        <button
          className={styles.example}
          onClick={handleExampleClick}
          type="button"
        >
          Example: {EXAMPLE_ADDRESS}
        </button>
      )}
      {compact && !isLoading ? (
        <button className={styles.reset} onClick={onReset} type="button">
          NEW QUERY
        </button>
      ) : null}
    </section>
  );
}

export default SearchView;
