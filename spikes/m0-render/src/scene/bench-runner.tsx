// Drives the camera along a fixed orbit, forces a frame every rAF and records frame times.
// In idle mode it does nothing except count how many frames demand mode still renders.
import type { CameraControls } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import type { BenchConfig, BenchResult, FrameSample } from '../bench'
import { summarize } from '../bench'

const ORBIT_DEG_PER_S = 30

export function BenchRunner({ cfg, controls, onDone }: {
  cfg: BenchConfig
  controls: React.RefObject<CameraControls | null>
  onDone: (r: BenchResult) => void
}) {
  const gl = useThree((s) => s.gl)
  const invalidate = useThree((s) => s.invalidate)
  const state = useRef({ start: 0, last: 0, done: false, samples: [] as FrameSample[], renders: 0 })

  useEffect(() => {
    gl.info.autoReset = false // composer renders several passes; count them all per frame
    state.current.start = performance.now()
    if (cfg.mode !== 'bench') return
    let raf = 0
    const tick = () => {
      invalidate()
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [cfg.mode, gl, invalidate])

  useFrame((_, delta) => {
    const s = state.current
    if (s.done) return
    const now = performance.now()
    const elapsed = now - s.start
    if (cfg.mode === 'bench') {
      controls.current?.rotate((ORBIT_DEG_PER_S * Math.PI / 180) * delta, 0, false)
      if (elapsed > cfg.warmupMs && s.last) {
        s.samples.push({ dt: now - s.last, calls: gl.info.render.calls, triangles: gl.info.render.triangles })
      }
    } else if (elapsed > cfg.warmupMs) {
      s.renders++
    }
    s.last = now
    gl.info.reset()
    if (elapsed > cfg.warmupMs + cfg.durationMs) {
      s.done = true
      const programs = gl.info.programs?.length ?? 0
      const ctx = gl.getContext()
      const dbg = ctx.getExtension('WEBGL_debug_renderer_info')
      onDone(summarize(cfg, s.samples, {
        programs,
        rendererPixelRatio: gl.getPixelRatio(),
        gpu: dbg ? ctx.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : ctx.getParameter(ctx.RENDERER),
        ...(cfg.mode === 'idle' ? { idleFramesRendered: s.renders, idleWindowMs: cfg.durationMs } : {}),
      }))
    }
  })

  // Idle mode never invalidates, so useFrame may never fire again; finish on a timer.
  useEffect(() => {
    if (cfg.mode !== 'idle') return
    const t = setTimeout(() => {
      const s = state.current
      if (s.done) return
      s.done = true
      onDone(summarize(cfg, [], { programs: gl.info.programs?.length ?? 0, idleFramesRendered: s.renders, idleWindowMs: cfg.durationMs }))
    }, cfg.warmupMs + cfg.durationMs + 50)
    return () => clearTimeout(t)
  }, [cfg, gl, onDone])

  return null
}
