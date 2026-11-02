import { motion } from 'framer-motion'
import { BookOpen } from 'lucide-react'
import { useEffect } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'

import { BackToTop, PrevNext } from '../components/docs/PrevNext'
import { DocBlock } from '../components/docs/DocBlock'
import { DocsLayout } from '../components/docs/DocsLayout'
import { EmptyState } from '../components/ui'
import {
  DOC_GROUPS,
  DOC_SECTIONS,
  getAdjacentSections,
  getSection,
  getSectionHeadings,
} from '../content/docs'

export default function Documentation() {
  const { sectionId } = useParams()
  const location = useLocation()

  const currentSection = getSection(sectionId || 'overview')
  const headings = currentSection ? getSectionHeadings(currentSection) : []
  const { prev, next } = currentSection ? getAdjacentSections(currentSection.id) : { prev: null, next: null }

  // Handle deep link / hash scrolling
  useEffect(() => {
    if (location.hash) {
      const id = location.hash.replace('#', '')
      const el = document.getElementById(id)
      if (el) {
        setTimeout(() => {
          el.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [location.pathname, location.hash])

  if (!currentSection) {
    return (
      <DocsLayout groups={DOC_GROUPS} sections={DOC_SECTIONS}>
        <div className="py-12">
          <EmptyState
            title="Section Not Found"
            description={`The requested documentation section "${sectionId}" does not exist.`}
            action={
              <Link to="/documentation" className="btn-primary">
                Back to Documentation Overview
              </Link>
            }
          />
        </div>
      </DocsLayout>
    )
  }

  return (
    <DocsLayout
      groups={DOC_GROUPS}
      sections={DOC_SECTIONS}
      currentSection={currentSection}
      headings={headings}
    >
      <motion.article
        key={currentSection.id}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
        className="space-y-6"
      >
        {/* Section Header */}
        <header className="border-b border-line/60 pb-6 mb-8">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent mb-2">
            <BookOpen className="h-3.5 w-3.5" />
            <span>{currentSection.group}</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-[-0.03em] text-ink sm:text-4xl">
            {currentSection.title}
          </h1>
          {currentSection.summary && (
            <p className="mt-3 text-base leading-relaxed text-muted font-normal">
              {currentSection.summary}
            </p>
          )}
        </header>

        {/* Section Blocks */}
        <div className="space-y-4">
          {currentSection.blocks?.map((block, idx) => (
            <DocBlock key={block.id || `${block.type}-${idx}`} block={block} />
          ))}
        </div>

        {/* Previous / Next Section navigation & Back to top */}
        <div className="pt-8">
          <div className="flex justify-end mb-2">
            <BackToTop />
          </div>
          <PrevNext prev={prev} next={next} />
        </div>
      </motion.article>
    </DocsLayout>
  )
}
