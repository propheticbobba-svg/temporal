import { formatDate } from "../lib/format";
import type { Brief } from "../types/api";
import { REL_LABEL } from "../types/api";
import styles from "./EdgeTable.module.css";

interface EdgeTableProps {
  brief: Brief;
}

export default function EdgeTable({ brief }: EdgeTableProps) {
  const labels = new Map<string, string>([[brief.graph.place_id, brief.address]]);
  for (const entity of brief.graph.entities) {
    labels.set(entity.id, entity.label);
  }

  return (
    <section className={styles.wrap} aria-label="Tabular relations">
      <h2>Table</h2>
      {brief.graph.edges.length === 0 ? (
        <p className={styles.empty}>No related records to list yet.</p>
      ) : (
        <div className={styles.scroll}>
          <table>
            <thead>
              <tr>
                <th>From</th>
                <th>Relation</th>
                <th>To</th>
                <th>Source</th>
                <th>Capability</th>
                <th>Date</th>
              </tr>
            </thead>
            <tbody>
              {brief.graph.edges.map((edge) => (
                <tr key={edge.id}>
                  <td>{labels.get(edge.from_id || brief.graph.place_id) ?? edge.from_id}</td>
                  <td>{REL_LABEL[edge.rel]}</td>
                  <td>{labels.get(edge.entity_id) ?? edge.entity_id}</td>
                  <td>{edge.origin || edge.source}</td>
                  <td>{edge.capability.replaceAll("_", " ")}</td>
                  <td>
                    <time dateTime={edge.observed_at}>{formatDate(edge.observed_at)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
