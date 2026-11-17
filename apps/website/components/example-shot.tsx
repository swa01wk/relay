import Image from "next/image"

import { type Example, screenshotOf } from "@/lib/examples"

/** The example's home page in a browser-window frame, for gallery cards. */
export function ExampleShot({ example, priority = false }: { example: Example; priority?: boolean }) {
  return (
    <div className="border-b border-line bg-sunken px-4 pt-4">
      <div className="overflow-hidden rounded-t-lg border border-b-0 border-line-strong bg-raised shadow-sm">
        <div className="flex h-6 items-center gap-1.5 border-b border-line px-2.5" aria-hidden>
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
        </div>
        <Image
          src={screenshotOf(example)}
          alt={`${example.name} home page`}
          width={1200}
          height={750}
          sizes="(min-width: 1280px) 400px, (min-width: 768px) 50vw, 100vw"
          priority={priority}
          unoptimized
          className="block aspect-[16/10] w-full object-cover object-top transition-transform duration-300 group-hover:scale-[1.02]"
        />
      </div>
    </div>
  )
}
