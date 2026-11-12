/** Shapes returned by the booking API (examples/bus-booking/tools). */

export const CITIES = {
  BLR: "Bengaluru",
  CHE: "Chennai",
  HYD: "Hyderabad",
  MUM: "Mumbai",
  PUN: "Pune",
  GOA: "Goa (Panaji)",
  MYS: "Mysuru",
  CBE: "Coimbatore",
  COK: "Kochi",
  MNG: "Mangaluru",
  VJA: "Vijayawada",
  MDU: "Madurai",
} as const
export type CityCode = keyof typeof CITIES

export const BUS_TYPES = {
  ac_sleeper: "AC Sleeper (2+1)",
  multi_axle_sleeper: "Multi-Axle AC Sleeper (2+1)",
  non_ac_sleeper: "Non-AC Sleeper (2+1)",
  ac_seater: "AC Seater Push-back (2+2)",
  non_ac_seater: "Non-AC Seater (2+2)",
} as const

export const DEPARTURE_WINDOWS = {
  early_morning: "Before 6 am",
  morning: "6 am – 12 pm",
  afternoon: "12 pm – 6 pm",
  night: "After 6 pm",
} as const

export const AMENITIES = {
  charging_point: "Charging point",
  water_bottle: "Water bottle",
  blanket: "Blanket",
  reading_light: "Reading light",
  live_tracking: "Live tracking",
  wifi: "Wi-Fi",
  cctv: "CCTV",
  toilet: "Toilet",
} as const

export const SORTS = {
  departure: "Departure",
  fare: "Cheapest",
  rating: "Top rated",
  duration: "Fastest",
  seats_left: "Most seats",
  arrival: "Arrival",
} as const

export const OPERATORS = {
  "OP-NSC": "Northstar Coaches",
  "OP-DCC": "Deccan Comfort",
  "OP-CRD": "Coastal Rider",
  "OP-MLS": "Moonlit Sleepers",
  "OP-KBZ": "Konkan Breeze",
  "OP-TMT": "Tamarind Tours",
  "OP-BBI": "Bluebird Intercity",
  "OP-SFW": "Saffron Wheels",
} as const

export const PAYMENT_METHODS = { upi: "UPI", card_on_file: "Card on file (Visa •••• 4242)", wallet: "Wayline Wallet" } as const
export const GENDERS = ["female", "male", "other"] as const
export const CANCEL_REASONS = {
  change_of_plans: "Change of plans",
  found_another_bus: "Found another bus",
  booked_by_mistake: "Booked by mistake",
  trip_postponed: "Trip postponed",
  other: "Other",
} as const
export const BOOKING_STATUSES = ["upcoming", "in_transit", "completed", "cancelled"] as const

export type TripCard = {
  trip_id: string
  schedule_id: string
  from: CityCode
  from_city: string
  to: CityCode
  to_city: string
  date: string
  operator: string
  operator_id: string
  hue: number
  bus_type: keyof typeof BUS_TYPES
  bus_type_label: string
  ac: boolean
  sleeper: boolean
  departs: string
  arrives: string
  arrives_next_day: number
  duration_min: number
  duration: string
  departure_window: keyof typeof DEPARTURE_WINDOWS
  fare: number
  fare_max: number
  seats_left: number
  seats_total: number
  women_only_seats: number
  rating: number
  amenities: (keyof typeof AMENITIES)[]
  boarding_from: string
  dropping_at: string
  bookable: boolean
}

export type SearchResult = {
  from: CityCode
  from_city: string
  to: CityCode
  to_city: string
  date: string
  distance_km?: number
  total: number
  cheapest_fare?: number | null
  trips: TripCard[]
  note?: string
}

export type Seat = {
  id: string
  deck: "lower" | "upper" | "main"
  row: number
  col: number
  kind: "sleeper" | "seat"
  window: boolean
  price: number
  status: "available" | "booked" | "booked_female" | "yours"
  women_only: boolean
}

export type Point = { id: string; name: string; landmark: string; time: string }

export type Review = { id: string; operator: string; operator_id: string; route: string; author: string; rating: number; comment: string; date: string; mine: boolean }

export type TripDetail = TripCard & {
  distance_km: number
  amenity_labels: string[]
  boarding_points: Point[]
  dropping_points: Point[]
  decks: ("lower" | "upper" | "main")[]
  seats: Seat[]
  gst_pct: number
  upper_berth_discount: number
  cancellation_policy: { window: string; charge_pct: number | null; note?: string }[]
  latest_reviews: Review[]
}

export type Quote = {
  seats: string[]
  seat_prices: Record<string, number>
  fare_total: number
  coupon: string | null
  coupon_problem: string | null
  discount: number
  gst: number
  total: number
}

export type CalendarDay = { date: string; weekday: string; cheapest_fare: number | null; buses: number; seats_left: number }

export type Traveller = { id: string; name: string; age: number; gender: (typeof GENDERS)[number] }

export type Passenger = {
  seat: string
  name: string
  age: number
  gender: string
  fare: number
  paid: number
  status: "confirmed" | "cancelled"
  refund?: number
  charge?: number
  cancelled_at?: string
}

export type BookingBrief = {
  id: string
  pnr: string
  status: (typeof BOOKING_STATUSES)[number]
  route: string
  journey_date: string
  departs: string
  arrives: string
  seats: string[]
  amount_paid: number
  operator: string
  boarding_point: string
  bus_type: string
  passengers: number
  can_cancel: boolean
  can_rate: boolean
  total: number
  refunded: number
}

export type Booking = {
  id: string
  pnr: string
  status: (typeof BOOKING_STATUSES)[number]
  trip: TripCard
  trip_id: string
  journey_date: string
  route: string
  departs: string
  arrives: string
  boarding_point: Point
  dropping_point: Point
  passengers: Passenger[]
  seats: string[]
  contact_email: string
  contact_phone: string
  payment_method: keyof typeof PAYMENT_METHODS
  payment_label: string
  coupon: string | null
  fare_total: number
  discount: number
  gst: number
  total: number
  extra_paid: number
  refunded: number
  amount_paid: number
  booked_at: string
  rescheduled_from: string | null
  rating: { stars: number; review_id: string } | null
  history: { at: string; event: string; detail: string }[]
  can_cancel: boolean
  cancellation_charge_pct: number | null
  charges_rise_at: { from: string; charge_pct: number | null } | null
  can_reschedule: boolean
  can_change_points: boolean
  can_rate: boolean
  boarding_points: Point[]
  dropping_points: Point[]
}

export type MyContext = {
  traveller: { name: string; email: string; phone: string; gender: string; age: number; home_city: string }
  saved_travellers: Traveller[]
  wallet_balance: number
  payment_methods: { id: keyof typeof PAYMENT_METHODS; label: string }[]
  upcoming_trips: number
  next_trip: (Omit<BookingBrief, "can_cancel" | "can_rate" | "passengers" | "bus_type" | "arrives" | "total" | "refunded">) | null
  total_bookings: number
  lifetime_spend: number
}

export type Offer = { code: string; title: string; description: string }
export type RouteInfo = {
  route: string
  from: CityCode
  from_city: string
  to: CityCode
  to_city: string
  distance_km: number
  typical_duration: string
  buses_per_day: number
  fares_from: number | null
  operators: string[]
}
export type AttentionItem = { kind: string; booking_id: string; text: string }
