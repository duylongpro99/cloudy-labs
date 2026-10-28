// Light and dark theme tokens (PRD F3.9). Group border colours follow the AWS group
// convention from F3.7; the dark theme only lifts their lightness for contrast.
import type { GroupKind, LeafKind } from '../fixture'

export type ThemeName = 'light' | 'dark'

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
  block: Record<LeafKind, string>
  groups: Record<GroupKind, GroupStyle>
  edge: string
  pulse: string
  outline: string
}

const AWS = { teal: '#00A4A6', purple: '#8C4FFF', green: '#7AA116' }

export const THEMES: Record<ThemeName, Theme> = {
  light: {
    background: '#F4F6F8',
    label: '#16191F',
    labelOutline: '#FFFFFF',
    hemisphere: { sky: '#FFFFFF', ground: '#B9C2CC', intensity: 1.1 },
    key: 2.2,
    fill: 0.45,
    environment: 0.6,
    block: { instance: '#ED7100', nat: '#8C4FFF', igw: '#8C4FFF' },
    groups: {
      region: { border: AWS.teal, dashed: 'dash-dot', fill: '#FFFFFF', opacity: 0.55 },
      vpc: { border: AWS.purple, dashed: 'none', fill: '#F3EDFF', opacity: 0.5 },
      az: { border: AWS.teal, dashed: 'dash', fill: '#E6F6F6', opacity: 0.35 },
      'subnet-public': { border: AWS.green, dashed: 'none', fill: '#EEF5E0', opacity: 0.6 },
      'subnet-private': { border: AWS.teal, dashed: 'none', fill: '#E0F2F2', opacity: 0.6 },
    },
    edge: '#5F6B7A',
    pulse: '#FF9900',
    outline: '#0972D3',
  },
  dark: {
    background: '#0F141A',
    label: '#E9EDF1',
    labelOutline: '#0F141A',
    hemisphere: { sky: '#C9D6E3', ground: '#1A2129', intensity: 0.7 },
    key: 1.6,
    fill: 0.3,
    environment: 0.35,
    block: { instance: '#F58A2B', nat: '#A57BFF', igw: '#A57BFF' },
    groups: {
      region: { border: '#2CC7C9', dashed: 'dash-dot', fill: '#1B232C', opacity: 0.6 },
      vpc: { border: '#A57BFF', dashed: 'none', fill: '#221D33', opacity: 0.55 },
      az: { border: '#2CC7C9', dashed: 'dash', fill: '#15292B', opacity: 0.4 },
      'subnet-public': { border: '#9BC93A', dashed: 'none', fill: '#1E2A14', opacity: 0.65 },
      'subnet-private': { border: '#2CC7C9', dashed: 'none', fill: '#13292A', opacity: 0.65 },
    },
    edge: '#8A97A6',
    pulse: '#FFB347',
    outline: '#5CB2FF',
  },
}
