// Light and dark scene tokens (PRD F3.9). Group border colours follow the AWS group
// convention from F3.7; the dark theme only lifts their lightness for contrast.
// Object plinth and glyph colours are not here: AwsObjectLayer reads them from aws-objects/object-theme.ts by theme name.
import type { GroupKind } from './fixture'
import { AWS_COLORS, OBJECT_THEMES, type ThemeName } from './aws-objects'

export type { ThemeName }

export interface GroupStyle {
  border: string
  dashed: 'none' | 'dash' | 'dash-dot'
  fill: string
  opacity: number
}

export interface Theme {
  background: string
  label: string
  labelOutline: string
  hemisphere: { sky: string; ground: string; intensity: number }
  key: number
  fill: number
  environment: number
  groups: Record<GroupKind, GroupStyle>
  edge: string // edges without a kind (benchmark fixture)
  edges: { routeIgw: string; routeNat: string; association: string; usesKey: string }
  pulse: string
  outline: string
  // Ghosts of the lab's target architecture (PRD F6.2): kind colours kept, faded, dashed, labelled.
  ghost: { trayOpacity: number; borderOpacity: number; label: string }
  achieved: string // the mark on a real resource that reached its target node
  failed: string // a check that does not pass yet
  checkHighlight: string // outlines what the selected check looks at
}

export const THEMES: Record<ThemeName, Theme> = {
  light: {
    background: '#F4F6F8',
    label: '#16191F',
    labelOutline: '#FFFFFF',
    hemisphere: { sky: '#FFFFFF', ground: '#B9C2CC', intensity: 1.1 },
    key: 2.2,
    fill: 0.45,
    environment: 0.6,
    groups: {
      region: { border: AWS_COLORS.teal, dashed: 'dash-dot', fill: '#FFFFFF', opacity: 0.55 },
      vpc: { border: AWS_COLORS.networking, dashed: 'none', fill: '#F3EDFF', opacity: 0.5 },
      az: { border: AWS_COLORS.teal, dashed: 'dash', fill: '#E6F6F6', opacity: 0.35 },
      'subnet-public': { border: AWS_COLORS.green, dashed: 'none', fill: '#EEF5E0', opacity: 0.6 },
      'subnet-private': { border: AWS_COLORS.teal, dashed: 'none', fill: '#E0F2F2', opacity: 0.6 },
    },
    edge: '#5F6B7A',
    edges: { routeIgw: '#4D7A0E', routeNat: '#7A3FE6', association: '#5F6B7A', usesKey: '#C4362F' },
    pulse: '#FF9900',
    outline: '#0972D3',
    ghost: { trayOpacity: 0.35, borderOpacity: 0.75, label: '#5F6B7A' },
    achieved: '#1D8102',
    failed: '#D91515',
    checkHighlight: '#EC7211',
  },
  dark: {
    background: '#0F141A',
    label: '#E9EDF1',
    labelOutline: '#0F141A',
    hemisphere: { sky: '#C9D6E3', ground: '#1A2129', intensity: 0.7 },
    key: 1.6,
    fill: 0.3,
    environment: 0.35,
    groups: {
      region: { border: OBJECT_THEMES.dark.region.plinth, dashed: 'dash-dot', fill: '#1B232C', opacity: 0.6 },
      vpc: { border: OBJECT_THEMES.dark.vpc.plinth, dashed: 'none', fill: '#221D33', opacity: 0.55 },
      az: { border: OBJECT_THEMES.dark.region.plinth, dashed: 'dash', fill: '#15292B', opacity: 0.4 },
      'subnet-public': { border: OBJECT_THEMES.dark['subnet-public'].plinth, dashed: 'none', fill: '#1E2A14', opacity: 0.65 },
      'subnet-private': { border: OBJECT_THEMES.dark['subnet-private'].plinth, dashed: 'none', fill: '#13292A', opacity: 0.65 },
    },
    edge: '#8A97A6',
    edges: { routeIgw: '#A4CF4A', routeNat: '#B591FF', association: '#9AA6B4', usesKey: '#FF7A70' },
    pulse: '#FFB347',
    outline: '#5CB2FF',
    ghost: { trayOpacity: 0.4, borderOpacity: 0.8, label: '#9AA6B4' },
    achieved: '#7FD14A',
    failed: '#FF7A80',
    checkHighlight: '#FFB347',
  },
}
