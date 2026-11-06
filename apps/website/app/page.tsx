import {
  ArrowRightIcon,
  AudioLinesIcon,
  BadgeCheckIcon,
  ChartColumnIcon,
  FormInputIcon,
  KeyRoundIcon,
  MicIcon,
  MousePointerClickIcon,
  ShieldCheckIcon,
  WaypointsIcon,
} from "lucide-react"
import Link from "next/link"

import { CopyButton } from "@/components/copy-button"
import { EventStream } from "@/components/event-stream"
import { Footer } from "@/components/footer"
import { Nav } from "@/components/nav"
import { examples } from "@/lib/examples"

const INSTALL = "npm install @sumukhj1219-wkt-org/relay-web-sdk"

export default function Home() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <WhyNow />
        <HowItWorks />
        <Capabilities />
        <UseCases />
        <Developers />
        <Pricing />
        <ClosingCta />
      </main>
      <Footer />
    </>
  )
}

function SectionHeading({ eyebrow, title, children }: { eyebrow: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="max-w-2xl">
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">{title}</h2>
      {children && <p className="mt-4 text-pretty text-muted">{children}</p>}
    </div>
  )
}

function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-line">
      <div className="grid-bg pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-6xl gap-12 px-4 pt-16 pb-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pt-24 lg:pb-28">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-line-strong bg-raised px-3 py-1 font-mono text-xs text-muted">
            <span className="size-1.5 rounded-full bg-accent" /> Preview · voice + text
          </p>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
            Your users talk.
            <br />
            <span className="text-accent">Your app acts.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg text-pretty text-muted">
            Relay is a realtime assistant layer for the product you already have. It hears a request, calls your
            tools, and drives your own UI&nbsp;— navigation, filters, charts, forms and approved changes. No widget
            bolted on top.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/try"
              className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
            >
              <MicIcon className="size-4" /> Try a live demo
            </Link>
            <a
              href="#how"
              className="inline-flex items-center gap-2 rounded-md border border-line-strong px-4 py-2.5 text-sm transition-colors hover:bg-raised"
            >
              How it works <ArrowRightIcon className="size-4" />
            </a>
          </div>
          <div className="mt-8 flex max-w-md items-center gap-2 rounded-md border border-line bg-sunken py-1.5 pr-1.5 pl-3 font-mono text-[13px]">
            <span className="text-faint">$</span>
            <span className="truncate">{INSTALL}</span>
            <CopyButton text={INSTALL} label="Copy install command" className="ml-auto" />
          </div>
        </div>
        <EventStream />
      </div>
    </section>
  )
}

