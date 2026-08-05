import type { ClarificationQuestion } from '../models/clarification'

type ClarificationReviewProps = {
  questions: ClarificationQuestion[]
  answers: Record<string, string>
  onAnswer: (questionId: string, value: string) => void
  onGenerate: () => void
  onBackToJd: () => void
  isGenerating: boolean
}

export function ClarificationReview({ questions, answers, onAnswer, onGenerate, onBackToJd, isGenerating }: ClarificationReviewProps) {
  const allAnswered = questions.every((question) => Boolean(answers[question.id]))

  return (
    <div className="clarify-panel-wrap">
      <section className="brief-panel clarify-panel" aria-label="Clarifying questions">
        <div className="clarify-intro">
          <p className="workspace__preview-label">A few quick questions</p>
          <p className="clarify-intro__body">
            The job description leaves a little ambiguity. Answer these so the search brief comes out right — nothing else needs typing.
          </p>
        </div>

        {questions.map((question) => (
          <div key={question.id} className="brief-section">
            <h2 className="brief-section__title">{question.question}</h2>
            <div className="brief-segmented" role="radiogroup" aria-label={question.question}>
              {question.options.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`brief-segmented__option${answers[question.id] === option.value ? ' is-active' : ''}`}
                  onClick={() => onAnswer(question.id, option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>

      <div className="brief-actions">
        <button type="button" className="brief-back" onClick={onBackToJd}>
          Back to JD
        </button>

        <button
          type="button"
          className={`workspace__parse${isGenerating ? ' workspace__parse--busy' : ''}`}
          onClick={onGenerate}
          disabled={!allAnswered || isGenerating}
        >
          {isGenerating ? (
            <>
              <span className="workspace__spinner" aria-hidden="true" />
              <span>Understanding the role…</span>
            </>
          ) : (
            <span>Generate Search Brief</span>
          )}
        </button>
      </div>
    </div>
  )
}
