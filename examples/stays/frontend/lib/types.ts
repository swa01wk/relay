/** Shapes returned by the site API (examples/stays/tools). */

export const DESTINATIONS = {
  goa: "Goa",
  manali: "Manali",
  coorg: "Coorg",
  udaipur: "Udaipur",
  jaipur: "Jaipur",
  alleppey: "Alleppey",
  rishikesh: "Rishikesh",
  pondicherry: "Pondicherry",
  ooty: "Ooty",
  munnar: "Munnar",
  mumbai: "Mumbai",
  bengaluru: "Bengaluru",
} as const

export const KINDS = { beach: "Beach", mountains: "Mountains", countryside: "Countryside", lakes: "Lakes & backwaters", city: "City" } as const

export const PROPERTY_TYPES = {
  villa: "Villa",
  cottage: "Cottage",
  apartment: "Apartment",
  houseboat: "Houseboat",
  treehouse: "Treehouse",
  haveli: "Heritage haveli",
  farmhouse: "Farmhouse",
  homestay: "Homestay room",
  loft: "Loft",
} as const

export const ROOM_TYPES = { entire_place: "Entire place", private_room: "Private room" } as const

export const AMENITIES = {
  wifi: "Wi-Fi",
  kitchen: "Kitchen",
  ac: "Air conditioning",
  pool: "Pool",
  parking: "Free parking",
  workspace: "Dedicated workspace",
  washer: "Washing machine",
  hot_tub: "Hot tub",
  fireplace: "Fireplace",
  bbq: "BBQ grill",
  breakfast: "Breakfast included",
  mountain_view: "Mountain view",
  lake_view: "Lake view",
  beach_access: "Beach access",
  garden: "Garden",
  ev_charger: "EV charger",
  power_backup: "Power backup",
} as const

export const SORTS = { recommended: "Recommended", price: "Price", rating: "Top rated", reviews: "Most reviewed", newest: "Newest" } as const
export const PAYMENT_METHODS = { upi: "UPI", card_on_file: "Card on file (Visa •••• 4242)" } as const
export const CANCEL_REASONS = {
  change_of_plans: "Change of plans",
  found_another_place: "Found another place",
  travel_restrictions: "Travel restrictions",
  booked_by_mistake: "Booked by mistake",
  other: "Other",
} as const
export const TRIP_STATUSES = ["requested", "upcoming", "in_stay", "completed", "cancelled", "declined"] as const
export const POLICY_LABEL = { flexible: "Flexible", moderate: "Moderate", strict: "Strict" } as const
export const SUB_RATINGS = { cleanliness: "Cleanliness", accuracy: "Accuracy", communication: "Communication", location: "Location", check_in: "Check-in", value: "Value" } as const

export type ListingCard = {
  id: string
  title: string
  destination: keyof typeof DESTINATIONS
  destination_name: string
  area: string
  state: string
  property_type: keyof typeof PROPERTY_TYPES
  property_type_label: string
  room_type: keyof typeof ROOM_TYPES
  max_guests: number
  bedrooms: number
  beds: number
  baths: number
  price: number
  weekend_price: number
  rating: number
  review_count: number
  superhost: boolean
  host_name: string
  instant_book: boolean
  cancellation_policy: keyof typeof POLICY_LABEL
  pets_allowed: boolean
  amenities: (keyof typeof AMENITIES)[]
  hue: number
  icon: string
  summary: string
  is_new: boolean
  stay_total?: number
  nights?: number
  average_night?: number
}

export type SearchResult = {
  destination: string | null
  check_in: string | null
  check_out: string | null
  guests: { adults: number; children: number; infants: number; pets: number }
  total: number
  unavailable_for_dates: number
  price_range: [number, number] | null
  listings: ListingCard[]
}

export type Review = {
  id: string
  listing_id: string
  author: string
  rating: number
  sub_ratings: Record<keyof typeof SUB_RATINGS, number>
  comment: string
  date: string
  mine: boolean
}

