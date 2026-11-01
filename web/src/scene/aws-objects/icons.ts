// Every SVG in ./icons, bundled at build time. A kind whose icon is not here draws as the fallback
// object; adding a kind's artwork means adding its SVG here (scripts/import-aws-icons.mjs) and rebuilding.
const RAW = import.meta.glob('./icons/*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const URL = import.meta.glob('./icons/*.svg', { query: '?url', import: 'default', eager: true }) as Record<string, string>

const byFile = <T>(glob: Record<string, T>) => new Map(Object.entries(glob).map(([path, v]) => [path.slice('./icons/'.length), v]))

export const ICON_SVG: ReadonlyMap<string, string> = byFile(RAW)
export const ICON_URL: ReadonlyMap<string, string> = byFile(URL)

// Self-drawn artwork for a kind the web app has no icon for (see icons/NOTICE.md).
export const FALLBACK_ICON = 'generic-resource.svg'
