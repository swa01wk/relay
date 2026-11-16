# Wayline bus booking — Relay inventory and coverage

Built by the workflow in the SDK's `AGENTS.md`: every page, write and entity of the site mapped to a
tool, a screen action, or an exclusion. Tools: `tools/src/bus_api/tools.py` (one table → `GET /tools`).

**Counts:** 8 pages · 7 writes (server actions → booking API) + 6 page forms · 6 entities →
**32 tools** (25 read, 7 side-effecting) · **5 screen actions** + automatic navigation and page forms.

## Pages

| Page | What is on it | Assistant reaches it with |
|---|---|---|
| `/` Home | Search form, next trip, attention items, popular routes, offers | `NAVIGATE` (logo link) |
| `/search` Results | Route + date, fare-by-date strip, filters (AC / non-AC, sleeper / seater, departure time, operator, max fare, rating, amenity), sort tabs, bus cards | **`SEARCH_BUSES`** |
| `/trips/[id]` Seat map | Lower / upper deck (or seater) map with prices and women-only seats, boarding and dropping points, fare, Continue; cancellation policy, reviews | **`OPEN_TRIP`**, **`SELECT_SEATS`** |
| `/checkout` Passenger details | One passenger per seat (name, age, gender; saved-traveller chips), contact, payment, offer code, Pay | `SELECT_SEATS` with `go_to_checkout`, page form "Passenger details" |
| `/bookings` My trips | Status chips (upcoming, on the way, completed, cancelled), booking list | `NAVIGATE`, **`FILTER_BOOKINGS`** |
| `/bookings/[id]` Ticket | PNR, boarding / dropping, passengers, payment, history; Change points, Reschedule, Cancel seats, Rate forms | **`OPEN_BOOKING`**, page forms "Change boarding point", "Reschedule trip", "Cancel booking", "Rate trip" |
| `/travellers` Travellers | Profile, wallet, saved travellers, Add / remove | `NAVIGATE` (header link), page form "Add traveller" |
| `/offers` Offers | Offer codes | `NAVIGATE` (header link) |
| not-found | — | — |

`/offers` and `/bookings?status=cancelled` are also listed in `registerAutoNavigation`'s `pages`; the
rest are links on screen. The home search form is `data-relay-ignore` (SEARCH_BUSES does the same in one step).

## Writes (server actions in `frontend/app/actions.ts` → booking API → `logic.py`)

| Where | What, in the traveller's words | Input | Tool |
|---|---|---|---|
| Passenger details → Pay | "Book L4 and L5 for me and Rahul" | trip, seats (1–4), boarding / dropping point, per seat name + age 1–110 + gender (3), email, mobile, payment (UPI / card on file / wallet), offer code | `book_tickets` (form-bound; read first: `get_fare_quote`, `find_seats`) |
| Cancel seats form | "Cancel Rahul's seat" / "cancel the whole trip" | booking, seats (optional), reason (5) | `cancel_booking` (read first: `get_cancellation_quote`) |
| Change boarding point form | "Board at Silk Board instead" | booking, boarding and/or dropping point | `change_boarding_point` |
| Reschedule form | "Move it to Friday" | booking, new date, seats (optional) | `reschedule_booking` |
| Rate form (completed trips) | "Four stars, a bit late" | booking, rating 1–5, review ≤ 1000 | `rate_trip` |
| Add traveller form | "Save my dad Suresh, 61" | name ≤ 60, age, gender | `add_traveller` |
| Remove (trash) | "Remove Meera" | traveller | `remove_traveller` |

**Excluded:** payment entry (UPI PIN / card number — payments use the methods on file and the demo
charges nothing); sign-in (one traveller per browser / sandbox); `/sandbox/reset` and `/health` (operator endpoints).

## Entities and their tools

