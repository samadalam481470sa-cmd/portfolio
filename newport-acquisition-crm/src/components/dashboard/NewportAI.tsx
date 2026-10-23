import { useState, type FormEvent } from 'react'
import { Sparkles, Send } from 'lucide-react'

/**
 * Newport AI — UI prototype only.
 * Architected for a future AI backend; no external API calls in this sprint.
 */

const SUGGESTED_PROMPTS = [
  'Which deals need attention?',
  'What changed this week?',
  'Show active deals with no next action',
  'Summarize Project Guardian',
] as const

interface NewportAIProps {
  onPrompt?: (prompt: string) => void
}

export function NewportAI({ onPrompt }: NewportAIProps) {
  const [input, setInput] = useState('')
  const [response, setResponse] = useState<string | null>(null)

  const handleSubmit = (prompt: string) => {
    const trimmed = prompt.trim()
    if (!trimmed) return
    setInput(trimmed)
    setResponse(
      'Newport AI will be connected in a future sprint. Your question has been captured for the prototype: “' +
        trimmed +
        '”',
    )
    onPrompt?.(trimmed)
  }

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault()
    handleSubmit(input)
  }

  return (
    <section className="rounded-xl border border-border bg-gradient-to-br from-navy-900 to-navy-800 p-5 text-white shadow-(--shadow-card)">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/25">
          <Sparkles className="h-4 w-4 text-accent-soft" strokeWidth={1.75} />
        </div>
        <div>
          <h2 className="font-brand text-lg font-bold">Newport AI</h2>
          <p className="text-xs text-white/55">Pipeline assistant · prototype</p>
        </div>
      </div>

      <form onSubmit={onFormSubmit} className="relative">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about your acquisition pipeline..."
          className="h-11 w-full rounded-lg border border-white/10 bg-white/10 pr-11 pl-3.5 text-sm text-white outline-none placeholder:text-white/40 focus:border-accent focus:ring-2 focus:ring-accent/30"
          aria-label="Ask Newport AI"
        />
        <button
          type="submit"
          className="absolute top-1/2 right-1.5 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md bg-accent text-white transition-colors hover:bg-accent-hover"
          aria-label="Send"
        >
          <Send className="h-3.5 w-3.5" strokeWidth={2} />
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => handleSubmit(prompt)}
            className="rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[11px] text-white/75 transition-colors hover:bg-white/10 hover:text-white"
          >
            {prompt}
          </button>
        ))}
      </div>

      {response && (
        <p className="mt-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-xs leading-relaxed text-white/80">
          {response}
        </p>
      )}
    </section>
  )
}
