---
title: "Plan: 3D object library from AWS icons (M2)"
date: 2026-10-28
summary: Planned a reusable 3D object library extruded from AWS Architecture Icons 07312026 after the user allowed free modification of the icons.
---

# Plan: 3D object library from AWS icons (M2)

## What happened

User downloaded AWS Architecture Icons (release 07312026) into aws-icon-pkg/ and decided on 2026-10-28 that the icons may be modified freely, including extruding into 3D. This overrides PRD F3.8 (self-drawn default, no modification). Scope: plan only, as part of M2.

Plan: plans/261028-0230-m2-aws-icon-3d-object-library (6 phases, 15.5h): manifest + asset rules, SVG→ExtrudeGeometry pipeline, object/theme design, instanced R3F layer + gallery, perf re-verification with the M0 method, PRD/license updates.

## Findings from scouting the package

- Resource icons are single-path, single-colour, evenodd SVGs: extrudable directly with SVGLoader.
- No icons for Security Group, Key Pair or AZ; almost no dark-background variants for the needed icons.
- Route Table candidates differ a lot in weight (Route 53 Route Table 14 KB path vs VPC Router 1.6 KB).
- aws-icon-pkg/ is untracked; plan adds it to .gitignore and commits only selected SVGs with a NOTICE.

## Risk recorded, not re-litigated

AWS guidelines forbid modifying icons and commercial redistribution is unconfirmed (A5). Kept behind a replaceable icon-pack interface.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
