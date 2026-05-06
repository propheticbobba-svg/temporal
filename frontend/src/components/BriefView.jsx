import AnomalyCallout from "./AnomalyCallout.jsx";
import CategoryPanel from "./CategoryPanel.jsx";
import SignalTimeline from "./SignalTimeline.jsx";
import styles from "./BriefView.module.css";

const CATEGORY_DEFINITIONS = [
  {
    key: "physical_condition",
    label: "Physical Condition",
  },
  {
    key: "regulatory_standing",
    label: "Regulatory Standing",
  },
  {
    key: "operational_activity",
    label: "Operational Activity",
  },
  {
    key: "environmental_context",
    label: "Environmental Context",
  },
];

function formatGeneratedAt(value) {
  if (!value) {
    return "UNKNOWN";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "UNKNOWN";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatCoordinate(value) {
  return typeof value === "number" ? value.toFixed(5) : null;
}

function getSignals(brief) {
  return CATEGORY_DEFINITIONS.flatMap(({ key }) => brief?.[key]?.signals || []);
}

function buildNarrative(brief, signalCount) {
  if (brief?.narrative) {
    return brief.narrative;
  }

  const summaries = CATEGORY_DEFINITIONS.map(({ key }) => brief?.[key]?.summary)
    .filter(Boolean)
    .slice(0, 2);

  if (summaries.length > 0) {
    return summaries.join(" ");
  }

  return signalCount > 0
    ? "Signals are present, but no narrative summary has been generated for this location yet."
    : brief?.business_license_coverage_note ||
        "No signal coverage has been collected for this location yet.";
}

function BriefView({ brief, location }) {
  const signals = getSignals(brief);
  const signalCount = brief.signal_count ?? signals.length;
  const anomalyFlags = Array.isArray(brief.anomaly_flags)
    ? brief.anomaly_flags
    : [];
  const latitude = formatCoordinate(location?.latitude);
  const longitude = formatCoordinate(location?.longitude);
  const coordinates =
    latitude && longitude ? `${latitude}, ${longitude}` : "COORDINATES UNRESOLVED";

  return (
    <article className={styles.brief} aria-label="Place intelligence brief">
      <header className={styles.headerStrip}>
        <div>
          <p className={styles.headerLabel}>LOCATION DOSSIER</p>
          <h1 className={styles.address}>{brief.address || location?.address}</h1>
          <p className={styles.coordinates}>{coordinates}</p>
        </div>
        <div className={styles.generated}>
          GENERATED · {formatGeneratedAt(brief.generated_at)}
          <span>{signalCount} SIGNALS</span>
        </div>
      </header>

      <section className={styles.narrative} aria-label="Narrative summary">
        <p>{buildNarrative(brief, signalCount)}</p>
      </section>

      <AnomalyCallout flags={anomalyFlags} />

      <section className={styles.categoryGrid} aria-label="Intelligence categories">
        {CATEGORY_DEFINITIONS.map((category, index) => (
          <CategoryPanel
            category={brief[category.key]}
            index={index}
            key={category.key}
            label={category.label}
          />
        ))}
      </section>

      <SignalTimeline brief={brief} />
    </article>
  );
}

export default BriefView;
