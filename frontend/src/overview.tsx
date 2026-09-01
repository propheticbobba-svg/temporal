import { formatCoordinate, formatWhen } from "./format";
import { sourceNotes } from "./graph";
import type { Brief, Location } from "./api/types";

interface BriefViewProps {
  brief: Brief;
  location: Location | null;
}

export function BriefView({ brief, location }: BriefViewProps) {
  const latitude = formatCoordinate(location?.latitude);
  const longitude = formatCoordinate(location?.longitude);
  const coordinates = latitude && longitude ? `${latitude}, ${longitude}` : null;
  const read = brief.fusion?.place_read || brief.narrative;
  const highlights = brief.modules.filter((module) => module.status === "answered");
  const notes = sourceNotes(brief);
  const lead = brief.fusion?.sources_read;
  const readings = (brief.fusion?.thoughts ?? []).filter((item) => item.kind === "link");

  return (
    <article className="workspace-in mx-auto mb-10 w-full max-w-xl" aria-label="Place overview">
      <p className="m-0 text-xs text-dim">
        {brief.place_class_label}
        {brief.place_class_assumed ? " · assumed" : ""}
        {coordinates ? ` · ${coordinates}` : ""}
      </p>
      <h1 className="mt-2 mb-0 text-[1.65rem] leading-tight font-medium tracking-tight text-white">
        {brief.address || location?.address}
      </h1>
      <p className="mt-4 text-[0.95rem] leading-relaxed text-ink">{read}</p>

      {brief.anomaly_flags.length > 0 ? (
        <section className="mt-8" aria-label="Anomalies">
          <h2 className="m-0 text-xs tracking-[0.08em] text-danger uppercase">Watch</h2>
          <ul className="mt-2 mb-0 list-none p-0">
            {brief.anomaly_flags.map((flag) => (
              <li key={flag} className="border-t border-white/8 py-2.5 text-[0.9rem] leading-relaxed text-ink first:border-0 first:pt-0">
                {flag}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {readings.length > 0 ? (
        <section className="mt-8" aria-label="Reading">
          <h2 className="m-0 text-xs tracking-[0.08em] text-dim uppercase">Reading</h2>
          <ul className="mt-2 mb-0 list-none p-0">
            {readings.map((thought) => (
              <li key={`${thought.from_id}-${thought.to_id}-${thought.line}`} className="border-t border-white/8 py-2.5 text-[0.9rem] leading-relaxed text-ink first:border-0 first:pt-0">
                {thought.line}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {highlights.length > 0 ? (
        <section className="mt-8" aria-label="On file">
          <h2 className="m-0 text-xs tracking-[0.08em] text-dim uppercase">On file</h2>
          <ul className="mt-2 mb-0 list-none p-0">
            {highlights.map((module) => (
              <li key={module.id} className="border-t border-white/8 py-2.5 first:border-0 first:pt-0">
                <p className="m-0 text-[0.9rem] text-white">{module.title}</p>
                <p className="mt-1 text-[0.85rem] leading-relaxed text-muted">{module.summary}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="mt-8" aria-label="Sources">
        <h2 className="m-0 text-xs tracking-[0.08em] text-dim uppercase">Sources</h2>
        {lead ? <p className="mt-2 text-[0.88rem] leading-relaxed text-muted">{lead}</p> : null}
        {notes.length === 0 ? (
          <p className="mt-2 text-[0.88rem] text-dim">No covering source produced a record for this place yet.</p>
        ) : (
          <ul className="mt-2 mb-0 list-none p-0">
            {notes.map((note) => (
              <li key={`${note.origin}-${note.edge_id}`} className="border-t border-white/8 py-2.5 first:border-0 first:pt-0">
                <p className="m-0 text-[0.9rem] text-white">{note.origin}</p>
                <p className="mt-1 text-[0.85rem] leading-relaxed text-muted">{note.proved}</p>
                {note.when ? <p className="mt-1 text-[0.72rem] text-dim">{formatWhen(note.when)}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
