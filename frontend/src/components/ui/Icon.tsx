import type { SVGProps } from 'react'

export type IconName =
  | 'dashboard'
  | 'path'
  | 'resource'
  | 'assessment'
  | 'report'
  | 'assistant'
  | 'profile'
  | 'sun'
  | 'moon'
  | 'activity'
  | 'clock'
  | 'arrow'

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName
  size?: number
}

export default function Icon({ name, size = 18, ...props }: IconProps) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      {...props}
    >
      {name === 'dashboard' && (
        <g {...common}>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="4" rx="1.5" />
          <rect x="14" y="11" width="7" height="10" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
        </g>
      )}
      {name === 'path' && (
        <g {...common}>
          <circle cx="5" cy="18" r="2.3" />
          <circle cx="12" cy="6" r="2.3" />
          <circle cx="19" cy="15" r="2.3" />
          <path d="M6.7 16.2 10.3 8m3.3-1.2 4.1 6.1M7.2 18h9.4" />
        </g>
      )}
      {name === 'resource' && (
        <g {...common}>
          <path d="M5 4.5h10.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3V4.5Z" />
          <path d="M8 4.5v15.5M12 9h3.5M12 13h3.5" />
        </g>
      )}
      {name === 'assessment' && (
        <g {...common}>
          <rect x="4" y="3" width="16" height="18" rx="2" />
          <path d="m8 9 1.5 1.5L12 8m-4 7 1.5 1.5L12 14" />
          <path d="M14 10h2.5M14 16h2.5" />
        </g>
      )}
      {name === 'report' && (
        <g {...common}>
          <path d="M4 20V10m5 10V4m5 16v-7m5 7V7" />
          <path d="M3 20h18" />
        </g>
      )}
      {name === 'assistant' && (
        <g {...common}>
          <rect x="4" y="6" width="16" height="12" rx="3" />
          <path d="M12 3v3M8.5 11h.01M15.5 11h.01M8.5 15h7" />
        </g>
      )}
      {name === 'profile' && (
        <g {...common}>
          <circle cx="12" cy="8" r="3.5" />
          <path d="M5 20c.8-4 3.1-6 7-6s6.2 2 7 6" />
        </g>
      )}
      {name === 'sun' && (
        <g {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </g>
      )}
      {name === 'moon' && (
        <g {...common}>
          <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
        </g>
      )}
      {name === 'activity' && (
        <g {...common}>
          <path d="M3 12h4l2.2-6 3.4 12 2.7-8 1.7 2h4" />
        </g>
      )}
      {name === 'clock' && (
        <g {...common}>
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7v5l3 2" />
        </g>
      )}
      {name === 'arrow' && (
        <g {...common}>
          <path d="M5 12h14M14 7l5 5-5 5" />
        </g>
      )}
    </svg>
  )
}
