import { useTranslation } from 'react-i18next'

interface WelcomeScreenProps {
  onExampleClick: (question: string) => void
}

const examples = [
  'Python 列表推导式是什么？',
  '请解释面向对象编程中的继承和多态',
  '如何用 Python 实现快速排序算法？',
]

export default function WelcomeScreen({ onExampleClick }: WelcomeScreenProps) {
  const { t } = useTranslation()

  return (
    <div className="core-empty h-full flex flex-col items-center justify-center">
      <h2 className="text-2xl font-bold mb-2 text-primary">{t('chat.welcome')}</h2>
      <p className="text-sm mb-8 text-center max-w-md text-secondary">
        {t('chat.welcomeDesc')}
      </p>
      <div className="grid gap-3 w-full max-w-md">
        {examples.map((q, i) => (
          <button
            key={i}
            onClick={() => onExampleClick(q)}
            className="text-left px-4 py-3 rounded-xl border text-sm transition-all duration-200 hover:-translate-y-0.5 border-border bg-bg-secondary text-secondary"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
