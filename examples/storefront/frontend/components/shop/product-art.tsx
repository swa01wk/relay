import {
  CookingPotIcon,
  HeadphonesIcon,
  LampDeskIcon,
  type LucideIcon,
  MountainSnowIcon,
  ShoppingBagIcon,
  SparklesIcon,
} from "lucide-react"

import { cn } from "@/lib/utils"

const ICONS: Record<string, LucideIcon> = {
  Audio: HeadphonesIcon,
  "Home Office": LampDeskIcon,
  Kitchen: CookingPotIcon,
  Outdoor: MountainSnowIcon,
  Wellness: SparklesIcon,
  Accessories: ShoppingBagIcon,
}

/** Product imagery for the demo: a soft gradient in the product's hue with its category's icon. */
export function ProductArt({
  hue,
  category,
  className,
  iconClassName,
}: {
  hue: number
  category: string
  className?: string
  iconClassName?: string
}) {
  const Icon = ICONS[category] ?? ShoppingBagIcon
  return (
    <div
      className={cn("relative grid aspect-square place-items-center overflow-hidden rounded-xl", className)}
      style={{
        background: `radial-gradient(120% 90% at 30% 20%, oklch(0.97 0.03 ${hue}) 0%, oklch(0.9 0.06 ${hue}) 55%, oklch(0.8 0.08 ${hue}) 100%)`,
      }}
      aria-hidden="true"
    >
      <div
        className="absolute -right-6 -bottom-6 size-2/3 rounded-full opacity-40"
        style={{ background: `oklch(0.75 0.1 ${hue})` }}
      />
      <Icon className={cn("relative size-1/3 stroke-[1.25]", iconClassName)} style={{ color: `oklch(0.38 0.08 ${hue})` }} />
    </div>
  )
}
