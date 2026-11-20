# QUICK PASS

A railway-booking demo named QUICK PASS with a Python backend. Local development uses
SQLite; the included Render Blueprint connects the public web service to a
separate managed PostgreSQL database using a private connection URL.

## Run locally

Install Python 3.9 or newer, then open a terminal in this folder and run:

```powershell
python server.py
```

Open <http://127.0.0.1:8000>. Without `DATABASE_URL`, bookings are stored in
`railway.sqlite3` beside `server.py`.

## Public demo

- Website: <https://quick-pass-demo.onrender.com>
- Public source: <https://github.com/saivamshikrishna-cell/QUICK-PASS>

The website is hosted by Render. To show it on Google Sites, create or open a
Site, choose **Insert → Embed → By URL**, paste the website URL above, and
publish the Site. Google Sites embeds the app; it does not host the Python
server or database.

## Deploy on Render

1. Push this folder to a GitHub repository and create a Render account.
2. In Render, choose **New → Blueprint**, select that repository, and deploy
   its `render.yaml` file.
3. Render creates the Python web service and a separate PostgreSQL database.
   The Blueprint injects the database's `connectionString` into the service as
   the private `DATABASE_URL`; never paste the database URL into website code
   or commit it to Git.
4. Open the public `onrender.com` web-service URL. `/healthz` reports whether
   the server can reach its database.

## Embed in Google Sites

After the Render deployment is live:

1. Open a Google Site and choose **Insert → Embed → By URL**.
2. Paste the public HTTPS Render web-service URL and select **Insert**.
3. Resize the embedded frame to fit the page, then publish the Google Site.

Google Sites embeds the app; it does not host the Python API or database. The
Render service must remain deployed for bookings and availability to work.

The included Blueprint selects Render's **Free** plans for the demo. Render's
free web service can sleep while idle, and its free PostgreSQL database expires
after 30 days. Review Render's current limits and pricing before deploying;
upgrade the database and service plans for persistent/production use. The
database is connected privately to the app rather than exposed publicly.

The source code is released under the MIT License; see [LICENSE](LICENSE).

The app creates/updates its reservation table automatically at startup.
`schema.sql` documents the equivalent SQL schema and lookup indexes.
For local development with PostgreSQL, install `requirements.txt` and set
`DATABASE_URL` in the server environment before running `python server.py`.

The public availability API returns seat/route data and aggregate cancellation
counts, not passenger names, phone numbers, or ticket IDs. Booking details,
including passenger name, age, and phone number, are kept in that browser's
local storage; up to 20 unique phone numbers can be saved on a device and used
to find that browser's saved tickets. Tickets and numbers do not sync across
browsers or devices. Phone number alone is not secure identity verification;
use lookup only on a private device. Do not use this sample app to store real
passenger information or accept real payments without adding authentication,
privacy controls, and an authorized payment provider.

## Demo behavior

- Seat availability is checked for the exact route segment and journey date.
  A seat booked from Manmad to Hyderabad can also be booked from Shirdi to
  Manmad because the journeys do not overlap.
- Search supports General (GEN), Sleeper (SL), and AC 3 Tier (3A) demo classes.
  Each class has a separate seat inventory and indicative demo fare; General is
  treated as reserved seating in this prototype, not real unreserved rail travel.
- The server validates each selected seat at checkout. Sleeper and AC show a
  two-bay, 16-berth demo map with lower, middle, upper, side-lower, and side-upper
  positions; General uses reserved demo seats without berth types. The map
  highlights the selected coach, bay, and berth.
- Search shows currently available seats and cancelled-seat totals for the
  selected class, date, and overlapping route. Cancelling releases a seat for
  any passenger to book; the available count drops again if it is rebooked.
  Availability and cancellation totals refresh every 15 seconds while open.
- Booking records the selected journey date, class, and server booking timestamp.
  The search date defaults to India’s current date, blocks past dates, and the
  live clock and ticket registration time are displayed in IST. Ticket
  confirmation and history show the selected seat's berth type. Ticket
  cancellation requires confirmation and releases that class's seat segment in
  the configured SQLite or PostgreSQL inventory.
- Checkout offers simulated UPI, card, and net banking methods. It does not
  collect payment credentials or process real money. Successful demo checkouts
  show a printable ticket confirmation with the PNR and allocated seat.
- The ticket lookup can find and cancel active tickets saved in the current
  browser by the booking mobile number. It accepts Indian 10-digit numbers with
  optional `+91` or leading `0`; up to 20 unique numbers are stored per browser.
  Railway security and medical assistance
  is available through the official [RailMadad 139 helpline](https://railmadad.indianrailways.gov.in/madad/final/home.jsp).
  Food ordering links to [IRCTC eCatering / Food on Track](https://www.ecatering.irctc.co.in/);
  menu and delivery availability depend on the journey and PNR.
- Train tracking shows a schedule-based position and current update time for
  the selected journey date. It is not a GPS feed: real train location,
  schedules, fares, payment processing, and ticket issuance require authorized
  providers and are not included in this demo.
- The booking form, seat map, tracking route, and ticket list adapt to narrow
  mobile screens.

This is a prototype, not an official ticketing service. It does not
include user accounts, a real payment gateway, or live train location data.
