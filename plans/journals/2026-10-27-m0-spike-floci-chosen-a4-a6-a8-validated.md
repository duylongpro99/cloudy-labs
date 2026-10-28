---
title: "M0 spike: Floci chosen, A4/A6/A8 validated"
date: 2026-10-27
summary: "Executed the M0 spike; Floci 2.3.0 is the primary backend, full post-processing holds 60 fps on Safari at DPR 2, no blocking licenses."
---

# M0 spike: Floci chosen, A4/A6/A8 validated

## What happened

Executed plans/261027-1353-m0-spike-emulator-and-render-validation end to end. Report: plans/reports/spike-261027-2248-m0-validation.md. PRD bumped to v0.5 (A4, A6 verified; F3.7 downgrade level is now `lite`), roadmap marks M0 done.

- Lab 6 + 7 ran 36/36 steps on Floci 2.3.0 and MiniStack 1.5.33. Floci has 38/39 graph fields on this machine; the miss is `PrivateIpAddress`, caused by Floci silently substituting 10.240.0.0/16 when the lab CIDR overlaps an existing Docker network (user's Swarm `ingress` and `ecommerce-net`). Non-overlapping CIDR reports correctly.
- Floci EC2: an IMDS proxy binds 169.254.169.254:80 inside the instance, so a UserData server on 0.0.0.0:80 fails; package install at boot is slow and once timed out (no IMDS). `docker compose down -v` leaves EC2 containers, VPC networks and a volume orphaned; clean by label `io.floci.owner`.
- api-tap (stdlib proxy, Host preserved) is transparent and keeps SigV4 valid against moto; +2.8 ms p50.
- moto 5.2.4 enforces Allow/Deny but ignores `Condition` and has no `simulate-*`; Floci's `simulate-principal-policy` evaluates conditions correctly. moto reset needs `/moto-api/reset` plus `/moto-api/reset-auth` (text/plain bare number). Port 5000 is macOS AirPlay, so moto ran on 5050.
- Render: all 24 configs hit vsync (Chrome p95 9.3 ms, Safari p95 17 ms), idle demand mode renders 0 frames. Licenses: 0 blocking across 95 npm + 84 Python packages.

## Mistakes worth remembering

- drei `<OrthographicCamera makeDefault>` let `CameraControls` bind to R3F's default perspective camera, so camera moves never rendered. The first benchmark orbit would have been a no-op; caught only because a zoom close-up screenshot did not change. Fix: `<Canvas orthographic>`.
- Safari pauses rAF when another app takes focus; three runs were invalidated (moved to results/invalid/ with reasons) and rerun with Safari activated per run.
- A 2 s idle warm-up overlapped the entrance animation and falsely showed 196 idle frames.

## Decision

Floci primary, MiniStack fallback, `full` post-processing default with `PerformanceMonitor` downgrading to `lite`.

## Next steps

- M1: preflight CIDR-overlap warning, orphan cleanup by label, pre-pull `alpine/socat:latest`, moto reset + reset-auth.
- Repeat Floci boots to measure IMDS-proxy failure rate before keeping Lab 8 on Floci.
- A5 (AWS icon license) still awaits legal; non-blocking.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
