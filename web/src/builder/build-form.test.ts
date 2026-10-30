import { describe, expect, it } from 'vitest'
import { userDataHint } from './build-form'
import { pemOf } from './command-panel'

describe('userDataHint', () => {
  it('warns about a server that binds 0.0.0.0:80', () => {
    for (const script of ['python3 -m http.server 80', 'nginx -g "listen 0.0.0.0:80;"', 'python3 -m http.server 80 --bind 0.0.0.0']) {
      expect(userDataHint(script)).toContain('IMDS')
    }
  })

  it('stays quiet for a server bound to the instance addresses, and for comments', () => {
    expect(userDataHint('IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)\npython3 -m http.server 80 ${IP:+--bind $IP}')).toBeNull()
    expect(userDataHint('# IMDS holds 0.0.0.0:80\nfor IP in $(ip -4 -o addr); do\n  python3 -m http.server 80 --bind "$IP" &\ndone')).toBeNull()
    expect(userDataHint('')).toBeNull()
  })
})

describe('pemOf', () => {
  const ran = (stdout: string, exitCode: number | null = 0) => ({ command: '', exitCode, stdout, stderr: '', durationMs: 1, expect: null })
  const key = JSON.stringify({ KeyName: 'lab07-key', KeyMaterial: '-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----', KeyPairId: 'key-1' })

  it('offers the private key create-key-pair printed', () => {
    expect(pemOf('create-key-pair', ran(key))).toEqual({ name: 'lab07-key', key: JSON.parse(key).KeyMaterial })
  })

  it('offers nothing for other ops, failures or output without a key', () => {
    expect(pemOf('create-vpc', ran(key))).toBeNull()
    expect(pemOf('create-key-pair', ran(key, 254))).toBeNull()
    expect(pemOf('create-key-pair', ran('{"KeyName": "x"}'))).toBeNull()
    expect(pemOf('create-key-pair', ran('not json'))).toBeNull()
    expect(pemOf('create-key-pair', null)).toBeNull()
  })
})
