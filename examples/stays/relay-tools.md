# Roostly vacation rentals — Relay inventory and coverage

Built by the workflow in the SDK's `AGENTS.md`: every page, write and entity of the site mapped to a
tool, a screen action, or an exclusion. Tools: `tools/src/stays_api/tools.py` (one table → `GET /tools`).

**Counts:** 10 pages · 8 writes (server actions → site API) + 7 page forms · 7 entities →
**31 tools** (23 read, 8 side-effecting) · **6 screen actions** + automatic navigation and page forms.

## Pages

| Page | What is on it | Assistant reaches it with |
|---|---|---|
| `/` Home | Search bar, kinds of places, next trip, "for you", destinations, guest favourites | `NAVIGATE` (logo link) |
| `/search` Results | Where / dates / guests, property-type and amenity chips, instant book, superhost, room type, price, bedrooms, rating, sort; listing cards with hearts | **`SEARCH_STAYS`** |
| `/listings/[id]` Home | Gallery, host, instant book / request, policy, description, amenities, house rules and fees, rating breakdown, reviews; booking panel (dates, guests, month calendar, price breakdown, Reserve) | **`OPEN_LISTING`**, **`SET_STAY`** |
| `/book` Confirm and pay | Trip summary, message to the host, payment, price, policy | `SET_STAY` with `go_to_checkout`, page form "Confirm and pay" |
| `/trips` Trips | Status chips, trip cards | `NAVIGATE`, **`FILTER_TRIPS`** |
| `/trips/[id]` Trip | Dates, guests, check-in details (once confirmed), messages, history, payment; Change, Cancel, Review forms | **`OPEN_TRIP`**, page forms "Message host", "Change trip", "Cancel trip", "Write a review" |
| `/wishlists` Wishlists | Lists with covers, New wishlist | `NAVIGATE` (header link), page form "New wishlist" |
| `/wishlists/[id]` Wishlist | Saved homes | **`OPEN_WISHLIST`** |
| `/inbox` Inbox | One thread per trip | `NAVIGATE` (header link) |
| not-found | — | — |

`/search` (all homes) and `/trips?status=cancelled` are also in `registerAutoNavigation`'s `pages`.
The search bar, filters and booking panel are `data-relay-ignore` (the actions above do the same in one step).

## Writes (server actions in `frontend/app/actions.ts` → site API → `logic.py`)

| Where | What, in the guest's words | Input | Tool |
|---|---|---|---|
| Confirm and pay | "Book it for the two of us" | home, check-in, check-out, adults, children, infants, pets, message to the host (required for requests), payment (UPI / card on file) | `reserve_stay` (form-bound; read first: `get_price_quote`, `check_availability`) |
| Cancel trip form | "Cancel my Ooty trip" | trip, reason (5) | `cancel_reservation` (read first: `get_cancellation_quote`) |
| Change trip form | "Make it one night longer" / "add my sister" | trip, new dates and/or guests | `change_reservation` |
| Message host | "Ask the host if there's parking" | trip, message ≤ 1000 | `message_host` |
| Review form | "Five stars, spotless and quiet" | trip, overall 1–5, six sub-ratings, text 20–2000 | `write_review` |
| Heart (save) | "Save this one to Goa with friends" | home, wishlist (name creates it) | `save_to_wishlist` |
| Heart (unsave) | "Take it off my wishlist" | home, wishlist (optional) | `remove_from_wishlist` |
| New wishlist form | "Make a list called Honeymoon" | name ≤ 50 | `create_wishlist` |

**Excluded:** card / UPI entry (payments use the methods on file; the demo charges nothing); sign-in
(one guest per browser / sandbox); host-side actions (accepting requests is simulated); `/sandbox/reset`
and `/health` (operator endpoints).

## Entities and their tools

