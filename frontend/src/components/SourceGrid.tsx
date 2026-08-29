import { useEffect, useMemo, useState } from "react";

import { formatDate } from "../lib/format";
import { sourceCategories, type SourceCard } from "../lib/workspaceGraph";
import styles from "./SourceGrid.module.css";

interface SourceGridProps {
  cards: SourceCard[];
  focus?: string | null;
}

export default function SourceGrid({ cards, focus }: SourceGridProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string | null>(focus ?? null);

  useEffect(() => {
    setCategory(focus ?? null);
  }, [focus]);
  const categories = useMemo(() => sourceCategories(cards), [cards]);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return cards.filter((card) => {
      if (category && card.category !== category) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return `${card.source} ${card.connector} ${card.path} ${card.category} ${card.family} ${card.tags.join(" ")} ${card.summary}`
        .toLowerCase()
        .includes(needle);
    });
  }, [cards, category, query]);
  const sections = useMemo(() => groupCards(visible), [visible]);

  return (
    <section className={styles.wrap} aria-label="Sources">
      <div className={styles.header}>
        <h2>
          Sources <span>{cards.length}</span>
          {categories.length > 0 ? <span className={styles.meta}>{categories.length} types</span> : null}
        </h2>
        <input
          className={styles.search}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search sources…"
          type="search"
          value={query}
        />
      </div>
      {categories.length > 1 ? (
        <div className={styles.chips} role="tablist" aria-label="Source types">
          <button
            aria-selected={category == null}
            onClick={() => setCategory(null)}
            role="tab"
            type="button"
          >
            All <em>{cards.length}</em>
          </button>
          {categories.map((item) => (
            <button
              key={item.title}
              aria-selected={category === item.title}
              onClick={() => setCategory(item.title)}
              role="tab"
              type="button"
            >
              {item.title} <em>{item.count}</em>
            </button>
          ))}
        </div>
      ) : null}
      {visible.length === 0 ? (
        <p className={styles.empty}>No covering sources produced a record for this place yet.</p>
      ) : (
        sections.map((section) => (
          <section className={styles.section} key={`${section.family}:${section.title}`}>
            <header>
              <p>{section.family}</p>
              <h3>
                {section.title} <span>{section.cards.length}</span>
              </h3>
            </header>
            <ul className={styles.grid}>
              {section.cards.map((card) => (
                <li key={card.id}>
                  <article className={styles.card}>
                    <p className={styles.source}>{card.source}</p>
                    <p className={styles.path}>{card.path}</p>
                    <p className={styles.summary}>{card.summary}</p>
                    <div className={styles.tags}>
                      {card.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                      <time dateTime={card.observedAt}>{formatDate(card.observedAt)}</time>
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </section>
  );
}

function groupCards(cards: SourceCard[]): { family: string; title: string; cards: SourceCard[] }[] {
  const groups = new Map<string, { family: string; title: string; cards: SourceCard[] }>();
  for (const card of cards) {
    const key = `${card.family}:${card.category}`;
    const existing = groups.get(key);
    if (existing) {
      existing.cards.push(card);
      continue;
    }
    groups.set(key, { family: card.family, title: card.category, cards: [card] });
  }
  return [...groups.values()].sort((left, right) => right.cards.length - left.cards.length || left.title.localeCompare(right.title));
}
