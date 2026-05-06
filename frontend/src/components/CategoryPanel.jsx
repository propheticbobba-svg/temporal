import styles from "./CategoryPanel.module.css";

function formatScore(score) {
  return typeof score === "number" ? score.toFixed(2) : "NO DATA";
}

function CategoryPanel({ category = {}, index = 0, label }) {
  const score = category?.score;
  const hasScore = typeof score === "number";
  const signals = category?.signals || [];
  const hasAnomaly = signals.some((signal) => signal.is_anomaly);
  const summary = category?.summary || "No category-level signals available.";

  return (
    <article
      className={styles.panel}
      style={{ "--panel-delay": `${index * 80}ms` }}
    >
      <div className={styles.panelHeader}>
        <h2>{label}</h2>
        {hasAnomaly ? <span className={styles.anomaly}>⚠ ANOMALY</span> : null}
      </div>
      <div className={hasScore ? styles.score : styles.nullScore}>
        {formatScore(score)}
      </div>
      <div className={styles.progressTrack} aria-hidden="true">
        <div
          className={styles.progressFill}
          style={{ width: hasScore ? `${score * 100}%` : "0%" }}
        />
      </div>
      <p className={styles.summary}>{summary}</p>
    </article>
  );
}

export default CategoryPanel;
