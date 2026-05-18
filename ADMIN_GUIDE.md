# MUSIKA Admin — detailed how-to

This guide matches the current admin UI (URLs, button labels, and delete confirmations). Replace `yoursite.com` with your real domain (or use `http://127.0.0.1:8000` when running locally).

---

## 1. How to log in

1. Open **`https://yoursite.com/admin/login`** (or your local URL + `/admin/login`).
2. Enter your **admin email** and **password**.
3. Submit the form. On success you are sent to **`/admin`** (Admin Home).

**If login fails:** check spelling, caps lock, and that your account exists in the database as an admin user.

**How to log out:** on any admin page, use the left sidebar and click **Logout** (this posts to `/logout`).

---

## 2. Layout you see on every admin page

- **Left sidebar** — links to: Event, Artist, Gallery, Admission Setup, Admissions, Inbox, Subscribers, Logout.
- **Badges** on Admissions / Inbox / Subscribers — counts of **new** items (same idea as “unread”).
- **Admin Home** (`/admin`) — shortcut cards to Inbox, Subscribers, and Admissions; it is not the only way to open those pages.

**Extra page (not in the sidebar):** **Courses / fee builder** — `https://yoursite.com/admin/courses` (see [§10](#10-admin-courses--fee-structures-admincourses)).

---

## 3. Admin Home (`/admin`)

| What you do | How |
|---------------|-----|
| See what is new | Read the three numbers: New Messages, New Subscriptions, New Admissions. |
| Open a list | Click the card to go to Inbox, Subscribers, or Admissions. |
| Go elsewhere | Use the sidebar (Event, Artist, Gallery, etc.). |

Nothing is “created” only on this page; it is an overview.

---

## 4. Events (`/admin/events`)

### 4.1 Create an event

1. Go **Event** in the sidebar.
2. In **Create Event**, fill in:
   - **Title** (required)
   - **Description** (optional)
   - **Location**, **State** (optional)
   - **Event Date** and **Event Time** (required)
   - **Event Images** — you may pick **multiple** image files (optional at create time, but usually you want at least one)
3. Click **Create Event**.

### 4.2 Edit an event

1. Find the event under **Manage Events**.
2. Open **Edit event** (disclosure).
3. Change fields or add more images with **Add more images (optional)**.
4. Click **Save changes**.

### 4.3 Delete one image from an event

1. Under that event, find the image thumbnail.
2. Click **Delete Image**.
3. In the box that appears, type exactly **`delete`** (lowercase).
4. Click **Confirm Delete**.

### 4.4 Delete the whole event

1. Scroll to the bottom of that event’s card.
2. Click **Delete Event**.
3. Confirm in the **browser popup** (OK / Cancel). This removes the event and its images.

---

## 5. Artist (Faculty roster) (`/admin/artist`)

Use the two tabs at the top: **Create Faculty** and **Add Media**.

### 5.1 Create a faculty member

1. Tab **Create Faculty** (default).
2. **Profile:** Name (required), Role/title, Bio (optional), **Background image**, **Hero image** (file fields as shown).
3. **Social & contact:** Facebook, Instagram, X, WhatsApp, Email — fill what you need (URLs where indicated).
4. **Music & streaming:** YouTube, Spotify, YouTube Music, Amazon Music, Apple Music — optional URLs.
5. Click **Create artist**.

### 5.2 Add gallery images for an existing faculty member

1. Switch to tab **Add Media**.
2. **Artist** — choose the person from the dropdown (required).
3. **Upload image** — choose a file (required; the form expects an image file).
4. Click **Add media**.

### 5.3 View or delete an artist’s media files

1. In **Manage artists**, click **View media** for that person (opens `/admin/artist/<id>/media`).
2. To remove one item: click **Delete**, type **`delete`**, then **Confirm Delete**. Use **×** to cancel.

### 5.4 Edit a faculty profile

1. In **Manage artists**, open **Edit profile, links & featured** for that row.
2. Update fields; for images, **leave file inputs empty** to keep the current file.
3. Click **Save changes**.

### 5.5 Delete a faculty member

1. At the bottom of their card, click **Delete artist**.
2. Type exactly **`delete <Full name as shown>`** — for example, if the name is `Jane Doe`, type **`delete Jane Doe`** (same spelling and spaces as on screen; matching is case-insensitive).
3. Click **Confirm Delete**. Use **×** to cancel.

---

## 6. Gallery (`/admin/gallery`)

### 6.1 Create a category

1. In **Create Category**, enter **Category Name**.
2. Click **Create Category**.

### 6.2 Upload an image into a category

1. In **Upload Image**, choose **Select Category** (required).
2. Optional **Caption**.
3. Choose **Image** file (required).
4. Click **Upload**.

### 6.3 Open one category to see only its images

1. Under **Manage Categories**, click **View** for that category.

### 6.4 Delete a category

1. On the main Gallery page, click **Delete Category** for that row.
2. Type exactly **`delete <CategoryName>`** as the label shows (e.g. **`delete Concerts`** if the category name is `Concerts`).
3. Click **Confirm Delete**. Use **×** to cancel.

### 6.5 Delete a single gallery image

**From the main Gallery page — section “All Uploads”:**

- Click **Delete Image** on the card (submits immediately — no typed confirmation on this grid).

**From a category page** (`View` → category uploads):

- Same: **Delete Image** on the card.

Use **Previous** / **Next** when there are many uploads.

---

## 7. Admission setup (`/admin/admission-options`)

Configure payment text, QR, and the dropdowns on the public admission form.

### 7.1 Fee payment details (bank / UPI / QR)

1. Fill **Account holder name**, **Bank account number**, **IFSC**, **UPI ID** as needed.
2. **QR code:** upload or replace the **QR image** file if you use scan-to-pay.
3. Click **Save fee details**.

### 7.2 Add a discipline (course)

1. Under **Add discipline**, enter **Discipline / Course Name** (e.g. Piano).
2. Click **Add discipline**.  
   You need at least one discipline before grades and teachers make sense.

### 7.3 Add a grade (under a discipline)

1. Under **Add grade**, select **Discipline**, enter **Grade Name**, set **Sort Order** (number; lower often shows first).
2. Click **Add grade**.

### 7.4 Add a teacher (under a discipline)

1. Under **Add teacher**, select **Discipline**, enter **Teacher Name**.
2. Click **Add teacher**.

### 7.5 Delete discipline, grade, or teacher

- In the **Disciplines** list: **Delete Discipline** removes that course (use only if you intend to remove it).
- Next to each grade or teacher line: **Delete** — submits immediately (no “type delete” step on these buttons).

---

## 8. Admissions

### 8.1 List all applications (`/admin/admissions`)

| Action | Steps |
|--------|--------|
| **Open one application** | Click **View**. |
| **Download PDF** | Click **Download** (same row). |
| **Delete** | Click **Delete** → type **`delete`** in the box → **Confirm**. Click **×** to cancel the panel. |

### 8.2 One application — detail (`/admin/admissions/<id>`)

**Applicant data (main form)**

1. Edit any fields (personal details, address, course choices, etc.).
2. **Passport photo:** optional replacement upload; must be **under 1 MB** or the browser will alert and clear the file.
3. **Discipline / Grade / Teacher:** changing **Discipline** refreshes the grade and teacher lists; pick values again if needed.
4. Click **Save application details**.

**Office use only (review block)**

1. Set **Status** (New, Reviewing, Accepted, Rejected, Waitlisted).
2. Set **Accepted** (Pending / Yes / No), fees, invoice fields, payment method, course dates, class type, **Remarks**.
3. Click **Save Review** (this saves the review form only — applicant edits use **Save application details** above).

**Contact shortcuts**

- **Send via WhatsApp** — opens WhatsApp (if configured for this applicant).
- **Send via mail** — sends follow-up email (only shown when an email exists).

**PDF**

- **Download PDF** — application as PDF.

**Delete this application**

- **Delete** → type **`delete`** → **Confirm** (or cancel with **×**).

---

## 9. Inbox and Subscribers

### 9.1 Inbox (`/admin/inbox`)

- Table of **contact form** messages: date, name, email, phone, subject, message.
- Long messages: use **Show full** / **Show less** inside the row.

There is no “delete message” or “reply inside app” button in the default template — you read here and respond from your normal email or phone.

### 9.2 Subscribers (`/admin/subscribers`)

- List of **newsletter** sign-ups: date and email.
- **Send newsletter** (top of page): subject, optional header image, message body, optional extra images (up to 5). Uses the same SMTP settings as other site emails.
- Tick row checkboxes and click **Send to selected subscribers**, or tick **Select all active subscribers** to email everyone active in the database (not only the rows shown on screen).
- Confirm in the browser dialog before send completes.

---

## 10. Admin Courses / fee structures (`/admin/courses`)

This page is **not** linked in the sidebar; open the URL directly or bookmark it.

1. Choose **Offline** or **Online** tab (two separate saved structures).
2. Set **Page title** if you want a custom heading on the public fees page.
3. Use **+ Add section** to add blocks; inside each section add **rows** with the column text fields.
4. Click **Save Online Structure** (the button label is fixed; it saves whichever mode tab you are on — Offline or Online).

If save fails, read the red **error** text at the top (often invalid or empty structure).

---

## 11. Delete confirmation cheat sheet

| Where | What to type or do |
|-------|---------------------|
| Event — remove one photo | Type **`delete`** then Confirm |
| Event — remove whole event | Browser **confirm** dialog only |
| Gallery — delete category | Type **`delete <Category name>`** exactly as labeled |
| Gallery — delete single image | **Delete Image** only (no typed phrase) |
| Artist — delete person | Type **`delete <Artist name>`** as labeled |
| Artist — delete media item | Type **`delete`** then Confirm |
| Admission — delete application | Type **`delete`** then Confirm |
| Admission setup — grade/teacher/discipline | **Delete** buttons (no typed phrase) |

---

## 12. After you change something

- Green / success messages and red / error messages at the top of a page tell you whether the last action worked.
- If the page does not change as expected, scroll to the top and read the message, then fix the form and submit again.

---

*Generated for the MUSIKA project admin templates and routes. If the app is updated, some labels or URLs may change; compare with the live site if in doubt.*
