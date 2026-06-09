# 🔗 Setting Up the Google Form for QR Code Registration

Follow these steps so every QR code scan opens **your** Google Form and the responses land in your Google Sheet.

---

## Step 1 — Create the Google Form

1. Open [forms.google.com](https://forms.google.com) and sign in with **your Google account**.
2. Click **Blank form** (or use a template).
3. Set the form title, e.g. **"Swahilipot Hub Event Registration"**.
4. Add the following questions (all required):

| Question | Type |
|---|---|
| Full Name | Short answer |
| Email Address | Short answer |
| Phone Number | Short answer |
| Event Name | Short answer *(will be pre-filled by QR)* |
| Will you attend? | Multiple choice: Yes / No / Already attended |

5. Click the **gear icon (Settings)** → enable **"Collect email addresses"** (optional but recommended).
6. Click **Send** → copy the **sharing link** — it looks like:
   ```
   https://docs.google.com/forms/d/e/1FAIpQLSxxxxxxxxxxxxxxxx/viewform
   ```

---

## Step 2 — Get the pre-fill entry IDs

1. In your form editor, click the **three-dot menu (⋮)** → **"Get pre-filled link"**.
2. Type a sample answer in the **Event Name** field (e.g. "Test Event").
3. Click **Get link** → copy the URL shown.  
   It will look like:
   ```
   https://docs.google.com/forms/d/e/1FAIpQLSxxx/viewform?usp=pp_url&entry.123456789=Test+Event
   ```
4. The `entry.123456789` part is the **entry ID** for the Event Name field.

---

## Step 3 — Update `events/models.py`

Open `events/models.py` and update these two lines near the top:

```python
# Replace with the real sharing URL from Step 1:
GOOGLE_FORM_BASE_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLSxxxxxxxxxxxxxxxx"          # ← paste your form ID here
    "/viewform?usp=pp_url"
)

# Replace with the real entry ID from Step 2:
GOOGLE_FORM_EVENT_FIELD = "entry.123456789"   # ← paste your entry ID here
```

Save the file.

---

## Step 4 — Regenerate QR codes for existing events

Run these Django management commands on your server:

```bash
python manage.py shell
```

Then in the shell:

```python
from events.models import Event
for event in Event.objects.all():
    event.google_form_url = ""   # clear so it regenerates
    event.qr_code = None
    event.save()
    print(f"Regenerated QR for: {event.title}")
exit()
```

---

## Step 5 — View responses in Google Sheets

1. In your form, click **Responses** tab → **green Sheets icon**.
2. This creates a linked Google Sheet where every form submission appears as a row.
3. You'll see: timestamp, full name, email, phone, event name, attendance status.
4. The sheet is owned by the Google account you used — you'll receive email
   notifications for every new response if you enable them under
   **Responses → "Get email notifications for new responses"**.

---

## How the QR code flow works

```
Attendee scans QR code at event venue
         ↓
Opens Google Form (pre-filled with event name)
         ↓
Attendee fills: Name, Email, Phone, Attendance
         ↓
Data saved to Google Sheet (linked to your Google account)
         ↓
Portal admin downloads report (PDF/Excel) — shows portal-registered users
```

> **Note:** The portal's own attendance report (PDF/Excel) shows users who
> have a portal account. The Google Form captures *everyone* — including
> walk-in guests who don't have portal accounts. Use both for complete records.

