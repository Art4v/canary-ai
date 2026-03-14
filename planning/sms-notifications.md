# SMS Notifications — Two-Way via Twilio

## Feature Goal

Two-way SMS: send news alerts and trading suggestions to users, and let them reply to act (e.g., confirm a trade, dismiss an alert). No app install required — works on any phone.

## Recommended Tool: Twilio

**Why Twilio?**

- Simplest setup for SMS — well-documented, mature API
- No app install needed on the user's end
- Official Python SDK (`twilio` package) integrates cleanly with FastAPI backend
- Australian phone numbers available (important for local sender ID)
- Webhook-based inbound replies — Twilio POSTs to a FastAPI endpoint when a user texts back

## Target Scale

- **Region**: Australia
- **Users**: Under 50
- **Cost estimate**: ~\$6/month for an AU phone number + a few dollars/month for messages at this scale (well under \$20/month total)

## What's Needed to Implement

1. **Twilio account + Australian phone number** — sign up at twilio.com, purchase an AU number with SMS capability
2. **`twilio` Python package** — add to backend dependencies (`pip install twilio`)
3. **Outbound send route** — backend calls Twilio API to send SMS to user's phone (news alert or trade suggestion)
4. **Inbound webhook route** — FastAPI endpoint that Twilio calls when a user replies; parses the reply and triggers the appropriate action (e.g., execute trade, acknowledge alert)

## Flow

```
Outbound:  Backend → Twilio API → User's phone (news/trade alert)
Inbound:   User replies → Twilio webhook → FastAPI endpoint → Process action
```

## Alternatives Considered

| Service           | Why Not                                                        |
|-------------------|----------------------------------------------------------------|
| Vonage (Nexmo)    | More complex setup, less intuitive Python SDK                  |
| AWS SNS + Pinpoint| Overkill for <50 users, requires more AWS infrastructure       |
| MessageBird       | Less AU number availability, smaller community/docs            |

All alternatives are viable but add unnecessary complexity for this scale and region.
