import { Callout } from './Callout'
import { CodeBlock } from './CodeBlock'
import { DefinitionList } from './DefinitionList'
import { Diagram } from './Diagram'
import { DocTable } from './DocTable'
import { FaqList } from './FaqList'
import { HeadingAnchor } from './HeadingAnchor'
import { LinkCard } from './LinkCard'
import { StepList } from './StepList'

export function DocBlock({ block }) {
  if (!block) return null

  switch (block.type) {
    case 'heading':
      return (
        <HeadingAnchor id={block.id} level={block.level || 2}>
          {block.text}
        </HeadingAnchor>
      )

    case 'paragraph':
      return (
        <p className="my-4 text-[0.98rem] leading-[1.75] text-muted">
          {block.text}
        </p>
      )

    case 'list':
      return (
        <ul className="my-4 space-y-2 pl-5 list-disc marker:text-accent text-[0.95rem] leading-relaxed text-muted">
          {block.items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )

    case 'steps':
      return <StepList steps={block.steps} />

    case 'table':
      return <DocTable headers={block.headers} rows={block.rows} caption={block.caption} />

    case 'callout':
      return (
        <Callout tone={block.tone} title={block.title} body={block.body}>
          {block.children}
        </Callout>
      )

    case 'code':
      return (
        <CodeBlock
          code={block.code}
          language={block.language}
          filename={block.filename}
        />
      )

    case 'diagram':
      return <Diagram name={block.name} caption={block.caption} />

    case 'definition-list':
      return <DefinitionList items={block.items} />

    case 'link-card':
      return (
        <LinkCard
          title={block.title}
          description={block.description}
          href={block.href}
          external={block.external}
        />
      )

    case 'faq':
      return <FaqList items={block.items} />

    default:
      return null
  }
}
