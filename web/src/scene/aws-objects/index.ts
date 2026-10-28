// Public surface of the AWS 3D object library.
export { AwsObjectLayer, type AwsObjectLayerProps, type AwsObjectPlacement } from './aws-object-layer'
export { HighlightOverlay } from './highlight-overlay'
export { glyphGeometry, outlineGeometry, plinthGeometry } from './geometry-cache'
export {
  MANIFEST,
  MANIFEST_BY_KIND,
  REQUIRED_KINDS,
  ICON_PACKAGE_RELEASE,
  type AwsKind,
  type IconCategory,
  type ManifestEntry,
  type ObjectRole,
} from './manifest'
export * from './object-specs'
export { AWS_COLORS, OBJECT_THEMES, contrastRatio, type ObjectPalette, type ThemeName } from './object-theme'
