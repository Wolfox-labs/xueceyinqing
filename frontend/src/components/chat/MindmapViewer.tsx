import { useEffect, useRef } from 'react'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'

interface MindmapViewerProps {
  content: string
}

export default function MindmapViewer({ content }: MindmapViewerProps) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const mmRef = useRef<Markmap | null>(null)

  useEffect(() => {
    if (!content) return
    const svg = svgRef.current
    if (!svg) return

    const transformer = new Transformer()
    const { root } = transformer.transform(content)

    svg.setAttribute('width', '100%')
    svg.setAttribute('height', '100%')

    requestAnimationFrame(() => {
      if (!svgRef.current) return

      if (mmRef.current) {
        mmRef.current.setData(root)
        mmRef.current.fit()
      } else {
        mmRef.current = Markmap.create(svgRef.current, { autoFit: true }, root)
      }
    })
  }, [content])

  return (
    <div className="w-full" style={{ height: '500px' }}>
      <svg ref={svgRef} style={{ width: '100%', height: '100%', display: 'block' }} />
    </div>
  )
}
