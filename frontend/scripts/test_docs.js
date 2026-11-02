/**
 * Documentation Integrity & Search Verification Script
 * Runs in Node to verify content completeness, anchor validity, and search ranking.
 */

import { DOC_SECTIONS, getSection, getSectionHeadings } from '../src/content/docs/index.js'

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`)
    process.exit(1)
  }
}

console.log('Running Documentation Content Integrity Tests...\n')

// Test 1: Unique section IDs
const sectionIds = new Set()
DOC_SECTIONS.forEach((sec) => {
  assert(!sectionIds.has(sec.id), `Duplicate section ID detected: "${sec.id}"`)
  sectionIds.add(sec.id)
})
console.log(`✓ Test 1: All ${DOC_SECTIONS.length} section IDs are unique.`)

// Test 2: Section titles, groups, and summaries
DOC_SECTIONS.forEach((sec) => {
  assert(sec.title && sec.title.trim().length > 0, `Section "${sec.id}" is missing a title.`)
  assert(sec.group && sec.group.trim().length > 0, `Section "${sec.id}" is missing a group.`)
  assert(sec.summary && sec.summary.trim().length > 10, `Section "${sec.id}" has an invalid or too short summary.`)
})
console.log('✓ Test 2: Every section has non-empty title, group, and summary.')

// Test 3: No empty blocks and valid block types
const VALID_BLOCK_TYPES = new Set([
  'heading', 'paragraph', 'list', 'steps', 'table',
  'callout', 'code', 'diagram', 'definition-list', 'link-card', 'faq',
])

DOC_SECTIONS.forEach((sec) => {
  assert(Array.isArray(sec.blocks) && sec.blocks.length > 0, `Section "${sec.id}" has no blocks.`)
  sec.blocks.forEach((block, idx) => {
    assert(VALID_BLOCK_TYPES.has(block.type), `Section "${sec.id}" block #${idx} has unknown type "${block.type}".`)
    if (block.type === 'heading') {
      assert(block.id && block.text, `Section "${sec.id}" heading block is missing id or text.`)
    } else if (block.type === 'paragraph') {
      assert(block.text && block.text.trim().length > 0, `Section "${sec.id}" paragraph is empty.`)
    } else if (block.type === 'steps') {
      assert(Array.isArray(block.steps) && block.steps.length > 0, `Section "${sec.id}" steps block is empty.`)
      block.steps.forEach((s) => {
        assert(s.title && s.expected, `Step in "${sec.id}" is missing title or expected result line.`)
      })
    } else if (block.type === 'table') {
      assert(Array.isArray(block.headers) && block.headers.length > 0, `Table in "${sec.id}" has no headers.`)
      assert(Array.isArray(block.rows) && block.rows.length > 0, `Table in "${sec.id}" has no rows.`)
    }
  })
})
console.log('✓ Test 3: All blocks have valid types, non-empty content, and required step expected results.')

// Test 4: Headings and anchor resolution
DOC_SECTIONS.forEach((sec) => {
  const headings = getSectionHeadings(sec)
  const headingIds = new Set()
  headings.forEach((h) => {
    assert(!headingIds.has(h.id), `Duplicate heading anchor id "${h.id}" in section "${sec.id}".`)
    headingIds.add(h.id)
  })
})
console.log('✓ Test 4: All heading anchors within sections are unique and valid.')

// Test 5: Search Indexing & Ranking
console.log('\nRunning Client-Side Search Ranking Tests...')

function simulateSearch(query) {
  if (!query.trim()) return []
  const q = query.toLowerCase().trim()
  const terms = q.split(/\s+/).filter(Boolean)

  const items = []
  DOC_SECTIONS.forEach((sec) => {
    items.push({ id: sec.id, title: sec.title, content: `${sec.title} ${sec.summary}` })
    sec.blocks?.forEach((b) => {
      if (b.type === 'heading') {
        items.push({ id: `${sec.id}-${b.id}`, title: b.text, content: b.text })
      } else if (b.type === 'paragraph' && b.text) {
        items.push({ id: `${sec.id}-p`, title: sec.title, content: b.text })
      } else if (b.type === 'definition-list' && b.items) {
        b.items.forEach((item) => {
          items.push({ id: `term-${item.term}`, title: item.term, content: `${item.term} ${item.definition}` })
        })
      }
    })
  })

  return items
    .map((item) => {
      const titleLower = item.title.toLowerCase()
      const contentLower = item.content.toLowerCase()
      let score = 0
      if (titleLower === q) score += 100
      else if (titleLower.startsWith(q)) score += 50
      else if (titleLower.includes(q)) score += 30

      const matchesAll = terms.every((t) => contentLower.includes(t))
      if (!matchesAll) return null

      terms.forEach((t) => {
        if (titleLower.includes(t)) score += 20
        if (contentLower.includes(t)) score += 5
      })
      return { item, score }
    })
    .filter(Boolean)
    .sort((a, b) => b.score - a.score)
    .map((e) => e.item)
}

// 5a: Search for "mock"
const mockResults = simulateSearch('mock')
assert(mockResults.length > 0, 'Search for "mock" returned 0 results.')
console.log(`✓ Test 5a: Search for "mock" returned ${mockResults.length} relevant matches.`)

// 5b: Search for "docker"
const dockerResults = simulateSearch('docker')
assert(dockerResults.length > 0, 'Search for "docker" returned 0 results.')
console.log(`✓ Test 5b: Search for "docker" returned ${dockerResults.length} relevant matches.`)

// 5c: Search for "work unit" (glossary term)
const workUnitResults = simulateSearch('work unit')
assert(workUnitResults.length > 0, 'Search for "work unit" returned 0 results.')
assert(workUnitResults[0].title.toLowerCase().includes('work unit'), 'Search for "work unit" did not rank term first.')
console.log('✓ Test 5c: Search for "work unit" correctly ranked glossary term first.')

// 5d: Search for non-existent gibberish
const noResults = simulateSearch('xyzqwertyunknown')
assert(noResults.length === 0, 'Search for nonsense returned unexpected results.')
console.log('✓ Test 5d: Search for non-matching query correctly returned empty results array.')

console.log('\nAll documentation content and search tests PASSED successfully!')
