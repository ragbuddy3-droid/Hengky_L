/** Logo Soalnya: buku terbuka dengan percikan. Sumber yang sama dengan favicon di `src/app/icon.svg`. */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false" style={{ flexShrink: 0, display: 'block' }}>
      <rect width="32" height="32" rx="8" fill="var(--mantine-primary-color-filled)" />
      <g fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 12.5C13.6 10.8 10.4 10.3 7.5 10.6V23.6C10.4 23.3 13.6 23.8 16 25.5C18.4 23.8 21.6 23.3 24.5 23.6V14" />
        <path d="M16 12.5C17.2 11.6 18.6 11.1 20 10.8" />
        <path d="M16 12.5V25.5" />
      </g>
      <path d="M24.5 3.5Q25.1 6.9 28.5 7.5Q25.1 8.1 24.5 11.5Q23.9 8.1 20.5 7.5Q23.9 6.9 24.5 3.5Z" fill="var(--mantine-color-accent-4)" />
    </svg>
  );
}
