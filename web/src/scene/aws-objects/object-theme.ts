// Plinth and glyph colours for each icon category, per theme (PRD F3.9).
// Light: the AWS category colours taken from the icon SVGs, with a white glyph as on AWS service icons.
// Dark: the same hues lifted ~10-15% in lightness, with a glyph in the background colour.
// A category the table does not list uses `general`.

export type ThemeName = 'light' | 'dark'

export interface ObjectPalette {
  plinth: string
  glyph: string
}

export const AWS_COLORS = {
  compute: '#ED7100',
  networking: '#8C4FFF',
  security: '#DD344C',
  teal: '#00A4A6',
  green: '#7AA116',
  database: '#C925D1', // also Developer Tools
  pink: '#E7157B', // App Integration, Management & Governance
  ml: '#01A88D',
  gray: '#7D8998', // General resources
} as const

const DARK_GLYPH = '#0F141A'
const LIGHT_GLYPH = '#FFFFFF'

export const OBJECT_THEMES: Record<ThemeName, Record<string, ObjectPalette>> = {
  light: {
    compute: { plinth: AWS_COLORS.compute, glyph: LIGHT_GLYPH },
    networking: { plinth: AWS_COLORS.networking, glyph: LIGHT_GLYPH },
    security: { plinth: AWS_COLORS.security, glyph: LIGHT_GLYPH },
    region: { plinth: AWS_COLORS.teal, glyph: LIGHT_GLYPH },
    vpc: { plinth: AWS_COLORS.networking, glyph: LIGHT_GLYPH },
    'subnet-public': { plinth: AWS_COLORS.green, glyph: LIGHT_GLYPH },
    'subnet-private': { plinth: AWS_COLORS.teal, glyph: LIGHT_GLYPH },
    storage: { plinth: AWS_COLORS.green, glyph: LIGHT_GLYPH },
    database: { plinth: AWS_COLORS.database, glyph: LIGHT_GLYPH },
    'app-integration': { plinth: AWS_COLORS.pink, glyph: LIGHT_GLYPH },
    management: { plinth: AWS_COLORS.pink, glyph: LIGHT_GLYPH },
    analytics: { plinth: AWS_COLORS.networking, glyph: LIGHT_GLYPH },
    'developer-tools': { plinth: AWS_COLORS.database, glyph: LIGHT_GLYPH },
    ml: { plinth: AWS_COLORS.ml, glyph: LIGHT_GLYPH },
    containers: { plinth: AWS_COLORS.compute, glyph: LIGHT_GLYPH },
    general: { plinth: AWS_COLORS.gray, glyph: LIGHT_GLYPH },
  },
  dark: {
    compute: { plinth: '#F58A2B', glyph: DARK_GLYPH },
    networking: { plinth: '#A57BFF', glyph: DARK_GLYPH },
    security: { plinth: '#EC6478', glyph: DARK_GLYPH },
    region: { plinth: '#2CC7C9', glyph: DARK_GLYPH },
    vpc: { plinth: '#A57BFF', glyph: DARK_GLYPH },
    'subnet-public': { plinth: '#9BC93A', glyph: DARK_GLYPH },
    'subnet-private': { plinth: '#2CC7C9', glyph: DARK_GLYPH },
    storage: { plinth: '#9BC93A', glyph: DARK_GLYPH },
    database: { plinth: '#E05EE8', glyph: DARK_GLYPH },
    'app-integration': { plinth: '#F2549D', glyph: DARK_GLYPH },
    management: { plinth: '#F2549D', glyph: DARK_GLYPH },
    analytics: { plinth: '#A57BFF', glyph: DARK_GLYPH },
    'developer-tools': { plinth: '#E05EE8', glyph: DARK_GLYPH },
    ml: { plinth: '#2CC9AE', glyph: DARK_GLYPH },
    containers: { plinth: '#F58A2B', glyph: DARK_GLYPH },
    general: { plinth: '#A3ADB8', glyph: DARK_GLYPH },
  },
}

export const objectPalette = (theme: ThemeName, category: string): ObjectPalette =>
  OBJECT_THEMES[theme][category] ?? OBJECT_THEMES[theme].general

// The outline that marks a fallback object: a kind this build of the web app does not fully support.
export const FALLBACK_OUTLINE: Record<ThemeName, string> = { light: '#E0B000', dark: '#FFD43B' }

export const MIN_GLYPH_CONTRAST = 3

// WCAG 2 relative luminance of a #RRGGBB colour.
export function relativeLuminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [relativeLuminance(a), relativeLuminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
