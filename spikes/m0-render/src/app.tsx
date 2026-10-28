import { Canvas } from '@react-three/fiber'
import { useCallback, useMemo, useState } from 'react'
import { NeutralToneMapping } from 'three'
import type { BenchResult } from './bench'
import { CANVAS, nextSuiteUrl, publish, readConfig, resultName, SUITE } from './bench'
import { ArchitectureScene } from './scene/architecture-scene'

export function App() {
  const cfg = useMemo(() => readConfig(), [])
  const [result, setResult] = useState<BenchResult | null>(null)

  const onDone = useCallback(
    async (r: BenchResult) => {
      setResult(r)
      await publish(r)
      const next = nextSuiteUrl(cfg)
      if (next) location.href = next
      else if (cfg.suiteIndex !== null) document.title = 'SUITE DONE'
    },
    [cfg],
  )

  const download = result && URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
  const postFx = cfg.post !== 'flat'
  return (
    <>
      <div id="stage" style={CANVAS}>
        <Canvas
          dpr={cfg.mode === 'view' ? [1, 2] : cfg.dpr}
          frameloop="demand"
          // Orthographic from the first render: a drei <OrthographicCamera makeDefault> arrives one
          // effect later, after CameraControls has already bound itself to the default perspective camera.
          orthographic
          camera={{ position: [60, 60, 60], near: -500, far: 1000, zoom: 10 }}
          shadows={postFx}
          // With a composer the ToneMapping effect owns tone mapping; flat mode tone-maps in the renderer.
          flat={postFx}
          gl={{ antialias: false, powerPreference: 'high-performance' }}
          onCreated={({ gl }) => {
            if (!postFx) gl.toneMapping = NeutralToneMapping
          }}
        >
          <ArchitectureScene cfg={cfg} onDone={onDone} />
        </Canvas>
      </div>
      <div id="panel">
        <b>{cfg.mode}</b> post={cfg.post} theme={cfg.theme} dpr={cfg.dpr} run={cfg.run}
        {cfg.suiteIndex !== null && <> · suite {cfg.suiteIndex + 1}/{SUITE.length}</>}
        {result ? (
          <>
            {' '}· <a id="download" href={download!} download={`${resultName(result)}.json`}>tải JSON</a>
            <pre id="result">{JSON.stringify(result, null, 2)}</pre>
          </>
        ) : (
          cfg.mode !== 'view' && <> · đang đo… ({(cfg.warmupMs + cfg.durationMs) / 1000}s)</>
        )}
      </div>
    </>
  )
}
