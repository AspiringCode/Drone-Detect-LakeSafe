/** LakeSafe's decorative wave mark: a curling crest over open water, two-tone like the brand icon. */
export function WaveMark() {
  return <svg className="app-brand__wave" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <path className="wave-fill" d="M4 15.5C4.6 9 9.6 5 15.2 5c5.4 0 9.8 3.3 9.8 7.6 0 2.6-1.9 4.4-4.2 4.4-1.5 0-2.7-.9-2.7-2.3 0-1 .7-1.7 1.6-1.7-1.3-1.6-3.2-2.4-5.3-2.4-3.9 0-6.6 3.2-6.6 7.1 0 .6.1 1.2.2 1.8H28V24a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3z" />
    <path className="wave-line" d="M4 15.5C4.6 9 9.6 5 15.2 5c5.4 0 9.8 3.3 9.8 7.6 0 2.6-1.9 4.4-4.2 4.4-1.5 0-2.7-.9-2.7-2.3 0-1 .7-1.7 1.6-1.7" />
    <path className="wave-line" d="M4 19.5c2 1.4 4 1.4 6 0s4-1.4 6 0 4 1.4 6 0 4-1.4 6 0" />
    <path className="wave-line" d="M4 23.5c2 1.4 4 1.4 6 0s4-1.4 6 0 4 1.4 6 0 4-1.4 6 0" />
    <path className="wave-line" d="M10 27.5c2 1.4 4 1.4 6 0s4-1.4 6 0" />
  </svg>;
}
