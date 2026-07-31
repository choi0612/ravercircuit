Get one event (with its lineup) by id — event detail page, and every "does this event exist?" check
Get one event's updates, newest first, optionally in a date window — the updates stream
Browse events by region and/or month, in date order, paginated — the board's filters
Get my ranked recommendations, best first — the board itself
Get my circuit in date order; add a leg; remove a leg — the write path
Get all events where a given artist appears, in date order — "where can I catch Novastorm this year"
Get my favorites list — the scorer asks this on every score
Get my friends list; add a friend — crew roster
Get all RSVPs for one event; add/replace an RSVP — the crew factor's counts, and the second write path
On any circuit or RSVP change: recompute and re-store the recommendations — not a user question, but a write pattern the table must make cheap

Q1 — one event with its lineup. File everything about an event under one label: PK = EVENT#e017. The event's core facts get SK = META; each lineup slot gets SK = ARTIST#a042. One grab of the label returns META + all slots together — the event assembles itself from its own collection.

Q2 — updates, newest first. Same label! PK = EVENT#e017, SK = UPD#2026-07-01T18:00:00Z#u0031. Here's the trick that makes this work: ISO timestamps sort correctly as plain text (year, then month, then day — alphabetical is chronological). So "updates in a window, newest first" = grab the label, slice SK between UPD#<start> and UPD#<end>, read backward. The little id on the end just breaks ties for same-second updates. Notice Q1 and Q2 share a label but never collide, because their SKs start differently — META, ARTIST#, UPD# are shelves within the drawer.

Q5 — my circuit, date order. Your stuff gets your label: PK = USER#me, SK = LEG#2026-09-12#e017. Date in the SK → grabbing the label returns the itinerary already sorted. Add a leg = write one item; remove = delete one item.

Q7, Q8 — favorites, friends. Same drawer, own shelves: USER#me / FAV#a042 (affinity stored on the item), USER#me / FRIEND#f003.

Q9 — RSVPs for one event. Asked-together rule: the crew factor asks per event, so RSVPs file under the event's label: EVENT#e017 / RSVP#f003. Counting the crew = grab the event's label, look at the RSVP shelf. (Filing them under USER#me would've forced a full sift every score — the rule earns its keep here.)

Q4 — ranked recommendations. The clever one. PK = USER#me, SK = REC#087#e017 — where 087 is the score flipped (score 91.3 → stored as 100−91.3 = 008.7 → REC#0087... we'll nail the exact padding in code; the idea is what matters): lower SK sorts first, so flipping the score makes "best first" the natural storage order. Grabbing the label returns the board, already ranked, no sorting anywhere. This is the inverted-score sort key — flagship talking point #1.

Q10 — recompute on change. Now visible as a write pattern: when a leg or RSVP changes, delete the old REC# items and write fresh ones. Materialized — computed at write time, instant at read time — the trade being a moment of staleness during rewrite. (You'll defend "materialize vs. compute-on-read" out loud today; the honest answer is the board is read constantly and changed rarely, so precompute wins.)

Which leaves Q3 and Q6 — and a wall. Browse by region? Region isn't in any label. All events for one artist? Artist labels don't exist — artist ids live inside event drawers. The base table physically cannot answer these fast... and that's what a GSI is for: a second filing system over the same items. You pick two extra attributes on an item, call them the GSI's label and order, and DynamoDB maintains a parallel cabinet automatically.

GSI1 solves Q3: on each META item, add GSI1PK = REGION#west, GSI1SK = DATE#2026-09-12#EVENT#e017. In GSI1's cabinet, all西-coast events file together in date order — region browse is one grab, month filter is an SK slice.

GSI2 solves Q6 — the crown jewel. Look at the lineup-slot item: it's already the fact "artist a042 plays event e017." Add to that same item: GSI2PK = ARTIST#a042, GSI2SK = DATE#2026-09-12#EVENT#e017. Base cabinet: the item files under the event ("who plays here?"). GSI2 cabinet: the same item files under the artist ("where do they play?"). One item, two directions — the many-to-many relationship served both ways with zero duplication. That's the inverted index, flagship talking point #2, and it's why Q6 was the sneaky-important question.

Your table, complete — put this in the doc:

What	PK	SK	GSI1 (PK / SK)	GSI2 (PK / SK)
Event meta	EVENT#e017	META	REGION#west / DATE#2026-09-12#EVENT#e017	—
Lineup slot	EVENT#e017	ARTIST#a042	—	ARTIST#a042 / DATE#2026-09-12#EVENT#e017
Update	EVENT#e017	UPD#<iso>#<id>	—	—
RSVP	EVENT#e017	RSVP#f003	—	—
Circuit leg	USER#me	LEG#<date>#e017	—	—
Favorite	USER#me	FAV#a042	—	—
Friend	USER#me	FRIEND#f003	—	—
Recommendation	USER#me	REC#<inv-score>#e017	—	—

Why do RSVPs live under the event's label and not yours? 
Because of who asks for them together. The only code that reads RSVPs is the crew factor, and its question is always "who's coming to this event?" — never "everything Alex RSVPed to." Filing follows the question: put the RSVPs in the event's drawer, and scoring an event grabs one label and finds its crew right there in the collection. If we'd filed them under USER#me instead, answering "who's coming to e017?" would mean grabbing all RSVPs you've ever logged and sifting for the matching event — a mini-scan inside every single score, of every event, on every board load. Same data, wrong drawer, hundredfold cost. That's the mantra with consequences: things asked for together get filed together — and the deeper point worth saying in an interview: in DynamoDB, where a fact lives is decided by who reads it, not by what "owns" it. (And if the app someday does need "all of Alex's RSVPs" — that's not a redesign, that's one more GSI on the RSVP items. Known escape hatch, deliberately not built until asked for.)
What would break if we'd put the score un-flipped in the REC sort key?
The order comes out backward — the label grab would return your recommendations worst-first. Sort keys store in ascending order, plain and simple: REC#008 sits before REC#091, so if bigger-number-means-better, the garbage leads. And yes, DynamoDB can read a collection in reverse (ScanIndexForward=False — you'll type it today), so "just read backward" seems to rescue it... until you want the top slice: "give me the best 20" reading backward means the end of the collection, which still works, but now every consumer of this collection must remember to flip the direction flag forever, and forgetting it fails silently — the API happily returns confident, perfectly wrong rankings. Flipping the score at write time (100 − score, zero-padded so text-sorting behaves: 008.7 not 8.7) makes best-first the physical storage order — the default read is the right read, no flag, no way to forget. The interview-grade phrasing: encode your desired ordering into the key itself, so correctness doesn't depend on every reader remembering an option. The zero-padding matters for the same reason ISO dates worked yesterday — these sort as text, and 9 comes after 10 alphabetically unless you pad.


## Benchmarks

QUERY via GSI2 :    47 gigs in      5.0 ms — examined 47 items
SCAN + filter  :    47 gigs in   1331.3 ms — examined 45192 items
→ the scan examined 961x more items and ran 265x slower here