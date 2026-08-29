interface IconProps {
  size?: number;
}

export function SearchIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M16 16l5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function PlusIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function ArrowUpIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 19V6M6 11l6-6 6 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function GraphIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="5" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="6" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="18" cy="18" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M11 7L7 16M13 7l4 9" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function GlobeIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 12h16M12 4c2.5 2.8 3.8 5.8 3.8 8S14.5 17.2 12 20C9.5 17.2 8.2 14.2 8.2 12S9.5 6.8 12 4Z" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function BookIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5V5.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 18h12" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function TableIcon({ size = 16 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M4 10h16M10 5v14" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function PanelIcon({ size = 18 }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M9 4.5v15" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}
