import { formatCoordinate, formatGeneratedAt } from "../lib/format";
import type { Brief, GraphEntity, Location } from "../types/api";
import AnomalyCallout from "./AnomalyCallout";
import ModulePanel from "./ModulePanel";
import SignalTimeline from "./SignalTimeline";
import StreetView360 from "./StreetView360";
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
  const entitiesById = new Map(brief.graph.entities.map((entity) => [entity.id, entity]));

  return (
    <article className={styles.brief} aria-label="Place overview">
      <header className={styles.header}>
        <div>
          <p className={styles.kind} data-assumed={brief.place_class_assumed}>
            {brief.place_class_label}
            {brief.place_class_assumed ? " · assumed" : ""}
          </p>
          <h1 className={styles.address}>{brief.address || location?.address}</h1>
          <p className={styles.coordinates}>{coordinates}</p>
          <StreetView360 location={location} />
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

      {brief.place_class_reasons.length > 0 ? (
        <ul className={styles.reasons}>
          {brief.place_class_reasons.map((reason, index) => (
            <li key={`${reason}-${index}`}>{reason}</li>
          ))}
        </ul>
      ) : null}

      {brief.business_license_coverage_note ? (
        <p className={styles.coverage}>{brief.business_license_coverage_note}</p>
      ) : null}

      <AnomalyCallout flags={brief.anomaly_flags} />

      <section className={styles.moduleGrid} aria-label="Place trails">
        {brief.modules.map((module) => (
          <ModulePanel
            key={module.id}
            module={module}
            entities={entitiesFor(module.entity_ids, entitiesById)}
          />
        ))}
      </section>

      <SignalTimeline brief={brief} />
    </article>
  );
}

function entitiesFor(ids: string[], entitiesById: Map<string, GraphEntity>): GraphEntity[] {
  return ids.flatMap((id) => {
    const entity = entitiesById.get(id);
    return entity ? [entity] : [];
  });
}
