import { describe, expect, it } from 'vitest'
import { BuilderError, errorMessage, fetchLab, previewOp, runOp } from './builder-api'

const reply = (status: number, body: unknown) => (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch

describe('builder-api', () => {
  it('sends the typed op as JSON', async () => {
    let seen: RequestInit | undefined
    const fetcher = (async (_: string, init?: RequestInit) => {
      seen = init
      return new Response(JSON.stringify({ command: 'aws ec2 create-vpc', argv: [], problems: [] }))
    }) as unknown as typeof fetch
    const p = await previewOp('create-vpc', { name: 'v', cidr: '10.0.0.0/16' }, fetcher)
    expect(p.command).toBe('aws ec2 create-vpc')
    expect(seen?.method).toBe('POST')
    expect(new Headers(seen?.headers).get('content-type')).toBe('application/json')
    expect(JSON.parse(String(seen?.body))).toEqual({ op: 'create-vpc', params: { name: 'v', cidr: '10.0.0.0/16' } })
  })

  it('reads no open lab as null', async () => {
    expect(await fetchLab(reply(200, { id: null }))).toBeNull()
  })

  it.each([
    [403, { detail: 'builder requests are accepted from the Cloudy Labs web app only' }, 'chỉ nhận lệnh từ web app'],
    [409, { detail: 'no lab is open; run `labctl start <lab>` first' }, 'Lệnh chưa chạy: no lab is open'],
    [422, { detail: "unknown op 'x'" }, "Thao tác không hợp lệ: unknown op 'x'"],
    [503, { detail: 'the aws CLI is not installed' }, 'Chưa chạy được lệnh: the aws CLI'],
  ])('turns %i into a readable message', async (status, body, needle) => {
    const err = await runOp('create-vpc', {}, reply(status, body)).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(BuilderError)
    expect((err as BuilderError).message).toContain(needle)
    expect((err as BuilderError).status).toBe(status)
  })

  it('keeps the problems of a refused run', async () => {
    const problems = [{ field: 'igwId', message: 'already attached' }]
    const err = (await runOp('attach-internet-gateway', {}, reply(409, { detail: 'the command was not run', problems })).catch((e: unknown) => e)) as BuilderError
    expect(err.problems).toEqual(problems)
  })

  it('reports an unreachable server', async () => {
    const down = (async () => {
      throw new TypeError('Failed to fetch')
    }) as unknown as typeof fetch
    const err = (await fetchLab(down).catch((e: unknown) => e)) as BuilderError
    expect(err.status).toBe(0)
    expect(err.message).toContain('labctl serve')
  })

  it('falls back to the status when there is no detail', () => {
    expect(errorMessage(418, undefined)).toBe('lab-server trả lỗi 418')
  })
})
