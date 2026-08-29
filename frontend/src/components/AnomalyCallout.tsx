import styles from "./AnomalyCallout.module.css";

interface AnomalyCalloutProps {
  flags: string[];
}

export default function AnomalyCallout({ flags }: AnomalyCalloutProps) {
  if (flags.length === 0) {
    return null;
  }

  return (
    <aside className={styles.callout} aria-label="Anomaly flags">
      <p className={styles.label}>Anomalies</p>
      <ul>
        {flags.map((flag) => (
          <li key={flag}>{flag}</li>
        ))}
      </ul>
    </aside>
  );
}