| Entity | Fields that matter | Tools |
|---|---|---|
| Destination | 12 places, state, kind (beach, mountains, countryside, lakes, city), areas | `list_destinations`, `search_all` |
| Listing | type (9), room type, guests, rooms, prices (weekday, weekend, peak), fees, discounts, min nights, instant book, policy, pets, amenities (17), host | `search_listings`, `get_listing`, `check_availability`, `get_price_quote`, `compare_listings`, `aggregate_listings`, `get_top_listings` |
| Host | superhost, since, response rate / time, languages | `get_host` |
| Review | overall + 6 sub-ratings, text | `list_reviews`, `write_review` |
| Trip (per guest) | status (requested, upcoming, in_stay, completed, cancelled, declined), dates, guests, price, refunds, messages, history | `list_trips`, `get_trip`, `get_cancellation_quote`, `aggregate_trips`, `get_travel_spend_over_time`, trip writes above |
| Message | per trip, guest / host | `list_messages`, `message_host` |
| Wishlist (per guest) | name, homes | `list_wishlists`, `get_wishlist`, wishlist writes above |
| Guest | profile, payment methods | `get_my_context` |

Cross-entity: `search_all`, `get_overview`, `list_attention_items` (requests awaiting the host,
check-ins within 3 days, free cancellation ending, stays to review), `describe_data`; domain
calculations: `get_price_quote`, `check_availability`, `get_cancellation_quote`.

## Coverage check

| Check | Holds |
|---|---|
| Pages → reachable by `NAVIGATE` | ✓ 9 of 9 (Confirm and pay via `SET_STAY` — it needs dates; not-found excluded) |
| Detail views → `OPEN_<ENTITY>` | ✓ `OPEN_LISTING`, `OPEN_TRIP`, `OPEN_WISHLIST` |
| Lists with filters → `FILTER_<LIST>` | ✓ `SEARCH_STAYS` (place, dates, guests, every filter, sort), `FILTER_TRIPS` |
| Selections on screen | ✓ `SET_STAY` (dates, guests on the booking panel) |
| Writes and forms → `side_effecting` tools | ✓ 8 of 8 |
| Entities → list / get / aggregate (+ writes) | ✓ |
| Cross-entity tools | ✓ `search_all`, `get_overview`, `list_attention_items`, `get_my_context`, `describe_data`, rankings, comparison, spend over time |

## Questions it should answer (≤ 4 rounds each)

1. "A villa with a pool in Goa for 6 people, 20 to 23 December" → `SEARCH_STAYS`
2. "Cottages in the hills that allow dogs, under ₹7,000 a night" → `SEARCH_STAYS` (mountains, cottage, pets, max_price)
3. "Something on the backwaters this weekend for two" → `SEARCH_STAYS` (Alleppey, dates)
4. "Compare the two Udaipur places on the lake" → `search_listings` → `compare_listings`
5. "What's the cheapest place in Kerala?" → `get_top_listings` price_low
6. "Average price per night by destination" → `aggregate_listings` → bar chart
7. "Open the treehouse in Manali" → `OPEN_LISTING`
8. "Is it free 12–15 January?" → `check_availability`
9. "How much for a week there with my dog?" → `get_price_quote`
10. "What do people say about cleanliness?" → `get_listing` (rating breakdown, reviews)
11. "Book it for 12–15 Jan for two" → `SET_STAY` go_to_checkout (or a form bound to `reserve_stay`)
12. "Tell the host we'll arrive around 4" → fills the Confirm and pay page form
13. "Save it to Goa with friends" → `save_to_wishlist` (approval)
14. "When is my next trip and how do I check in?" → `get_overview` / `get_trip` (house manual) → `OPEN_TRIP`
15. "What would I get back if I cancel my Ooty trip?" → `get_cancellation_quote` → kv
16. "Cancel it" → `cancel_reservation` (approval)
17. "Make my Pondicherry trip one night longer" → `change_reservation` (approval)
18. "Ask the host if there's parking" → `message_host` (approval)
19. "Did the host reply about my request?" → `list_trips` requested / `get_trip`
20. "Review the Bengaluru flat: 4 stars, quiet and fast Wi-Fi" → `write_review` (form / approval)
21. "How much have I spent on stays this year?" → `get_travel_spend_over_time` → chart
22. "Where have I stayed most?" → `aggregate_trips` group_by destination
23. "Show my cancelled trips" → `FILTER_TRIPS`
24. "Anything I need to do?" → `list_attention_items`
25. "Who is the host of Casa Azul? Are they a superhost?" → `get_listing` / `get_host`
26. "What's the strict cancellation policy?" → `describe_data`
