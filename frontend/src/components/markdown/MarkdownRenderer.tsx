import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import DOMPurify from 'dompurify'

interface MarkdownRendererProps {
  content: string
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const sanitized = useMemo(
    () => DOMPurify.sanitize(content),
    [content],
  )

  return (
    <div className="markdown-body text-sm leading-relaxed text-primary">
      <ReactMarkdown rehypePlugins={[rehypeRaw]}>{sanitized}</ReactMarkdown>
    </div>
  )
}
