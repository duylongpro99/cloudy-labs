---
title: M2 AWS icon 3D object library implemented
date: 2026-10-28
summary: "AWS icons extruded into instanced 3D objects; 200-node scene passes Chrome and Safari, draw calls 680 -> 166"
---

# M2 AWS icon 3D object library implemented

## What happened
Executed plans/261028-0230-m2-aws-icon-3d-object-library (6 phases) in web/:
- Manifest of 12 kinds and an import script that copies the selected SVGs plus NOTICE.md. SG uses a self-drawn shield, Key Pair uses the IAM long-term credential icon, and AZ is outline-only.
- SVG -> ExtrudeGeometry, cached per kind. Two InstancedMeshes per kind (plinth and glyph), an easeOutBack entrance, and an Outlines overlay for hover and selection.
- Light and dark tokens with a 3:1 contrast test. Glyph coverage 0.75 was chosen from a 0.6/0.75/0.85 gallery comparison.
- Bench: every config p95 <= 20 ms on Chrome and Safari (Safari full DPR2 at 18 ms). Draw calls 680/448/445 -> 166/113/110. Triangles rose about 7x (30k -> 212k) because of the extruded glyphs. Idle 0 frames.
- PRD v0.7 adds A13 (AWS icons are the default and may be modified), with F3.2/F3.8/A5/risk 5 rewritten; roadmap and license summary updated.

## Lessons
- drei <Outlines> with the default angle rewrites the normals of a non-indexed geometry (RoundedBoxGeometry) in place and disposes it on unmount. Pointed at the shared cached plinth, it corrupted shading and freed live buffers. Fix: a separate creased outlineGeometry cache plus angle={0}, with a regression test.
- Running the full Safari suite in one go lost focus again: 10/12 runs had a max over 1 s. Rerunning one config at a time with an AppleScript activate loop worked; some configs needed 3–4 attempts.
- zsh does not word-split `set -- $var`; run such loops under bash -c.
- Replaced the hard-coded 1800 ms shadow refresh with AwsObjectLayer onSettled.

## Next steps
- Legal review (A5) before public release.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.

## Follow-up (same day)
- Entrance animation now plays only for ids new to the layer (`web/src/scene/aws-objects/entrance.ts`, unit-tested). Ids already shown stay at full size and removed ids are forgotten. The settle callback (static shadow refresh) still fires after every placement change.
- User accepted edge pulses holding still at idle in demand mode, and kept `web/.claude/agent-memory/`.
- PRD fallback for A5 now reads "an icon set from another source with a suitable licence", not necessarily self-drawn.