function WhyNow() {
  const beats = [
    {
      title: "People already talk to software",
      body: "Phones, cars, speakers. Then they open your app and go back to hunting through menus.",
    },
    {
      title: "Chatbots answer; they don't act",
      body: "A text box beside the product can explain a screen. It can't filter the table, fill the form or file the change.",
    },
    {
      title: "Relay works inside the app",
      body: "The assistant uses the same actions your buttons use, so what it does is visible, undoable and under the user's control.",
    },
  ]
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="Why now" title="Clicks are the bottleneck, not the answers." />
        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line md:grid-cols-3">
          {beats.map((b, i) => (
            <div key={b.title} className="bg-bg p-6">
              <p className="font-mono text-xs text-faint">0{i + 1}</p>
              <h3 className="mt-3 font-medium">{b.title}</h3>
              <p className="mt-2 text-sm text-muted">{b.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function HowItWorks() {
  const steps = [
    { n: "1", title: "They speak or type", body: "The Web SDK streams the microphone over WebRTC, or text over a WebSocket." },
    { n: "2", title: "Relay listens", body: "Turn-taking, transcription and interruptions handled on the gateway." },
    { n: "3", title: "Your backend decides", body: "The model calls your tools service. Your data, your validation, your permissions." },
    { n: "4", title: "Your app speaks and acts", body: "Typed events drive your UI: navigate, filter, show a chart, fill a form, ask for approval." },
  ]
  return (
    <section id="how" className="scroll-mt-14 border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="How it works" title="Three parts. You keep two of them.">
          Your frontend and your tools service stay yours. Relay runs the realtime session in between and speaks a
          typed protocol to both.
        </SectionHeading>

        <div className="mt-12 grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1.2fr_auto_1fr]">
          <ArchBox
            label="Your app"
            sub="Relay Web SDK"
            items={["Microphone + chat", "Registered screen actions", "Renders surfaces with your components"]}
          />
          <ArchArrow top="speech · text · state" bottom="events · actions" />
          <ArchBox
            accent
            label="Relay gateway"
            sub="hosted"
            items={["Speech in / speech out", "LLM + tool loop", "Approvals before any write", "Traces and metrics per turn"]}
          />
          <ArchArrow top="signed tool calls" bottom="JSON results" />
          <ArchBox
            label="Your tools service"
            sub="any language"
            items={["GET /tools — discovery", "POST /tools/{name}", "Your rules, your database"]}
          />
        </div>

        <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <li key={s.n} className="border-t border-line-strong pt-4">
              <span className="font-mono text-sm text-accent">{s.n}</span>
              <h3 className="mt-2 font-medium">{s.title}</h3>
              <p className="mt-1.5 text-sm text-muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

function ArchBox({ label, sub, items, accent }: { label: string; sub: string; items: string[]; accent?: boolean }) {
  return (
    <div className={`rounded-xl border p-5 ${accent ? "border-accent/40 bg-accent-soft" : "border-line-strong bg-raised"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-medium">{label}</h3>
        <span className="font-mono text-[11px] text-faint">{sub}</span>
      </div>
      <ul className="mt-4 space-y-2 text-sm text-muted">
        {items.map((item) => (
          <li key={item} className="flex gap-2">
            <span className={accent ? "text-accent" : "text-faint"}>›</span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ArchArrow({ top, bottom }: { top: string; bottom: string }) {
  return (
    <div className="flex flex-row items-center justify-center gap-3 py-1 font-mono text-[11px] text-faint lg:flex-col lg:gap-1 lg:px-1">
      <span>{top}</span>
      <span className="text-accent lg:hidden" aria-hidden="true">
        ⇅
      </span>
      <span className="hidden text-accent lg:block" aria-hidden="true">
        ⇄
      </span>
      <span>{bottom}</span>
    </div>
  )
}

function Capabilities() {
  const items = [
    { icon: AudioLinesIcon, title: "Barge-in that remembers what was heard", body: "Interrupt mid-sentence; the conversation keeps only the words that were actually spoken." },
    { icon: MousePointerClickIcon, title: "Screen actions", body: "Navigation, filters, sorting, opening records — the assistant calls the actions your app registers." },
    { icon: ChartColumnIcon, title: "Generated UI, rendered by you", body: "Tables, charts, comparisons and cards arrive as typed data. Your design system draws them." },
    { icon: FormInputIcon, title: "Form filling", body: "Values the user says land in your form's inputs. Nothing submits on its own." },
    { icon: BadgeCheckIcon, title: "Approve → commit → verify", body: "Tools that change data only run after a person approves that exact change." },
    { icon: ShieldCheckIcon, title: "Signed, per-user tool calls", body: "Every call is signed and says which of your users it is for, so tools return only their data." },
    { icon: KeyRoundIcon, title: "Your model key, per project", body: "Each project runs on its own agent, tools URL and model key. Nothing is shared." },
    { icon: WaypointsIcon, title: "A trace for every turn", body: "See what was heard, which tools ran and where the time went: relay logs <session>." },
  ]
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="What Relay handles" title="The parts that take months, done once.">
          Turn-taking, interruptions, latency, approvals, tenancy. You write tools and register actions.
        </SectionHeading>
        <div className="mt-12 grid gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
          {items.map(({ icon: Icon, title, body }) => (
            <div key={title} className="bg-bg p-6">
              <Icon className="size-5 text-accent" aria-hidden="true" />
              <h3 className="mt-4 text-sm font-medium">{title}</h3>
              <p className="mt-2 text-sm text-muted">{body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function UseCases() {
  return (
    <section className="border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <SectionHeading eyebrow="Experience Center" title="Don't take our word for it. Talk to one.">
            Real apps running on Relay. Each visitor gets a private copy of the data, so go ahead and change things.
          </SectionHeading>
          <Link href="/try" className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline">
            All examples <ArrowRightIcon className="size-4" />
          </Link>
        </div>
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          {examples.map((e) => (
            <Link
              key={e.slug}
              href={`/try/${e.slug}`}
              className="group flex flex-col rounded-xl border border-line-strong bg-raised p-6 transition-colors hover:border-accent/50"
            >
              <p className="font-mono text-xs text-faint">{e.industry}</p>
              <h3 className="mt-2 text-lg font-medium">{e.name}</h3>
              <p className="mt-1 text-sm text-muted">{e.tagline}</p>
              <div className="mt-5 rounded-lg border border-line bg-sunken p-3 font-mono text-[12px]">
                <span className="text-faint">try › </span>
                <span>&ldquo;{e.prompts[0]}&rdquo;</span>
              </div>
              <span className="mt-5 inline-flex items-center gap-1.5 text-sm text-accent">
                Open the sandbox <ArrowRightIcon className="size-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

const MANIFEST = `agent_id: orders
tools_url: https://tools.example.com
system_prompt: You help customers find and change their orders.`

const FRONTEND = `import { createRelaySession, registerPlaygroundSurfaces } from "@sumukhj1219-wkt-org/relay-web-sdk"

const session = createRelaySession({ gatewayUrl, apiKey, agentId: "orders", transport: "small-webrtc" })
registerPlaygroundSurfaces(session, ({ surfaces }) => render(surfaces))
session.registerAction("filter_orders", ({ status }) => setFilter(String(status)), {
  description: "Filter the orders table by status",
  parameters: { type: "object", properties: { status: { type: "string" } } },
})
await session.connect()`

function Developers() {
  return (
    <section id="developers" className="scroll-mt-14 border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="Developers" title="From npm install to talking app in an afternoon.">
          A CLI for your project and keys, a YAML manifest for the agent, and a framework-agnostic SDK. Your coding
          agent can do most of it: <code className="font-mono text-fg">relay init</code> points it at the SDK&apos;s
          guides.
        </SectionHeading>
        <div className="mt-12 grid gap-4 lg:grid-cols-3">
          <CodeCard
            step="1"
            title="Sign in and create a project"
            lang="shell"
            code={`npm install -g @sumukhj1219-wkt-org/relay-cli
relay login
relay secrets set openai`}
          />
          <CodeCard
            step="2"
            title="Describe the agent, push it"
            lang="orders.yaml"
            code={`${MANIFEST}

# then
relay agents push orders.yaml
relay keys create --kind publishable`}
          />
          <CodeCard step="3" title="Connect your frontend" lang="ts" code={FRONTEND} className="lg:col-span-1" />
        </div>
      </div>
    </section>
  )
}

function CodeCard({ step, title, lang, code, className = "" }: { step: string; title: string; lang: string; code: string; className?: string }) {
  return (
    <div className={`flex min-w-0 flex-col overflow-hidden rounded-xl border border-line-strong bg-sunken ${className}`}>
      <div className="flex items-center gap-3 border-b border-line px-4 py-2.5">
        <span className="font-mono text-xs text-accent">{step}</span>
        <h3 className="text-sm font-medium">{title}</h3>
        <span className="ml-auto font-mono text-[11px] text-faint">{lang}</span>
        <CopyButton text={code} label={`Copy: ${title}`} />
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-5 text-muted">
        <code>{code}</code>
      </pre>
    </div>
  )
}

function Pricing() {
  return (
    <section id="pricing" className="scroll-mt-14 border-b border-line">
      <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <SectionHeading eyebrow="Pricing" title="Free while Relay is in preview.">
          You bring your own model key, so model usage is billed by your provider. Usage-based plans for production
          traffic will be announced before the preview ends.
        </SectionHeading>
        <div className="mt-12 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-accent/40 bg-accent-soft p-6">
            <p className="font-mono text-xs text-accent">Preview</p>
            <p className="mt-2 text-3xl font-semibold">$0</p>
            <ul className="mt-5 space-y-2 text-sm text-muted">
              <li>› Voice and text sessions</li>
              <li>› Projects, agents, keys and allowed origins</li>
              <li>› Session logs and usage in the CLI</li>
            </ul>
          </div>
          <div className="rounded-xl border border-line-strong bg-raised p-6">
            <p className="font-mono text-xs text-faint">Production</p>
            <p className="mt-2 text-3xl font-semibold">Let&apos;s talk</p>
            <ul className="mt-5 space-y-2 text-sm text-muted">
              <li>› Higher session limits</li>
              <li>› Usage reporting for billing</li>
              <li>› Help with your launch</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

function ClosingCta() {
  return (
    <section>
      <div className="mx-auto flex max-w-6xl flex-col items-start gap-6 px-4 py-20 sm:px-6 md:flex-row md:items-center">
        <h2 className="max-w-xl text-3xl font-semibold tracking-tight text-balance">
          Hear it drive a real app before you write a line.
        </h2>
        <Link
          href="/try"
          className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 md:ml-auto"
        >
          <MicIcon className="size-4" /> Open the Experience Center
        </Link>
      </div>
    </section>
  )
}
