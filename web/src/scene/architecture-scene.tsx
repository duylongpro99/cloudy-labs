// Benchmark scene: a seeded 200-node resource graph drawn through the live path
// (graphToScene -> layout) with the shared scene rig.
// Resources are drawn by the AWS object library; trays, edges and labels stay scene layers.
import { CameraControls } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { BenchConfig, BenchResult } from '../bench/bench'
import { graphToScene } from '../graph/graph-to-scene'
import { mergeTwin } from '../graph/merge-twin'
import { syntheticGraph, syntheticTwin } from '../graph/synthetic-graph'
import { BenchRunner } from '../bench/bench-runner'
import { AwsObjectLayer } from './aws-objects'
import { EdgeLayer } from './edge-layer'
import { LabelLayer } from './label-layer'
import { computeLayout } from './layout'
import { edgeAnchors, scenePlacements } from './object-placements'
import { frameBounds, PostFx, SceneRig, useSceneProbe, useStaticShadows } from './scene-rig'
import { THEMES } from './theme'
import { TrayLayer } from './tray-layer'

export function ArchitectureScene({ cfg, onDone }: { cfg: BenchConfig; onDone: (r: BenchResult) => void }) {
  const theme = THEMES[cfg.theme]
  const fixture = useMemo(() => {
    const graph = syntheticGraph(42)
    const scene = graphToScene(graph)
    return cfg.ghosts ? mergeTwin(scene, syntheticTwin(graph, cfg.ghosts), true).scene : scene
  }, [cfg.ghosts])
  const layout = useMemo(() => computeLayout(fixture), [fixture])
  const placements = useMemo(() => scenePlacements(fixture, layout), [fixture, layout])
  const anchors = useMemo(() => edgeAnchors(placements), [placements])
  const [hovered, setHovered] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(cfg.mode === 'view' ? null : 'i-000')
  const controls = useRef<CameraControls>(null)
  const invalidate = useThree((s) => s.invalidate)
  const size = useThree((s) => s.size)
  const shadows = cfg.post !== 'flat'

  useLayoutEffect(() => {
    if (!controls.current) return
    return frameBounds(controls.current, layout.bounds, size, invalidate, cfg.zoom)
  }, [cfg.zoom, invalidate, layout.bounds, size])

  const refreshShadows = useStaticShadows()
  useSceneProbe(placements, hovered, selected)

  return (
    <>
      <SceneRig theme={theme} bounds={layout.bounds} shadows={shadows} controls={controls} />
      <TrayLayer groups={layout.groups} theme={theme} />
      <AwsObjectLayer
        placements={placements}
        theme={cfg.theme}
        shadows={shadows}
        hovered={hovered}
        selected={selected}
        outlineColor={theme.outline}
        onHover={setHovered}
        onSelect={setSelected}
        onSettled={refreshShadows}
      />
      <LabelLayer leaves={layout.leaves} theme={theme} />
      <EdgeLayer edges={fixture.edges} anchors={anchors} theme={theme} />
      <PostFx level={cfg.post} />
      {cfg.mode !== 'view' && <BenchRunner cfg={cfg} controls={controls} onDone={onDone} />}
    </>
  )
}
