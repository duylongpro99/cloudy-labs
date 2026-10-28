import { Canvas } from '@react-three/fiber'
import { useCallback, useMemo, useState } from 'react'
import { NeutralToneMapping } from 'three'
import type { BenchResult } from './bench/bench'
import { CANVAS, nextSuiteUrl, publish, readConfig, resultName, SUITE } from './bench/bench'
import { AwsObjectsGallery, type GalleryConfig } from './gallery/aws-objects-gallery'
import { ArchitectureScene } from './scene/architecture-scene'
import { GLYPH_COVERAGE, type ThemeName } from './scene/aws-objects'

function Stage({ post, dpr, children }: { post: string; dpr: number | [number, number]; children: React.ReactNode }) {
  const postFx = post !== 'flat'
  return (
    <div id="stage" style={CANVAS}>
      <Canvas
        dpr={dpr}
        frameloop="demand"
        // Orthographic from the first render: a drei <OrthographicCamera makeDefault> arrives one
        // effect later, after CameraControls has already bound itself to the default perspective camera.
        orthographic
        camera={{ position: [60, 60, 60], near: -500, far: 1000, zoom: 10 }}
        // three 0.186 dropped PCFSoftShadowMap, R3F's default for `shadows`; ask for PCF explicitly.
        shadows={postFx ? 'percentage' : false}
        // With a composer the ToneMapping effect owns tone mapping; flat mode tone-maps in the renderer.
        flat={postFx}
        gl={{ antialias: false, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => {
          if (!postFx) gl.toneMapping = NeutralToneMapping
        }}
      >
        {children}
      </Canvas>
    </div>
  )
}

function Gallery() {
  const initial = useMemo<GalleryConfig>(() => {
    const q = new URLSearchParams(location.search)
    return {
      theme: q.get('theme') === 'dark' ? 'dark' : 'light',
      coverage: q.has('coverage') ? Number(q.get('coverage')) : GLYPH_COVERAGE,
      post: (['full', 'lite', 'flat'] as const).find((p) => p === q.get('post')) ?? 'full',
      zoom: q.has('zoom') ? Number(q.get('zoom')) : null,
    }
  }, [])
  const [theme, setTheme] = useState<ThemeName>(initial.theme)
  const cfg = { ...initial, theme }
  return (
    <>
      <Stage post={cfg.post} dpr={[1, 2]}>
        <AwsObjectsGallery cfg={cfg} />
      </Stage>
      <div id="panel">
        <b>Thư viện object AWS</b> · glyph phủ {Math.round(cfg.coverage * 100)}% ·{' '}
        <button id="toggle-theme" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
          Chủ đề: {theme === 'light' ? 'sáng' : 'tối'}
        </button>
      </div>
    </>
  )
}

function Scene() {
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
  return (
    <>
      <Stage post={cfg.post} dpr={cfg.mode === 'view' ? [1, 2] : cfg.dpr}>
        <ArchitectureScene cfg={cfg} onDone={onDone} />
      </Stage>
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

export function App() {
  return new URLSearchParams(location.search).get('view') === 'gallery' ? <Gallery /> : <Scene />
}
