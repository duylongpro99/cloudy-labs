// Which artwork each AWS resource kind uses, and what role its 3D object plays in the scene.
// `source` is a path inside the AWS Architecture Icons package (aws-icon-pkg/, not committed);
// scripts/import-aws-icons.mjs copies exactly these files into ./icons. Self-drawn artwork
// lives in ./icons directly and has no `source`.
//
// This file is imported by a plain Node script, so it may only use erasable TypeScript syntax.

export const ICON_PACKAGE_RELEASE = '07312026'

export type AwsKind =
  | 'region'
  | 'vpc'
  | 'az'
  | 'subnet-public'
  | 'subnet-private'
  | 'igw'
  | 'nat'
  | 'route-table'
  | 'security-group'
  | 'key-pair'
  | 'instance'
  | 'elastic-ip'

// block: a coloured plinth with the glyph extruded on its top face.
// tray-badge: a small tile in the near corner of a group tray, next to the tray label.
// attach-badge: a small puck sitting on the top edge of the resource it is attached to.
// outline-only: no object; the group is drawn by its tray border alone.
export type ObjectRole = 'block' | 'tray-badge' | 'attach-badge' | 'outline-only'

// Colour family; object-theme.ts maps each one to plinth and glyph colours per theme.
export type IconCategory = 'compute' | 'networking' | 'security' | 'region' | 'vpc' | 'subnet-public' | 'subnet-private'

export interface ManifestEntry {
  kind: AwsKind
  role: ObjectRole
  label: string
  category: IconCategory
  // File name under ./icons. Absent only for outline-only kinds.
  file?: string
  // Path relative to aws-icon-pkg/. Absent for self-drawn artwork and outline-only kinds.
  source?: string
  // Bezier subdivision used when extruding; lower it for glyphs with many curves.
  curveSegments?: number
}

const RES = 'Resource-Icons_07312026'
const GROUP = 'Architecture-Group-Icons_07312026'
const base = (path: string) => path.slice(path.lastIndexOf('/') + 1)
const pkg = (source: string) => ({ source, file: base(source) })

export const MANIFEST: readonly ManifestEntry[] = [
  { kind: 'region', role: 'tray-badge', label: 'Region', category: 'region', ...pkg(`${GROUP}/Region_32.svg`) },
  { kind: 'vpc', role: 'tray-badge', label: 'VPC', category: 'vpc', ...pkg(`${GROUP}/Virtual-private-cloud-VPC_32.svg`) },
  // AWS diagrams draw an Availability Zone as a dashed border with no icon.
  { kind: 'az', role: 'outline-only', label: 'Availability Zone', category: 'region' },
  { kind: 'subnet-public', role: 'tray-badge', label: 'Subnet công khai', category: 'subnet-public', ...pkg(`${GROUP}/Public-subnet_32.svg`) },
  { kind: 'subnet-private', role: 'tray-badge', label: 'Subnet riêng tư', category: 'subnet-private', ...pkg(`${GROUP}/Private-subnet_32.svg`) },
  { kind: 'igw', role: 'block', label: 'Internet Gateway', category: 'networking', ...pkg(`${RES}/Res_Networking-Content-Delivery/Res_Amazon-VPC_Internet-Gateway_48.svg`) },
  { kind: 'nat', role: 'block', label: 'NAT Gateway', category: 'networking', ...pkg(`${RES}/Res_Networking-Content-Delivery/Res_Amazon-VPC_NAT-Gateway_48.svg`) },
  { kind: 'route-table', role: 'block', label: 'Route Table', category: 'networking', ...pkg(`${RES}/Res_Networking-Content-Delivery/Res_Amazon-VPC_Router_48.svg`) },
  // The package has no Security Group icon (AWS diagrams use a red border); this shield is self-drawn
  // on the same 48 px grid, one path, evenodd fill, so it goes through the same pipeline.
  { kind: 'security-group', role: 'attach-badge', label: 'Security Group', category: 'security', file: 'Security-Group-Shield_48.svg' },
  // No dedicated Key Pair icon; the IAM long-term credential icon is the closest match.
  { kind: 'key-pair', role: 'block', label: 'Key Pair', category: 'security', ...pkg(`${RES}/Res_Security-Identity/Res_AWS-Identity-Access-Management_Long-Term-Security-Credential_48.svg`) },
  { kind: 'instance', role: 'block', label: 'EC2 Instance', category: 'compute', ...pkg(`${RES}/Res_Compute/Res_Amazon-EC2_Instance_48.svg`) },
  { kind: 'elastic-ip', role: 'attach-badge', label: 'Elastic IP', category: 'compute', ...pkg(`${RES}/Res_Compute/Res_Amazon-EC2_Elastic-IP-Address_48.svg`) },
]

export const MANIFEST_BY_KIND = Object.fromEntries(MANIFEST.map((e) => [e.kind, e])) as Record<AwsKind, ManifestEntry>

// Resource scope of PRD F2.4 plus the Region and Elastic IP the scene also shows.
// Route ("route" in F2.4) is drawn as an edge and SG rules belong to the SG, so neither is an object.
export const REQUIRED_KINDS: readonly AwsKind[] = [
  'region', 'vpc', 'az', 'subnet-public', 'subnet-private', 'igw', 'nat', 'route-table', 'security-group', 'key-pair', 'instance', 'elastic-ip',
]
