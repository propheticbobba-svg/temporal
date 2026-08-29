import { PanelIcon, PlusIcon, SearchIcon } from "./icons";
import styles from "./Sidebar.module.css";

interface SidebarProps {
  history: string[];
  activeAddress: string | null;
  collapsed: boolean;
  open: boolean;
  onToggle: () => void;
  onNew: () => void;
  onSelect: (address: string) => void;
  onFocusComposer: () => void;
}

export default function Sidebar({
  history,
  activeAddress,
  collapsed,
  open,
  onToggle,
  onNew,
  onSelect,
  onFocusComposer,
}: SidebarProps) {
  return (
    <aside
      className={`${styles.sidebar} ${open ? styles.open : ""} ${collapsed ? styles.collapsed : ""}`}
      aria-label="Navigation"
    >
      <div className={styles.top}>
        <div className={styles.topActions}>
          <button className={styles.iconButton} onClick={onFocusComposer} type="button" aria-label="Search">
            <SearchIcon />
          </button>
          <button className={styles.iconButton} onClick={onToggle} type="button" aria-label="Toggle sidebar">
            <PanelIcon />
          </button>
        </div>
      </div>

      <nav className={styles.nav}>
        <button className={`${styles.navItem} ${styles.active}`} onClick={onNew} type="button">
          Places
        </button>
        <button className={styles.navItem} onClick={onNew} type="button">
          <PlusIcon size={16} />
          New place
        </button>
      </nav>

      <div className={styles.section}>
        <p className={styles.sectionLabel}>Opened</p>
        {history.length === 0 ? (
          <p className={styles.empty}>No places yet</p>
        ) : (
          <ul className={styles.list}>
            {history.map((address) => (
              <li key={address}>
                <button
                  className={`${styles.historyItem} ${
                    address === activeAddress ? styles.historyActive : ""
                  }`}
                  onClick={() => onSelect(address)}
                  type="button"
                >
                  {address}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
