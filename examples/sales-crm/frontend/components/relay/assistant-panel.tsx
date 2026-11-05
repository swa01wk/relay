"use client"

import * as React from "react"
import {
  ArrowUpIcon,
  MicIcon,
  MicOffIcon,
  PhoneOffIcon,
  RotateCcwIcon,
  SparklesIcon,
  Volume2Icon,
  XIcon,
} from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Textarea } from "@/components/ui/textarea"
import { ApprovalCards } from "@/components/relay/approval-cards"
import { AssistantAvatar } from "@/components/relay/assistant-avatar"
import { useRelay } from "@/components/relay/relay-provider"
import { cn } from "@/lib/utils"

const STARTERS = [
  "Chart our pipeline by stage",
  "Which reps are behind quota last quarter?",
  "Show deals in negotiation closing this month",
  "Compare Northwind Logistics and Cobalt Financial",
  "Brief me on Brightpath Health before my call",
]

function StatusBadge() {
  const { connection, voice } = useRelay()
  if (voice === "connected") return <Badge variant="secondary">Voice on</Badge>
  if (connection === "ready") return <Badge variant="outline">Connected</Badge>
  if (connection === "connecting") return <Badge variant="outline">Connecting…</Badge>
  return <Badge variant="destructive">Offline</Badge>
}

export function AssistantPanel() {
  const relay = useRelay()
  const [draft, setDraft] = React.useState("")
  const endRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" })
  }, [relay.messages, relay.liveTranscript, relay.busy, relay.approvals])

  if (!relay.panelOpen) return null
  const ready = relay.connection === "ready"
  const send = (text: string) => {
    if (!text.trim() || !ready) return
    relay.sendText(text)
    setDraft("")
  }
  const voiceOn = relay.voice === "connected"

  return (
    <aside
      className="sticky top-0 hidden h-svh w-[380px] shrink-0 flex-col border-l bg-background lg:flex"
      data-testid="assistant-panel"
      data-relay-ignore // the assistant's own chat input is not a page form for it to fill
    >
      <div className="flex h-(--header-height) items-center gap-2 border-b px-4">
        <SparklesIcon className="size-4" />
        <span className="font-medium">Relay assistant</span>
        <StatusBadge />
        <div className="ml-auto flex items-center">
          <Button variant="ghost" size="icon" className="size-8" onClick={relay.reconnect} aria-label="New conversation">
            <RotateCcwIcon />
          </Button>
          <Button variant="ghost" size="icon" className="size-8" onClick={() => relay.setPanelOpen(false)} aria-label="Close assistant">
            <XIcon />
          </Button>
        </div>
      </div>

      <AssistantAvatar className="border-b py-3" />

      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-3 p-4">
          {relay.messages.length === 0 && (
            <div className="flex flex-col gap-3">
              <p className="text-sm text-muted-foreground">
                Ask about your pipeline, deals, accounts or reps — by text or voice. Tables and charts appear on
                the dashboard.
              </p>
              <div className="flex flex-col gap-2">
                {STARTERS.map((starter) => (
                  <Button
                    key={starter}
                    variant="outline"
                    size="sm"
                    className="h-auto justify-start py-2 text-left whitespace-normal"
                    disabled={!ready}
                    onClick={() => send(starter)}
                  >
                    {starter}
                  </Button>
                ))}
              </div>
            </div>
          )}
          {relay.messages.map((message) => (
            <div
              key={message.id}
              data-testid="chat-message"
              data-role={message.role}
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                message.role === "user"
                  ? "self-end bg-primary text-primary-foreground"
                  : message.role === "system"
                    ? "max-w-full self-center bg-transparent py-0 text-xs text-muted-foreground"
                    : "self-start bg-muted",
              )}
            >
              {message.text}
            </div>
          ))}
          <ApprovalCards />
          {relay.liveTranscript && (
            <div className="max-w-[85%] self-end rounded-lg border border-dashed px-3 py-2 text-sm text-muted-foreground">
              {relay.liveTranscript}
            </div>
          )}
          {relay.busy && !relay.agentSpeaking && (
            <div className="flex gap-1 self-start rounded-lg bg-muted px-3 py-3" aria-label="Assistant is working">
              {[0, 150, 300].map((delay) => (
                <span
                  key={delay}
                  className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
                  style={{ animationDelay: `${delay}ms` }}
                />
              ))}
            </div>
          )}
          <div ref={endRef} />
        </div>
      </ScrollArea>

      {relay.error && (
        <Alert variant="destructive" className="mx-4 mb-2 w-auto">
          <AlertDescription>{relay.error}</AlertDescription>
        </Alert>
      )}
      <Separator />
      <form
        className="flex flex-col gap-2 p-3"
        onSubmit={(event) => {
          event.preventDefault()
          send(draft)
        }}
      >
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              send(draft)
            }
          }}
          placeholder={ready ? "Ask about deals, accounts, reps…" : "Connecting…"}
          disabled={!ready}
          className="max-h-32 min-h-16 resize-none"
          data-testid="assistant-input"
        />
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant={voiceOn ? "secondary" : "outline"}
            size="sm"
            onClick={relay.toggleVoice}
            disabled={!ready}
          >
            {voiceOn ? <PhoneOffIcon /> : <MicIcon />}
            {voiceOn ? "End voice" : relay.voice === "connecting" ? "Starting…" : "Voice"}
          </Button>
          {voiceOn && (
            <Button type="button" variant="ghost" size="icon" className="size-8" onClick={relay.toggleMute} aria-label={relay.micMuted ? "Unmute" : "Mute"}>
              {relay.micMuted ? <MicOffIcon /> : <MicIcon />}
            </Button>
          )}
          {relay.agentSpeaking && <Volume2Icon className="size-4 animate-pulse text-muted-foreground" />}
          <Button type="submit" size="icon" className="ml-auto size-8" disabled={!ready || !draft.trim()} aria-label="Send">
            <ArrowUpIcon />
          </Button>
        </div>
      </form>
    </aside>
  )
}
