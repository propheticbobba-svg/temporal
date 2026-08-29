import { useMemo, useState } from "react";

import { formatDate } from "../lib/format";
import type { Brief, Signal } from "../types/api";
import { CATEGORIES } from "../types/api";
import styles from "./SignalTimeline.module.css";

const DEFAULT_VISIBLE_COUNT = 5;

interface TimelineSignal extends Signal {
  categoryLabel: string;
}

function timestamp(signal: Signal): number {
  const value = new Date(signal.observed_at).getTime();
  return Number.isNaN(value) ? 0 : value;
}

function flattenSignals(brief: Brief): TimelineSignal[] {
  const fromModules = brief.modules.flatMap((module) =>
    module.signals.map((signal) => ({ ...signal, categoryLabel: module.title })),
  );
  if (fromModules.length > 0) {
    return fromModules.sort((first, second) => timestamp(second) - timestamp(first));
  }
  return CATEGORIES.flatMap(({ key, label }) =>
    brief[key].signals.map((signal) => ({ ...signal, categoryLabel: label })),
  ).sort((first, second) => timestamp(second) - timestamp(first));
}

interface SignalTimelineProps {
  brief: Brief;
}

export default function SignalTimeline({ brief }: SignalTimelineProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const signals = useMemo(() => flattenSignals(brief), [brief]);
  const visibleSignals = isExpanded ? signals : signals.slice(0, DEFAULT_VISIBLE_COUNT);
  const hasMore = signals.length > DEFAULT_VISIBLE_COUNT;

  return (
    <section className={styles.timeline} aria-label="Signal timeline">
      <div className={styles.header}>
        <h2>Signals</h2>
        <span>{signals.length}</span>
      </div>

      {signals.length === 0 ? (
        <p className={styles.empty}>No signals for this location.</p>
      ) : (
        <ol className={styles.list}>
          {visibleSignals.map((signal, index) => (
            <li
              className={`${styles.row} ${signal.is_anomaly ? styles.anomalyRow : ""}`}
              key={`${signal.source}-${signal.observed_at}-${index}`}
            >
              <span className={styles.source}>{signal.source}</span>
              <time dateTime={signal.observed_at}>{formatDate(signal.observed_at)}</time>
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
          {isExpanded ? "Show less" : `Show all ${signals.length}`}
        </button>
      ) : null}
    </section>
  );
}
