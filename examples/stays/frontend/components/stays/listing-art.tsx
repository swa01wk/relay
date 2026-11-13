import { BedDoubleIcon, Building2Icon, HomeIcon, LandmarkIcon, SailboatIcon, TreePineIcon, TreesIcon, WarehouseIcon, WheatIcon } from "lucide-react"

import { cn } from "@/lib/utils"

const ICONS = {
  home: HomeIcon,
  trees: TreesIcon,
  building: Building2Icon,
  sailboat: SailboatIcon,
  tree: TreePineIcon,
  landmark: LandmarkIcon,
  wheat: WheatIcon,
  bed: BedDoubleIcon,
  warehouse: WarehouseIcon,
} as const

/**
 * A stand-in "photo": a gradient in the listing's colour with its property icon. `shot` varies the
 * composition so a gallery doesn't repeat.
 */
export function ListingArt({ hue, icon, shot = 0, label, className }: { hue: number; icon: string; shot?: number; label?: string; className?: string }) {
  const Icon = ICONS[icon as keyof typeof ICONS] ?? HomeIcon
  const h2 = (hue + 40 + shot * 25) % 360
  const angle = 135 + shot * 40
  return (
    <div
      role="img"
      aria-label={label ?? "Photo"}
      className={cn("relative grid place-items-center overflow-hidden", className)}
      style={{ background: `linear-gradient(${angle}deg, oklch(0.86 0.06 ${hue}), oklch(0.7 0.09 ${h2}))` }}
    >
      <div className="absolute -right-6 -bottom-8 size-32 rounded-full opacity-30" style={{ background: `oklch(0.95 0.04 ${h2})` }} />
      <Icon className="size-1/4 max-h-16 max-w-16 text-white/85 drop-shadow" strokeWidth={1.4} />
      {label && <span className="absolute bottom-2 left-2 rounded-full bg-black/35 px-2 py-0.5 text-[11px] text-white">{label}</span>}
    </div>
  )
}
