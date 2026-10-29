import { Canvas } from '@react-three/fiber'
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { NeutralToneMapping } from 'three'
import type { BenchResult } from './bench/bench'
import { CANVAS, nextSuiteUrl, publish, readConfig, resultName, SUITE } from './bench/bench'
import { BuilderPanel } from './builder/builder-panel'
import { kindLabel } from './builder/drop-targets'
import { DragGhost, Palette } from './builder/palette'
import { useLab } from './builder/use-lab'
import { useSceneBuilder } from './builder/use-scene-builder'
import { AwsObjectsGallery, type GalleryConfig } from './gallery/aws-objects-gallery'
import { useResourceGraph, type ConnectionState } from './graph/graph-client'
import { graphToScene } from './graph/graph-to-scene'
import { ArchitectureScene } from './scene/architecture-scene'
import { GLYPH_COVERAGE, type ThemeName } from './scene/aws-objects'
import { LiveScene } from './scene/live-scene'
import { PropertyPanel } from './scene/property-panel'
import { THEMES } from './scene/theme'

function Stage({
  post,
  dpr,
  style = CANVAS,
  onPointerMissed,
  children,
}: {
  post: string
  dpr: number | [number, number]
  style?: CSSProperties
  onPointerMissed?: () => void
  children: React.ReactNode
}) {
  const postFx = post !== 'flat'
  return (
    <div id="stage" style={style}>
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
        onPointerMissed={onPointerMissed}
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

function Bench() {
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

// Theme follows the system setting and its changes until the learner picks one by hand (F3.9).
function useThemePreference(): [ThemeName, () => void] {
  const query = useMemo(() => matchMedia('(prefers-color-scheme: dark)'), [])
  const [system, setSystem] = useState<ThemeName>(query.matches ? 'dark' : 'light')
  const [manual, setManual] = useState<ThemeName | null>(null)
  useEffect(() => {
    const onChange = (e: MediaQueryListEvent) => setSystem(e.matches ? 'dark' : 'light')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [query])
  const theme = manual ?? system
  return [theme, () => setManual(theme === 'light' ? 'dark' : 'light')]
}

const STATE_LABEL: Record<ConnectionState, string> = {
  connecting: 'Đang kết nối lab-server…',
  live: 'Đang cập nhật trực tiếp',
  'emulator-down': 'Emulator không phản hồi (chạy labctl up)',
  disconnected: 'Mất kết nối lab-server (chạy labctl serve), đang thử lại…',
}

// index.html gives #stage the benchmark's fixed size; the live view fills the window instead.
const FULL_SCREEN: CSSProperties = { position: 'fixed', inset: 0, width: '100%', height: '100%' }

function Live() {
  const { graph, state, events } = useResourceGraph()
  const scene = useMemo(() => (graph ? graphToScene(graph) : null), [graph])
  const [theme, toggleTheme] = useThemePreference()
  const [fitKey, setFitKey] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const close = useCallback(() => setSelected(null), [])
  const t = THEMES[theme]
  const { lab, error: labError, loaded } = useLab()
  const builder = useSceneBuilder(graph, scene, lab, selected)
  const bs = builder.state
  const gesture = bs.phase === 'dragging' || bs.phase === 'connecting' ? bs : null
  const working = bs.phase === 'running' || bs.phase === 'waiting'
  return (
    <>
      {scene && (
        <Stage post="full" dpr={[1, 2]} style={FULL_SCREEN} onPointerMissed={close}>
          <LiveScene
            scene={scene}
            events={events}
            theme={theme}
            fitKey={fitKey}
            selected={selected}
            onSelect={setSelected}
            builder={lab && graph?.status === 'ok' ? builder.scene : undefined}
          />
        </Stage>
      )}
      {scene && graph && selected && (
        <PropertyPanel selected={selected} scene={scene} edges={graph.edges} theme={t} onClose={close} actions={lab ? builder.actionsFor(selected) : []} />
      )}
      {lab && 'draft' in bs && (
        <BuilderPanel state={bs} graph={graph} lab={lab} theme={t} dispatch={builder.dispatch} onRun={builder.run} />
      )}
      {gesture && (
        <DragGhost
          kind={gesture.phase === 'dragging' ? gesture.kind : null}
          ok={gesture.hover !== null}
          hint={
            gesture.reason ??
            (gesture.hover
              ? `Thả vào ${scene?.nodesById.get(gesture.hover)?.label ?? gesture.hover}`
              : gesture.phase === 'dragging'
                ? `Kéo ${kindLabel(gesture.kind)} vào chỗ được tô sáng`
                : 'Kéo tới đích được tô sáng')
          }
          theme={t}
        />
      )}
      <div id="live-panel" style={{ position: 'fixed', top: 12, left: 12, maxWidth: 520, padding: '8px 12px', borderRadius: 8, background: t.background, color: t.label, boxShadow: '0 1px 4px rgba(0,0,0,.25)' }}>
        <div>
          <b>Cloudy Labs</b> · <span id="connection-state" data-state={state}>{STATE_LABEL[state]}</span>
          {graph && <> · phiên bản {graph.version} · {graph.nodes.length} tài nguyên</>}
        </div>
        <div style={{ marginTop: 6 }}>
          <button id="fit-view" onClick={() => setFitKey((k) => k + 1)}>Vừa khung</button>
          <button id="toggle-theme" onClick={toggleTheme}>Chủ đề: {theme === 'light' ? 'sáng' : 'tối'}</button>
        </div>
        {lab ? (
          <div id="builder-lab" style={{ marginTop: 8 }}>
            <div>
              Lab <b>{lab.title}</b> · lần làm {lab.attempt}
            </div>
            <Palette lab={lab} disabled={working || graph?.status !== 'ok'} onStart={builder.startDrag} />
            {bs.phase === 'idle' && bs.notice && (
              <p id="builder-notice" role="status" style={{ margin: '6px 0 0' }}>
                {bs.notice}
              </p>
            )}
          </div>
        ) : (
          loaded && (
            <p id="builder-lab" style={{ margin: '8px 0 0', opacity: 0.8 }}>
              {labError ?? 'Chưa mở lab nào; chạy labctl start <lab> để kéo tài nguyên vào cảnh.'}
            </p>
          )
        )}
        {graph && graph.warnings.length > 0 && (
          <ul id="graph-warnings" style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {graph.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        )}
      </div>
    </>
  )
}

export function App() {
  const view = new URLSearchParams(location.search).get('view')
  return view === 'gallery' ? <Gallery /> : view === 'bench' ? <Bench /> : <Live />
}
