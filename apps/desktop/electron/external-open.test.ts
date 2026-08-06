import { describe, expect, it } from 'vitest'

import { externalOpenTarget, safeMcpElicitationUrl, wslExternalOpenCommand } from './external-open'

describe('wslExternalOpenCommand', () => {
  it('passes an OAuth URL as one argv value without cmd.exe parsing', () => {
    const url = 'https://auth.example.test/connect?a=1&b=2|c^d<e>f'

    expect(wslExternalOpenCommand(url)).toEqual({
      args: [url],
      command: 'explorer.exe'
    })
  })
})

describe('externalOpenTarget', () => {
  it('keeps the exact approved bytes on the trusted native-open path', () => {
    const approved = 'https://auth.example.test'

    expect(externalOpenTarget(approved, new URL(approved), true)).toBe(approved)
    expect(externalOpenTarget(approved, new URL(approved), false)).toBe('https://auth.example.test/')
  })
})

describe('safeMcpElicitationUrl', () => {
  it('preserves exact HTTPS bytes and accepts loopback HTTP', () => {
    expect(safeMcpElicitationUrl('https://auth.example.test')).toBe('https://auth.example.test')
    expect(safeMcpElicitationUrl('http://localhost:8787/callback')).toBe('http://localhost:8787/callback')
  })

  it('rejects public HTTP, userinfo, unsafe schemes, and whitespace', () => {
    expect(safeMcpElicitationUrl('http://example.test/connect')).toBeNull()
    expect(safeMcpElicitationUrl('https://user:secret@example.test/connect')).toBeNull()
    expect(safeMcpElicitationUrl('file:///etc/passwd')).toBeNull()
    expect(safeMcpElicitationUrl(' https://example.test/connect')).toBeNull()
  })

  it('rejects invisible and bidirectional formatting characters', () => {
    expect(safeMcpElicitationUrl('https://example.test/connect\u200bspoofed')).toBeNull()
    expect(safeMcpElicitationUrl('https://example.test/connect\u202eevil')).toBeNull()
  })
})
