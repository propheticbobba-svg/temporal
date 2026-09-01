import { type CSSProperties } from "react";

export const MARK = {
  word: "TEMPORAL",
  delay: 78,
  fuse: ["#22d3ee", "#38bdf8", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#f472b6"],
} as const;

export function TemporalMark({
  onHome,
  replay = 0,
}: {
  onHome: () => void;
  replay?: number;
}) {
  return (
    <button
      key={replay}
      className="block border-0 bg-transparent px-1 py-0.5"
      onClick={onHome}
      type="button"
      aria-label="Home"
    >
      <span className="mark">
        {MARK.word.split("").map((letter, index) => (
          <span
            key={`${letter}-${index}`}
            className="mark-letter"
            style={
              {
                animationDelay: `${index * MARK.delay}ms`,
                "--fuse": MARK.fuse[index],
              } as CSSProperties
            }
          >
            {letter}
          </span>
        ))}
      </span>
    </button>
  );
}