| Entity | Fields that matter | Tools |
|---|---|---|
| City / boarding point | 12 cities, 4 points each | `list_cities`, `search_all` |
| Route | from, to, distance, typical duration, buses per day, lowest fare | `list_routes`, `get_fare_calendar` |
| Trip (schedule on a date) | operator, bus type (5), departure / arrival, duration, fare (weekend +10%), seats (deck, window, price, status, women-only), amenities (8), rating | `search_trips` (list / filter / sort), `get_trip`, `find_seats`, `compare_trips`, `get_fare_quote` |
| Operator + review | rating, reviews 1–5 | `list_operators`, `get_operator`, `get_top_operators`, `list_reviews`, `rate_trip` |
| Offer | WAYLINE10, NIGHTOWL, GROUP4, FIRSTRIDE with conditions | `list_offers`, `check_coupon` |
| Booking (per traveller) | status (upcoming, in_transit, completed, cancelled), PNR, passengers + seats, points, paid / refunded, history | `list_bookings`, `get_booking`, `get_cancellation_quote`, `aggregate_bookings`, `get_travel_spend_over_time`, booking writes above |
| Traveller (per user) | profile, saved co-travellers (≤ 8), wallet, payment methods | `get_my_context`, `list_travellers`, `add_traveller`, `remove_traveller` |

Cross-entity: `search_all`, `get_overview`, `list_attention_items` (trips within 48 h, cancellation
charges about to rise, trips to rate), `describe_data`; domain calculations: `get_fare_quote`,
`find_seats`, `get_fare_calendar`, `get_cancellation_quote`, `check_coupon`.

## Coverage check

| Check | Holds |
|---|---|
| Pages → reachable by `NAVIGATE` | ✓ 8 of 8 (checkout via `SELECT_SEATS` — it needs a seat selection; not-found excluded) |
| Detail views → `OPEN_<ENTITY>` | ✓ `OPEN_TRIP`, `OPEN_BOOKING` |
| Lists with filters → `FILTER_<LIST>` | ✓ `SEARCH_BUSES` (route, date, every filter, sort), `FILTER_BOOKINGS` |
| Selections on screen | ✓ `SELECT_SEATS` (seats, boarding / dropping point) |
| Writes and forms → `side_effecting` tools | ✓ 7 of 7 |
| Entities → list / get / aggregate (+ writes) | ✓ |
| Cross-entity tools | ✓ `search_all`, `get_overview`, `list_attention_items`, `get_my_context`, `describe_data`, rankings, comparison, fare calendar, spend over time |

## Questions it should answer (≤ 4 rounds each)

1. "AC sleepers from Bangalore to Hyderabad tomorrow night" → `SEARCH_BUSES` (ac, sleeper, night)
2. "Which is the cheapest?" → `SEARCH_BUSES` sort_by fare (or `search_trips`)
3. "Which day next week is cheapest to Chennai?" → `get_fare_calendar` → bar chart
4. "Compare the 9 pm and the 10:30 pm buses" → `search_trips` → `compare_trips` → comparison
5. "Is Moonlit Sleepers any good?" → `get_operator` / `list_reviews`
6. "Open the 9:30 one" → `OPEN_TRIP`
7. "Two lower berths together, boarding at Silk Board" → `find_seats` → `SELECT_SEATS`
8. "Any window seats left on the upper deck?" → `find_seats` preference upper / `get_trip`
9. "Which seats can my mother book?" → `get_trip` (women_only seats)
10. "How much with WAYLINE10?" → `get_fare_quote` / `check_coupon`
11. "Book it for me and Rahul" → `get_my_context` → `SELECT_SEATS` go_to_checkout + fill Passenger details (or a form bound to `book_tickets`)
12. "Pay from my wallet" → `get_my_context` (balance) → payment method
13. "When does my next bus leave, and from where?" → `list_bookings` / `get_overview` → `OPEN_BOOKING`
14. "What would it cost to cancel my Mysuru trip?" → `list_bookings` → `get_cancellation_quote` → kv
15. "Cancel only Meera's seat" → `cancel_booking` seats (approval)
16. "Move my Hyderabad trip to Friday" → `reschedule_booking` (approval)
17. "Board at Electronic City instead" → `change_boarding_point` (approval)
18. "Rate my Chennai trip four stars" → `rate_trip` (approval / form)
19. "Save my dad Suresh, 61, as a traveller" → `add_traveller` (approval) or the Add traveller page form
20. "How much have I spent on buses in the last six months?" → `get_travel_spend_over_time` → chart
21. "Which operator do I use most?" → `aggregate_bookings` group_by operator
22. "Show only my cancelled trips" → `FILTER_BOOKINGS`
23. "Anything I should know about?" → `list_attention_items`
24. "What offers are there?" → `list_offers`
25. "Do you go to Madurai from Mysuru?" → `search_trips` (note lists the destinations)
26. "What's the cancellation policy?" → `describe_data` / `get_trip`
