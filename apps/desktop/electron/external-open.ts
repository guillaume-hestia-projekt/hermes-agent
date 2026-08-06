/** Build the shell-free Windows URL opener used from WSL. */
export function wslExternalOpenCommand(url: string): { args: string[]; command: 'explorer.exe' } {
  return { args: [url], command: 'explorer.exe' }
}

/** Keep the user's approved bytes when the caller requests consent-preserving navigation. */
export function externalOpenTarget(raw: string, parsed: URL, preserveRaw: boolean): string {
  return preserveRaw ? raw : parsed.toString()
}

/** Trusted-main-process validation for MCP URL-mode elicitation. */
export function safeMcpElicitationUrl(value: unknown): string | null {
  if (
    typeof value !== 'string' ||
    !value ||
    value !== value.trim() ||
    value.length > 2048 ||
    hasUnsafeCharacter(value)
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

  return value
}

function hasUnsafeCharacter(value: string): boolean {
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
