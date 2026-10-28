// Copies the AWS icons listed in the web app's manifest from the downloaded icon package
// (aws-icon-pkg/, not committed) into web/src/scene/aws-objects/icons/, and writes NOTICE.md.
// Exits non-zero, naming every missing file, if the package does not contain an entry.
// Usage: node scripts/import-aws-icons.mjs [path-to-aws-icon-pkg]
import { copyFileSync, existsSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const pkgDir = resolve(process.argv[2] ?? join(root, 'aws-icon-pkg'))
const outDir = join(root, 'web/src/scene/aws-objects/icons')
const { MANIFEST, ICON_PACKAGE_RELEASE } = await import(pathToFileURL(join(root, 'web/src/scene/aws-objects/manifest.ts')).href)

const fromPackage = MANIFEST.filter((e) => e.source)
const missing = fromPackage.filter((e) => !existsSync(join(pkgDir, e.source)))
if (missing.length) {
  for (const e of missing) console.error(`missing in ${pkgDir}: ${e.source} (kind ${e.kind})`)
  process.exit(1)
}
for (const e of fromPackage) copyFileSync(join(pkgDir, e.source), join(outDir, e.file))

const selfDrawn = MANIFEST.filter((e) => e.file && !e.source)
const absentSelfDrawn = selfDrawn.filter((e) => !existsSync(join(outDir, e.file)))
if (absentSelfDrawn.length) {
  for (const e of absentSelfDrawn) console.error(`self-drawn icon not found: ${e.file} (kind ${e.kind})`)
  process.exit(1)
}

const rows = fromPackage.map((e) => `| \`${e.file}\` | ${e.kind} | \`${e.source}\` |`).join('\n')
const own = selfDrawn.map((e) => `| \`${e.file}\` | ${e.kind} |`).join('\n')
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
