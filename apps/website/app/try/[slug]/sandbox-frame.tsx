"use client"

import { LightbulbIcon, PanelRightCloseIcon, PanelRightOpenIcon } from "lucide-react"
import { useState } from "react"

import { CopyButton } from "@/components/copy-button"
import type { Example } from "@/lib/examples"

/**
 * The example app in an iframe, with things to try beside it. The app runs on its own origin
 * in sandbox mode; `allow="microphone"` lets voice work inside the frame.
 */
export function SandboxFrame({ example }: { example: Example }) {
  const [guideOpen, setGuideOpen] = useState(true)
  const [loaded, setLoaded] = useState(false)

  return (
    <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
      <div className="relative min-h-0 flex-1 bg-sunken">
        {!loaded && (
          <div className="absolute inset-0 grid place-items-center font-mono text-sm text-faint">
            Starting your sandbox…
          </div>
        )}
        <iframe
          src={example.url}
          title={`${example.name} demo`}
          allow="microphone; autoplay; clipboard-write"
          className="relative size-full border-0"
          onLoad={() => setLoaded(true)}
        />
      </div>
      <aside
        className={`shrink-0 border-line bg-bg max-lg:border-t lg:border-l ${guideOpen ? "lg:w-80" : "lg:w-11"}`}
        aria-label="Things to try"
      >
        <div className="flex items-center gap-2 px-3 py-2">
          {guideOpen && (
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <LightbulbIcon className="size-4 text-accent" /> Things to try
            </h2>
          )}
          <button
            type="button"
            onClick={() => setGuideOpen((o) => !o)}
            className="ml-auto rounded-md p-1.5 text-faint hover:bg-raised hover:text-fg"
            aria-label={guideOpen ? "Hide suggestions" : "Show suggestions"}
            aria-expanded={guideOpen}
          >
            {guideOpen ? <PanelRightCloseIcon className="size-4" /> : <PanelRightOpenIcon className="size-4" />}
          </button>
        </div>
        {guideOpen && (
          <div className="max-h-[32vh] space-y-5 overflow-y-auto px-3 pb-4 lg:max-h-none">
            <p className="text-xs text-muted">
              Say these out loud with voice on, or paste them into the assistant. Changes you make stay in your
              sandbox — use <span className="text-fg">Reset demo</span> in the app to start over.
            </p>
            <ol className="space-y-2">
              {example.prompts.map((prompt) => (
                <li key={prompt} className="flex items-start gap-1 rounded-lg border border-line bg-raised py-2 pr-1 pl-3 text-sm">
                  <span className="flex-1 pt-0.5">{prompt}</span>
                  <CopyButton text={prompt} label="Copy prompt" />
                </li>
              ))}
            </ol>
            <div>
              <h3 className="font-mono text-[11px] uppercase tracking-wider text-faint">What to watch for</h3>
              <ul className="mt-2 space-y-1.5 text-sm text-muted">
                {example.highlights.map((h) => (
                  <li key={h}>› {h}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </aside>
    </div>
  )
}
