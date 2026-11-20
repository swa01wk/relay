"use client"

import { useScreenState } from "@/components/relay/relay-provider"

/** Tells the assistant what this screen shows (removed again when the page unmounts). */
export function ScreenState({ name, value }: { name: string; value: unknown }) {
  useScreenState(name, value)
  return null
}
