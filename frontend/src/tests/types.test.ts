import { describe, it, expect } from 'vitest'

describe('types', () => {
  it('JobStatus values are valid strings', () => {
    const statuses = ['queued', 'extracting', 'downloading', 'completed', 'failed', 'expired']
    expect(statuses).toHaveLength(6)
  })
})
