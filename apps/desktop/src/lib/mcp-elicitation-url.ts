/** Revalidate MCP URL-mode elicitation at the renderer-to-native open seam. */
export function safeMcpElicitationUrl(value: string): string | null {
  if (
    typeof value !== 'string' ||
    !value ||
    value !== value.trim() ||
    value.length > 2048 ||
    hasUnsafeMcpUrlCharacter(value)
  ) {
    return null
  }

  let parsed: URL

  try {
    parsed = new URL(value)
  } catch {
    return null
  }

  if (
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    (parsed.protocol !== 'https:' && parsed.protocol !== 'http:')
  ) {
    return null
  }

  if (parsed.protocol === 'http:' && !isLoopbackHostname(parsed.hostname)) {
    return null
  }

  // Preserve the exact value shown during consent; parsing is validation,
  // not permission to rewrite the target before native navigation.
  return value
}

function hasUnsafeMcpUrlCharacter(value: string): boolean {
  return /[\\`<>\s\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(value)
}

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, '')

  if (normalized === 'localhost' || normalized === '::1') {
    return true
  }

  const octets = normalized.split('.')

  return (
    octets.length === 4 && octets[0] === '127' && octets.every(octet => /^\d{1,3}$/.test(octet) && Number(octet) <= 255)
  )
}
