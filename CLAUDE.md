# CLAUDE.md

Guidance for working on this repository (Daisy Family Home Assistant integration, domain `daisyfamily`).

## What this is

An **unofficial**, AI-assisted Home Assistant custom integration for the Daisy Family service used by Finnish
municipalities. There is **no public API**: it uses the same undocumented JSON calls as the service's own web app,
so a service update can break it. Only the user's own credentials and children's data are used.
The code was developed against sanitised browser HAR recordings and verified on a real Home Assistant installation
by the maintainer (Olli Suominen, GitHub `Dis90`).

## Working agreements

- **Version stays 1.0.0** (`manifest.json`, `CARD_VERSION`/`MSG_CARD_VERSION`/`BUL_VERSION` in `__init__.py` and `www/*.js`)
  until the maintainer says otherwise. The tag `v1.0.0` / GitHub release is created by the maintainer.
- **Commit changes normally and push with a plain `git push`.** Do not rewrite history or force push unless the
  maintainer explicitly asks.
- **Code comments, docstrings and README in English.** The maintainer talks Finnish in chat; answer in Finnish.
  The only Finnish left in code is what must stay Finnish: regexes in `parser.py` that read Daisy's Finnish texts,
  and the Finnish translations (`translations/fi.json`, the `fi` block of `I18N` in each card).
- Cards and entity names are bilingual: Finnish when the Home Assistant language is `fi`, English otherwise.
  Add new card texts to both `fi` and `en` in `I18N`, and entity names to `strings.json`, `translations/fi.json` and `en.json`.
- README automation examples must be a **single automation each** (no leading `- `, no `automation:` key) so they
  paste into the automation editor's YAML mode. Use the new syntax (`triggers`/`trigger`/`actions`/`action`).
- Never put real names, ids (UUIDs), tokens or message contents in code, README or commits. Use made-up examples.
- Never commit or paste credentials, cookies or `Authorization` headers from HAR files. Ask the user to sanitise them.
- Daisy logos or other Daisy material must not be added. The icon in `brand/` is original.

## Layout (`custom_components/daisyfamily/`)

| File | Role |
|---|---|
| `api.py` | HTTP client. Logs in with username/password (`POST /api/auth/login`), sends a Bearer token, re-logs in after 8 min or on 401/403. No refresh token is used. |
| `coordinator.py` | `DataUpdateCoordinator`, 15 min. Fetches everything, caches slow data (pictures 1 h, holidays 6 h, centre info 24 h, full message threads until they change). Records diagnostics (`diag_*`). Optional parts are wrapped in `optional()` so one failing call does not fail the update. |
| `parser.py` | Pure functions turning Daisy payloads into the data the entities use (`parse_children`, `parse_messages`, `parse_bulletins`, `parse_calendar`, `parse_centres`, ...). Testable without Home Assistant. |
| `sensor.py`, `binary_sensor.py`, `image.py` | Entities. Large attributes are listed in `_unrecorded_attributes`. Diagnostic entities stay available when updates fail. |
| `config_flow.py` | Login, reauth and the options flow (days back/ahead, max messages, max bulletins; number boxes). |
| `views.py` | `DaisyAttachmentView`: proxies attachment downloads via signed, short-lived HA paths (also works in the mobile app). |
| `diagnostics.py` | Redacted diagnostics download. |
| `__init__.py` | Setup, static card paths, `daisyfamily.mark_thread_read` service. |
| `www/*.js` | Three vanilla-JS Lovelace cards (calendar, messages, bulletins). Each file is wrapped in an IIFE and has its own `I18N`. |

## Daisy API calls in use

`persons/getchildren/`, `nursingtimes/getnursingtimes/{month}/{start}/{end}` (the web app uses `getnursingtimes2`),
`nursingtimes/getnursingtimesquick/...` (holidays and vacation periods), `nursingtimes/vacationstatus`,
`Messages/MessageData/`, `Messages/GetMessageThread2`, `messages/setthreadread/`, `files/previewFile`,
`bulletinboards?type=parent`, `persons/getmainstats2`, `image/getprofilepictures/`, `centre/getcentreinfos`.

## Things learned about Daisy's data

- Day status types: `A` absence, `I` arrival, `O` departure.
- **Lock rule:** reservations and absences are locked up to the **Sunday of the next week**. The per-day flag is
  `IsLockedDate` (also set on days without reservations, e.g. absence days). It is exposed as `locked_dates`.
  `ShortestLockTime` only carries the request time of day, the date is that Sunday.
- `DaysToBeSelected` / `LockedDaysToBeSelected` are computed by Daisy over the **requested date range**
  (weekdays not `DateSelected`, split by lock window). They depend on the range we request and are left as is.
- `DateSelected` is `false` even for days with a reservation: it does not mean "has care time".
- `WeekHoliday` gives public holiday names per day; `ColorOfDay` is `#dfeef2` only on public holidays;
  neither adds information the integration lacks. Names of holiday periods (e.g. "Joululoma") come only from
  `vacationstatus` text, and only while reservations are missing.
- `getcentreinfos` lists centre, groups and children's placements (matched by id, then name, then centre and group).
- Attachments: `POST files/previewFile` returns a data URI, possibly without JSON quotes.

## Testing

No Home Assistant is needed for `parser.py`; load it as a package with a stub module (see git history) or run the
functions on sanitised sample payloads. Cards were tested in headless Chromium (Playwright) with stub `hass`
objects, a fake clock and both languages (`hass.locale.language`). Real-HA behaviour is verified by the maintainer.

## Ideas discussed, not built

- `calendar` entities for care times (read-only, from existing data), optionally an iCal feed with a secret token.
  Do not push events to external calendars: `calendar.create_event` cannot update or delete.
- Reminder before the lock using the "Care times not reported" sensor.
- A lighter "reservations only" refresh for the card's refresh button.
- Photo folders (`GrowthFolder`): fetch metadata rarely, proxy images on demand via signed paths, no files on disk.
- Quiet hours for polling were considered and advised against (evening is when reservations and messages arrive).
- HACS: needs a GitHub release/tag `v1.0.0`.
