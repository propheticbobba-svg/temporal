import { BookIcon, GlobeIcon, GraphIcon, TableIcon } from "./icons";
import styles from "./WorkspaceRail.module.css";

export type WorkspaceView = "graph" | "sources" | "table" | "overview";

interface WorkspaceRailProps {
  view: WorkspaceView;
  sourceCount: number;
  onChange: (view: WorkspaceView) => void;
}

const ITEMS: { id: WorkspaceView; label: string; icon: typeof GraphIcon }[] = [
  { id: "graph", label: "Graph", icon: GraphIcon },
  { id: "sources", label: "Sources", icon: GlobeIcon },
  { id: "table", label: "Table", icon: TableIcon },
  { id: "overview", label: "Overview", icon: BookIcon },
];

export default function WorkspaceRail({ view, sourceCount, onChange }: WorkspaceRailProps) {
  return (
    <aside className={styles.rail} aria-label="Workspace">
      <p className={styles.label}>Workspace</p>
      <nav>
        {ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              className={styles.item}
              data-active={view === item.id}
              onClick={() => onChange(item.id)}
              type="button"
            >
              <Icon />
              <span>{item.label}</span>
              {item.id === "sources" ? <em>{sourceCount}</em> : null}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
