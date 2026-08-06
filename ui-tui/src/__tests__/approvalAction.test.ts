import { describe, expect, it } from 'vitest'

import { approvalAction, approvalOptions, approvalPreview } from '../components/prompts.js'

describe('approvalAction — pure key dispatch for ApprovalPrompt', () => {
  it('maps Esc to deny — parity with global Ctrl+C cancellation', () => {
    expect(approvalAction('', { escape: true }, 0)).toEqual({ kind: 'choose', choice: 'deny' })
    expect(approvalAction('', { escape: true }, 2)).toEqual({ kind: 'choose', choice: 'deny' })
  })

  it('maps number keys 1..4 to once/session/always/deny in registration order', () => {
    expect(approvalAction('1', {}, 0)).toEqual({ kind: 'choose', choice: 'once' })
    expect(approvalAction('2', {}, 0)).toEqual({ kind: 'choose', choice: 'session' })
    expect(approvalAction('3', {}, 0)).toEqual({ kind: 'choose', choice: 'always' })
    expect(approvalAction('4', {}, 0)).toEqual({ kind: 'choose', choice: 'deny' })
  })

  it('ignores out-of-range numbers', () => {
    expect(approvalAction('0', {}, 1)).toEqual({ kind: 'noop' })
    expect(approvalAction('5', {}, 1)).toEqual({ kind: 'noop' })
    expect(approvalAction('9', {}, 1)).toEqual({ kind: 'noop' })
  })

  it('confirms the current selection on Enter', () => {
    expect(approvalAction('', { return: true }, 0)).toEqual({ kind: 'choose', choice: 'once' })
    expect(approvalAction('', { return: true }, 3)).toEqual({ kind: 'choose', choice: 'deny' })
  })

  it('moves selection up/down within bounds', () => {
    expect(approvalAction('', { upArrow: true }, 2)).toEqual({ kind: 'move', delta: -1 })
    expect(approvalAction('', { downArrow: true }, 1)).toEqual({ kind: 'move', delta: 1 })
  })

  it('clamps selection movement at the edges', () => {
    expect(approvalAction('', { upArrow: true }, 0)).toEqual({ kind: 'noop' })
    expect(approvalAction('', { downArrow: true }, 3)).toEqual({ kind: 'noop' })
  })

  it('Esc beats numeric/return — denying is always the first interpretation', () => {
    // If a terminal somehow delivers Esc + a digit in the same event, deny
    // wins.  Documents the precedence so a future refactor doesn't flip it.
    expect(approvalAction('1', { escape: true }, 0)).toEqual({ kind: 'choose', choice: 'deny' })
    expect(approvalAction('', { escape: true, return: true }, 1)).toEqual({ kind: 'choose', choice: 'deny' })
  })

  it('returns noop for unrelated keystrokes (printable letters etc.)', () => {
    expect(approvalAction('a', {}, 0)).toEqual({ kind: 'noop' })
    expect(approvalAction(' ', {}, 0)).toEqual({ kind: 'noop' })
  })

  it('respects a reduced option set when permanent allow is disabled', () => {
    // tirith content-security warning present → no "always"; the 3-item set is
    // once/session/deny, so 3 maps to deny and 4 is out of range.
    const opts = ['once', 'session', 'deny'] as const

    expect(approvalAction('3', {}, 0, opts)).toEqual({ kind: 'choose', choice: 'deny' })
    expect(approvalAction('4', {}, 0, opts)).toEqual({ kind: 'noop' })
    expect(approvalAction('', { downArrow: true }, 2, opts)).toEqual({ kind: 'noop' })
    expect(approvalAction('', { return: true }, 2, opts)).toEqual({ kind: 'choose', choice: 'deny' })
  })

  it('offers only once and deny for Smart DENY owner override', () => {
    const opts = approvalOptions({
      allowPermanent: true,
      command: 'rm -rf /',
      description: 'blocked',
      smartDenied: true
    })

    expect(opts).toEqual(['once', 'deny'])
    expect(approvalAction('2', {}, 0, opts)).toEqual({ kind: 'choose', choice: 'deny' })
    expect(approvalAction('3', {}, 0, opts)).toEqual({ kind: 'noop' })
  })

  it('uses explicit gateway choices as the prompt contract', () => {
    expect(
      approvalOptions({
        allowPermanent: true,
        choices: ['once', 'deny'],
        command: 'rm -rf /',
        description: 'blocked'
      })
    ).toEqual(['once', 'deny'])
  })

  it('forces URL mode to once or deny when transport choices are absent', () => {
    expect(
      approvalOptions({
        allowPermanent: false,
        command: 'https://auth.example.test/connect',
        description: 'external interaction',
        elicitationMode: 'url'
      })
    ).toEqual(['once', 'deny'])
  })
})

describe('approvalPreview', () => {
  it('never truncates a URL-mode target before consent', () => {
    const command = `https://auth.example.test/connect?state=${'x'.repeat(1200)}`

    const preview = approvalPreview(
      {
        choices: ['once', 'deny'],
        command,
        description: 'external interaction',
        elicitationMode: 'url',
        serverName: 'workspace'
      },
      80
    )

    expect(preview.overflow).toBe(0)
    expect(preview.shown.join('')).toBe(command)
    expect(preview.shown.length).toBeGreaterThan(10)
  })
})
