import { formatCoordinate, formatGeneratedAt } from "../lib/format";
import type { Brief, Location } from "../types/api";
import { CATEGORIES } from "../types/api";
import AnomalyCallout from "./AnomalyCallout";
import CategoryPanel from "./CategoryPanel";
import SignalTimeline from "./SignalTimeline";
import styles from "./BriefView.module.css";

interface BriefViewProps {
  brief: Brief;
  location: Location | null;
}

export default function BriefView({ brief, location }: BriefViewProps) {
  const latitude = formatCoordinate(location?.latitude);
  const longitude = formatCoordinate(location?.longitude);
  const coordinates =
    latitude && longitude ? `${latitude}, ${longitude}` : "Coordinates unresolved";

  return (
    <article className={styles.brief} aria-label="Place intelligence brief">
      <header className={styles.header}>
        <div>
          <h1 className={styles.address}>{brief.address || location?.address}</h1>
          <p className={styles.coordinates}>{coordinates}</p>
        </div>
        <dl className={styles.meta}>
          <div>
            <dt>Generated</dt>
            <dd>{formatGeneratedAt(brief.generated_at)}</dd>
          </div>
          <div>
            <dt>Signals</dt>
            <dd>{brief.signal_count}</dd>
          </div>
        </dl>
      </header>

      <p className={styles.narrative}>{brief.narrative}</p>

      {brief.business_license_coverage_note ? (
        <p className={styles.coverage}>{brief.business_license_coverage_note}</p>
      ) : null}

      <AnomalyCallout flags={brief.anomaly_flags} />

      <section className={styles.categoryGrid} aria-label="Categories">
        {CATEGORIES.map((category) => (
          <CategoryPanel
            category={brief[category.key]}
            key={category.key}
            label={category.label}
          />
        ))}
      </section>

      <SignalTimeline brief={brief} />
    </article>
  );
}
