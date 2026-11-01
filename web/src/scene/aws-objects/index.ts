// Public surface of the AWS 3D object library. What each kind looks like comes from the registry
// (src/registry/registry.ts); this library turns that into geometry and colours.
export { AwsObjectLayer, type AwsObjectLayerProps, type AwsObjectPlacement } from './aws-object-layer'
export { HighlightOverlay } from './highlight-overlay'
export { glyphGeometry, outlineGeometry, plinthGeometry } from './geometry-cache'
export { FALLBACK_ICON, ICON_URL } from './icons'
export * from './object-specs'
export {
  AWS_COLORS,
  FALLBACK_OUTLINE,
  OBJECT_THEMES,
  contrastRatio,
  objectPalette,
  type ObjectPalette,
  type ThemeName,
} from './object-theme'
