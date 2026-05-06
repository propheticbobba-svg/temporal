import { useMemo, useState } from "react";

import styles from "./SignalTimeline.module.css";

const DEFAULT_VISIBLE_COUNT = 5;

function getTimestamp(signal) {
  const timestamp = new Date(signal.observed_at).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function formatDate(value) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "DATE UNKNOWN";
  }

  return new Intl.DateTimeFormat("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function normalizeSource(source) {
  return String(source || "unknown").toLowerCase();
}

function flattenSignals(brief) {
  const categorizedSignals = [
    {
      label: "Physical Condition",
      signals: brief?.physical_condition?.signals || [],
    },
    {
      label: "Regulatory Standing",
      signals: brief?.regulatory_standing?.signals || [],
    },
    {
      label: "Operational Activity",
      signals: brief?.operational_activity?.signals || [],
    },
    {
      label: "Environmental Context",
      signals: brief?.environmental_context?.signals || [],
    },
  ];

  return categorizedSignals.flatMap(({ label, signals }) =>
    signals.map((signal) => ({
      ...signal,
      categoryLabel: label,
    })),
  ).sort((first, second) => getTimestamp(first) - getTimestamp(second));
}

function SignalTimeline({ brief }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const signals = useMemo(() => flattenSignals(brief), [brief]);
  const visibleSignals = isExpanded
    ? signals
    : signals.slice(0, DEFAULT_VISIBLE_COUNT);
  const hasMore = signals.length > DEFAULT_VISIBLE_COUNT;

  return (
    <section className={styles.timeline} aria-label="Signal timeline">
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>RAW SIGNAL TIMELINE</p>
          <h2>Collected Evidence</h2>
        </div>
        <span>{signals.length} TOTAL</span>
      </div>

      {signals.length === 0 ? (
        <p className={styles.empty}>No signals collected for this location yet.</p>
      ) : (
        <ol className={styles.list}>
          {visibleSignals.map((signal, index) => (
            <li
              className={`${styles.row} ${
                signal.is_anomaly ? styles.anomalyRow : ""
              }`}
              key={`${signal.source}-${signal.observed_at}-${index}`}
            >
              <span
                className={styles.sourceTag}
                data-source={normalizeSource(signal.source)}
              >
                {String(signal.source || "unknown").toUpperCase()}
              </span>
              <time dateTime={signal.observed_at}>
                {formatDate(signal.observed_at)}
              </time>
              <span className={styles.divider}>—</span>
              <p>{signal.summary}</p>
              <span className={styles.category}>{signal.categoryLabel}</span>
            </li>
          ))}
        </ol>
      )}

      {hasMore ? (
        <button
          className={styles.expand}
          onClick={() => setIsExpanded((expanded) => !expanded)}
          type="button"
        >
          {isExpanded
            ? `COLLAPSE TO ${DEFAULT_VISIBLE_COUNT}`
            : `EXPAND TO ${signals.length}`}
        </button>
      ) : null}
    </section>
  );
}

export default SignalTimeline;
