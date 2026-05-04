# Artist Roster DB Setup

## What was done

1. Added new database models in `app/models.py`:
   - `Artist` mapped to `artists`
   - `Media` mapped to `media`

2. Implemented requested columns:
   - `artists`: `id`, `name`, `title`, `bio`, `created_at`, `updated_at`
   - `media`: `id`, `artist_id`, `media_type`, `media_url`, `thumbnail_url`, `created_at`

3. Added cascade delete behavior:
   - `media.artist_id` -> foreign key to `artists.id` with `ON DELETE CASCADE`

4. Added SQL script file:
   - `artist_roster_tables.sql`
   - Contains the exact `CREATE TABLE` statements requested.

## How tables are created in this project

This project already runs:

- `Base.metadata.create_all(bind=engine)`

on app startup (in `app/main.py`), so with the new models present, the tables can be created automatically when the app starts (if they do not already exist).

## For later admin flow

You can now build an admin page to:

- create artist entries (`artists`)
- upload/add multiple image/video records per artist (`media`)
- show media list per artist and manage updates/deletes

## Admin page implementation added

Artist roster admin management is now available with:

- Route: `/admin/artist` (also `/admin/artists`)
- Template: `templates/adminartist.html`
- Styles: `static/pages/admin_artist.css`
- Admin home link: `templates/admin_page.html` -> "Open AdminArtist Page"

### Features added

- Create artist (name, title, bio)
- Add media to artist:
  - image via direct URL
  - image via file upload (S3)
  - video via URL
  - optional thumbnail URL
- List artists with media count
- Delete artist (linked media removed via FK cascade)
- List latest artist media
- Delete media entry
