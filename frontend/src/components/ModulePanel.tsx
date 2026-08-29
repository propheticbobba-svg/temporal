import type { BriefModule, GraphEntity } from "../types/api";
import { STATUS_LABEL } from "../types/api";
import { formatDate } from "../lib/format";
import styles from "./ModulePanel.module.css";

interface ModulePanelProps {
  module: BriefModule;
  entities: GraphEntity[];
}

export default function ModulePanel({ module, entities }: ModulePanelProps) {
  return (
    <article className={styles.panel} data-status={module.status}>
      <div className={styles.header}>
        <div>
          <h2>{module.title}</h2>
          <p className={styles.trail}>{module.trail}</p>
        </div>
        <span className={styles.status}>{STATUS_LABEL[module.status]}</span>
      </div>

      <p className={styles.summary}>{module.summary}</p>

      {entities.length > 0 ? (
        <ul className={styles.entities}>
          {entities.map((entity) => (
            <li key={entity.id}>{entity.label}</li>
          ))}
        </ul>
      ) : null}

      {module.signals.length > 0 ? (
        <ol className={styles.facts}>
          {module.signals.slice(0, 3).map((signal, index) => (
            <li key={`${signal.source}-${signal.observed_at}-${index}`}>
              <time dateTime={signal.observed_at}>{formatDate(signal.observed_at)}</time>
              <span>{signal.summary}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </article>
  );
}
