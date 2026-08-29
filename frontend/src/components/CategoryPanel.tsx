import { formatScore } from "../lib/format";
import type { CategoryBrief } from "../types/api";
import styles from "./CategoryPanel.module.css";

interface CategoryPanelProps {
  category: CategoryBrief;
  label: string;
}

export default function CategoryPanel({ category, label }: CategoryPanelProps) {
  const score = category.score;
  const hasScore = typeof score === "number";
  const hasAnomaly = category.signals.some((signal) => signal.is_anomaly);

  return (
    <article className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>{label}</h2>
        {hasAnomaly ? <span className={styles.anomaly}>Anomaly</span> : null}
      </div>
      <p className={hasScore ? styles.score : styles.nullScore}>{formatScore(score)}</p>
      <div className={styles.progressTrack} aria-hidden="true">
        <div
          className={styles.progressFill}
          style={{ width: hasScore ? `${score * 100}%` : "0%" }}
        />
      </div>
      <p className={styles.summary}>
        {category.summary || "No signals for this category."}
      </p>
    </article>
  );
}