export type Host = { id: string; name: string; superhost: boolean; since: number; response_rate: number; response_time: string; languages: string[] }

export type ListingDetail = ListingCard & {
  description: string
  guests_included: number
  extra_guest_fee: number
  cleaning_fee: number
  pet_fee: number
  weekly_discount: number
  monthly_discount: number
  min_nights: number
  amenity_labels: string[]
  house_rules: { check_in_from: string; check_out_by: string; pets_allowed: boolean; smoking_allowed: boolean; events_allowed: boolean; max_guests: number }
  cancellation_policy_text: string
  host: Host
  rating_breakdown: Record<keyof typeof SUB_RATINGS, number>
  reviews: Review[]
  booked_nights_next_60_days: string[]
  saved_in_wishlists: string[]
}

export type CalendarDay = { date: string; available: boolean; price: number; past: boolean }

export type Quote = {
  nights: number
  nightly: { date: string; price: number; weekend: boolean; peak: boolean }[]
  average_night: number
  accommodation: number
  extra_guests: number
  extra_guest_fee: number
  length_discount_pct: number
  length_discount: number
  cleaning_fee: number
  pet_fee: number
  service_fee: number
  gst_pct: number
  gst: number
  total: number
}

export type QuoteResult = { listing: ListingCard; check_in: string; check_out: string; available: boolean; booked_nights: string[]; instant_book: boolean; quote: Quote }

export type Message = { from: "guest" | "host"; name: string; at: string; text: string }

export type TripStatus = (typeof TRIP_STATUSES)[number]

export type TripBrief = {
  id: string
  code: string
  status: TripStatus
  check_in: string
  check_out: string
  nights: number
  guests: number
  amount_paid: number
  listing_id: string
  title: string
  destination: string
  area: string
  hue: number
  icon: string
  host: string
  can_cancel: boolean
  can_review: boolean
  refund_pct_now: number | null
}

export type Trip = {
  id: string
  code: string
  status: TripStatus
  listing: ListingCard
  listing_id: string
  check_in: string
  check_out: string
  check_in_from: string
  check_out_by: string
  nights: number
  adults: number
  children: number
  infants: number
  pets: number
  guests: number
  payment_method: keyof typeof PAYMENT_METHODS
  payment_label: string
  price: Quote
  total: number
  extra_paid: number
  refund: number
  amount_paid: number
  booked_at: string
  cancelled_at: string | null
  cancellation_policy: keyof typeof POLICY_LABEL
  cancellation_policy_text: string
  refund_pct_now: number | null
  full_refund_until: string | null
  can_cancel: boolean
  can_change: boolean
  can_message: boolean
  can_review: boolean
  review_until: string | null
  reviewed: boolean
  house_manual: { wifi: string; check_in: string; parking: string } | null
  host: { id: string; name: string; superhost: boolean; response_time: string }
  messages: Message[]
  history: { at: string; event: string; detail: string }[]
}

export type MyContext = {
  guest: { name: string; email: string; phone: string; city: string; verified: boolean }
  payment_methods: { id: keyof typeof PAYMENT_METHODS; label: string }[]
  wishlists: { id: string; name: string; count: number }[]
  upcoming_trips: number
  next_trip: Omit<TripBrief, "can_cancel" | "can_review" | "refund_pct_now"> | null
  trips_taken: number
  lifetime_spend: number
}

export type Wishlist = { id: string; name: string; count: number; listings: ListingCard[] }
export type Destination = { key: keyof typeof DESTINATIONS; name: string; state: string; kind: keyof typeof KINDS; areas: string[]; listings: number; price_from: number; price_to: number; avg_rating: number; property_types: string[] }
export type Thread = { trip_id: string; title: string; host: string; status: TripStatus; check_in: string; last_message: string; last_from: "guest" | "host"; last_at: string; count: number }
export type AttentionItem = { kind: string; trip_id: string; text: string }
