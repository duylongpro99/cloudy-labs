// Copies the AWS icons the resource registry names from the downloaded icon package
// (aws-icon-pkg/, not committed) into web/src/scene/aws-objects/icons/, and writes NOTICE.md.
// The registry comes from `uv run python -m cloudy_labs.registry export`, so no lab-server is needed.
// Exits non-zero, naming every missing file and its kind, if an icon cannot be found.
// Usage: node scripts/import-aws-icons.mjs [path-to-aws-icon-pkg]
import { execFileSync } from 'node:child_process'
import { copyFileSync, existsSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// The AWS Architecture Icons release the `source` paths in the registry point into.
const ICON_PACKAGE_RELEASE = '07312026'
// Self-drawn artwork for kinds the web app has no icon for; not a registry kind.
const FALLBACK = { icon: 'generic-resource.svg', kind: '(node dự phòng)' }

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkgDir = resolve(process.argv[2] ?? join(root, 'aws-icon-pkg'))
const outDir = join(root, 'web/src/scene/aws-objects/icons')
const registry = JSON.parse(
  execFileSync('uv', ['run', 'python', '-m', 'cloudy_labs.registry', 'export'], { cwd: join(root, 'server'), encoding: 'utf8' }),
)
const kinds = registry.kinds.filter((k) => k.icon)

const fromPackage = kinds.filter((k) => k.source)
const missing = fromPackage.filter((k) => !existsSync(join(pkgDir, k.source)))
if (missing.length) {
  for (const k of missing) console.error(`missing in ${pkgDir}: ${k.source} (kind ${k.kind})`)
  process.exit(1)
}
for (const k of fromPackage) copyFileSync(join(pkgDir, k.source), join(outDir, k.icon))

const selfDrawn = [...kinds.filter((k) => !k.source), FALLBACK]
const absentSelfDrawn = selfDrawn.filter((k) => !existsSync(join(outDir, k.icon)))
if (absentSelfDrawn.length) {
  for (const k of absentSelfDrawn) console.error(`self-drawn icon not found: ${join(outDir, k.icon)} (kind ${k.kind})`)
  process.exit(1)
}

const rows = fromPackage.map((k) => `| \`${k.icon}\` | ${k.kind} | \`${k.source}\` |`).join('\n')
const own = selfDrawn.map((k) => `| \`${k.icon}\` | ${k.kind} |`).join('\n')
writeFileSync(
  join(outDir, 'NOTICE.md'),
  `# Nguồn icon

File này do \`scripts/import-aws-icons.mjs\` sinh ra. Không sửa tay.

## AWS Architecture Icons

Các file dưới đây chép nguyên từ bộ AWS Architecture Icons, bản phát hành ${ICON_PACKAGE_RELEASE}, tải từ https://aws.amazon.com/architecture/icons/. Bản quyền thuộc Amazon.com, Inc. hoặc các công ty liên kết.

Cloudy Labs **sửa đổi** các icon này lúc chạy: path SVG được ép đùn thành khối 3D, ô màu nền của icon nhóm được thay bằng đế, và màu được đổi theo chủ đề sáng/tối. Việc sửa đổi theo quyết định của người dùng ngày 2026-10-28; điều khoản phân phối trong sản phẩm thương mại chưa được xác nhận (PRD A5).

| File | Loại | Đường dẫn trong gói |
|---|---|---|
${rows}

## Icon tự vẽ

Bộ icon AWS không có icon cho các loại dưới đây. Các file này do Cloudy Labs tự vẽ, cùng lưới 48 px và cùng cấu trúc (một path, \`fill-rule="evenodd"\`), phát hành theo giấy phép của Cloudy Labs.

| File | Loại |
|---|---|
${own}
`,
)
console.log(`copied ${fromPackage.length} icons from ${pkgDir}; ${selfDrawn.length} self-drawn present; NOTICE.md written`)
