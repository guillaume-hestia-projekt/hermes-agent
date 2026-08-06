import { describe, expect, it } from 'vitest'

import { safeMcpElicitationUrl } from './mcp-elicitation-url'

describe('safeMcpElicitationUrl', () => {
  it('accepts HTTPS and loopback HTTP', () => {
    expect(safeMcpElicitationUrl('https://auth.example.test/connect?state=opaque')).toBe(
      'https://auth.example.test/connect?state=opaque'
    )
    expect(safeMcpElicitationUrl('http://localhost:8787/callback')).toBe('http://localhost:8787/callback')
    expect(safeMcpElicitationUrl('http://127.0.0.2/callback')).toBe('http://127.0.0.2/callback')
    expect(safeMcpElicitationUrl('http://[::1]/callback')).toBe('http://[::1]/callback')
    expect(safeMcpElicitationUrl('https://auth.example.test')).toBe('https://auth.example.test')
  })

  it('rejects public HTTP and credential-bearing URLs', () => {
    expect(safeMcpElicitationUrl('http://example.test/connect')).toBeNull()
    expect(safeMcpElicitationUrl('https://user:secret@example.test/connect')).toBeNull()
  })

  it('rejects whitespace, unsafe schemes, and oversized values', () => {
    expect(safeMcpElicitationUrl(' https://example.test/connect')).toBeNull()
    expect(safeMcpElicitationUrl('file:///etc/passwd')).toBeNull()
    expect(safeMcpElicitationUrl(`https://example.test/${'a'.repeat(2049)}`)).toBeNull()
  })

  it('rejects invisible and bidirectional formatting characters', () => {
    expect(safeMcpElicitationUrl('https://example.test/connect\u200bspoofed')).toBeNull()
    expect(safeMcpElicitationUrl('https://example.test/connect\u202eevil')).toBeNull()
  })
})
