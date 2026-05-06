import styles from "./AnomalyCallout.module.css";

function AnomalyCallout({ flags = [] }) {
  if (!flags.length) {
    return null;
  }

  return (
    <aside className={styles.callout} aria-label="Anomaly flags">
      <p className={styles.label}>ANOMALY FLAGS</p>
      <ul>
        {flags.map((flag) => (
          <li key={flag}>{flag}</li>
        ))}
      </ul>
    </aside>
  );
}

export default AnomalyCallout;
