# Daisy Family – Home Assistant integration

[![Unofficial](https://img.shields.io/badge/integration-unofficial-orange)](#️-unofficial-and-made-with-ai)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11%2B-blue)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-custom-41BDF5)](https://hacs.xyz/)

A Home Assistant custom integration that fetches children's information, care times, absences, messages and bulletin board posts from the Daisy Family early-childhood-education service used by Finnish municipalities (e.g. `janakkala.daisyfamily.fi`). It also ships three custom Lovelace cards: a reservation calendar, messages and a bulletin board.

> The cards and entity names are available in Finnish and English. The language follows your Home Assistant language (Finnish → Finnish, any other language → English). Texts that come from the Daisy service itself (for example holiday names and the notice about missing care times) are in Finnish.

## ⚠️ Unofficial and made with AI

**This integration is unofficial.** It is not made, supported or endorsed by Daisy Family. Daisy Family is a trademark of its owner and the name is used here only to say which service the integration works with.

**The code and documentation were made with the help of AI (Claude, by Anthropic).** The AI wrote most of the code, the cards and this documentation, while a human guided the work, tested it on their own Home Assistant installation and approved the changes. The code has not been professionally reviewed for security or quality. Read it before use if you wish, especially since it handles your password and your children's data.

Please also note:
- Daisy Family has **no public API**. The integration uses the same undocumented API calls as the service's own web app. A service update can change those calls and **break the integration without notice**.
- The service's terms of use may restrict automated data retrieval. Check them and use the integration **at your own risk**, only with your own credentials and your own children's data.
- The integration fetches data every 15 minutes. It does not send messages and does not change care times or absences. The only write action towards Daisy is marking a message as read.
- The software is provided as is, without any warranty (see [license](#license)).

## Features

- Per-child care times, actual arrival and departure times, absences and care time lock status
- Messages with full text and attachments, bulletin board posts with attachments, marking a message as read
- Holiday periods, public holidays and alerts for missing care times
- Children's profile pictures, diagnostics and options (number of days and messages fetched)
- Cards: **reservation calendar**, **messages** and **bulletin board** (no separate installation needed)

## Requirements

- Home Assistant 2024.11 or newer
- A Daisy Family username and password (strong authentication does not work, see below)

## Installation

### Through HACS (custom repository)

1. HACS → ⋮ → **Custom repositories** → add the repository URL `https://github.com/Dis90/ha-daisyfamily` with type **Integration**.
2. Install **Daisy Family** and restart Home Assistant.

### Manually

1. Copy the folder `custom_components/daisyfamily` to the `config/custom_components/` folder of Home Assistant.
2. Restart Home Assistant.

### Setup

1. **Settings → Devices & services → Add integration → Daisy Family**.
2. Enter the service address (`janakkala.daisyfamily.fi` or just `janakkala`), your Daisy username and password.

Signing in requires a Daisy username and password. Strong authentication (bank credentials) does not work automatically. Create a password first through Daisy's own login. The username is shown under your name in the side menu of Daisy Family.

The password is stored in Home Assistant's own configuration storage like the credentials of other integrations. Data is not sent anywhere except to the Daisy Family service.

## Entities

Each child gets their own device. Entity names below are the English names; the integration also has Finnish translations.

| Entity | Content |
|---|---|
| Group | Name of the group. Attributes: daycare centre and the start and end date of the placement |
| Daycare centre | Name of the child's daycare centre. Attributes: `address`, `phone`, `manager`, `manager_phone`, `open_type`, `open_times`, `group`, `group_phone`, `group_open_times`, `placement_start` and `placement_end`. Fetched once a day for all children at once; if it is not available, only the name from the placement is shown |
| Care starts / ends today | Today's reservation (timestamp) |
| Next care time | Ongoing or next reservation. Attributes: end time and the next 10 reservations |
| Arrived / Left today | Actual times recorded by the daycare |
| At daycare | State "At daycare" when the child is checked in and not out, otherwise "Not at daycare" (state `on`/`off`) |
| Absent today | On if there is an absence entry for today |
| Next absence | Date. Attribute: all upcoming absence days |
| Reserved hours this week | Total duration of this week's reservations in hours |
| Care reservations | Number of upcoming reservations. The `reservations` attribute has all reservations from the fetched period, each with `date`, `weekday`, `start`, `end`, `hours`, `locked` (whether the reservation is locked) and a ready-made `text` (e.g. "Wed 28.10. 07:30–13:15"). The `locked_dates` attribute lists all locked days, including days without a reservation (for example absence days). The `history` attribute has the reservation (`start`, `end`), actual arrival and departure (`arrived`, `departed`) and `absent` for past days and today |
| Profile picture | The child's picture from Daisy (image entity). Only created for children who have a picture in Daisy. Fetched hourly and kept in Home Assistant |

Account-level entities:

| Entity | Content |
|---|---|
| Unread messages | Number of unread message threads, with the five newest unread ones as an attribute |
| Latest message | Title of the newest thread. Attributes: `sender`, `sent`, `preview` (start of the text), `content` (full message text) and `unread`. The full text is included when the API provides it for the newest thread |
| All messages | Total number of message threads. The `messages` attribute has all threads from newest to oldest: `title`, `sender`, `sent`, `preview`, `unread`, `unread_count`, `messages` (number of messages in the thread) and `attachments`, plus `content` (full text) and `parts` (the messages of the thread). The number of threads is set in the integration options (**Settings → Devices & services → Daisy Family → Configure**, default 10, maximum 100). The full text is fetched for every displayed thread (`GetMessageThread2`) and kept in memory until the thread changes, so the first update is slower if there are many messages. The attribute is large and is not recorded in history |
| Bulletin board posts | Number of active posts. The `posts` attribute has the newest posts (count in the options, default 20, maximum 100) with title, full text, date, validity, recipient, attachment names `attachments` and attachments `files` |
| Latest bulletin board post | Title of the newest post, with the text and attachments as attributes |
| Care times not reported | On when the Daisy front page reports missing care times or absences. The `message` attribute has Daisy's text, plus `lock_time`, `days_to_select`, `locked_days_to_select` and `children` |
| Holiday care times not reported | On when Daisy reports missing reservations for a holiday period. The `message` attribute has Daisy's own text (e.g. the deadline) and `rows` has the rows separately |
| Next holiday period | Start date of the ongoing or next holiday period. If the period is ongoing, `ongoing` is true and the state is its start date, which has already passed. Attributes: `end`, `days`, `days_until_start`, `name` and `reservation_deadline`, plus `upcoming` (the next five holiday periods) |
| Next public holiday | Date of the next public holiday (today counts). Attributes: `name` (e.g. "Christmas Eve"), `days_until`, `eve_compensation` and `upcoming` (the next five public holidays with names) |

**Diagnostics** (in the Diagnostic section of the account device):

| Entity | Description |
|---|---|
| Last successful update | Timestamp. Attributes: `last_attempt` (latest attempt) and `logins` (number of sign-ins, grows when the token expires) |
| Update duration | Duration of the latest update in seconds |
| Connection problem | `on` when the latest update failed or some part (e.g. messages or the bulletin board) could not be fetched. Attributes: `last_error`, `consecutive_failures` and `failed_parts`. The entity does not become `unavailable` when an error occurs |

A diagnostics report (with credentials and the server address removed) can also be downloaded from the integration menu.

Data is updated every 15 minutes. Holidays and public holidays are fetched for a two-year range and refreshed every six hours. Care times, actual times and absences are fetched for the period set in the options: days back (default 14, 0–365, fetching always starts from at least the Monday of the current week) and days ahead (default 77, 7–365). The options are under **Configure**. If Daisy does not accept too long a range, reduce the value.

## Phone notifications

Entity states change when a new message or bulletin arrives, and "Care times not reported" turns on when care times are missing, so they work directly as automation triggers. The examples below send a notification to two phones and open the right dashboard view when tapped. Change the entity IDs (check them under Settings → Devices & services → Daisy Family), the phone services (`notify.mobile_app_…`) and the dashboard paths to your own. Entity IDs depend on the language of your Home Assistant, because they are generated from the entity names.

Copy the automations one at a time: **Settings → Automations & scenes → Create automation → ⋮ → Edit in YAML**, and replace the content of the editor.

**1. Care times not reported**

```yaml
alias: "Daisy: care times not reported"
mode: single
variables:
  phones: [notify.mobile_app_phone_1, notify.mobile_app_phone_2]
  status: binary_sensor.daisy_family_janakkala_daisyfamily_fi_care_times_not_reported
triggers:
  - trigger: state
    entity_id: binary_sensor.daisy_family_janakkala_daisyfamily_fi_care_times_not_reported
    to: "on"
  - trigger: time
    at: "17:00:00"   # reminder if still open
conditions:
  - condition: state
    entity_id: binary_sensor.daisy_family_janakkala_daisyfamily_fi_care_times_not_reported
    state: "on"
actions:
  - repeat:
      for_each: "{{ phones }}"
      sequence:
        - action: "{{ repeat.item }}"
          data:
            title: "Care times not reported"
            message: >-
              {{ state_attr(status, 'message') }}
              {% set k = state_attr(status, 'children') %}
              {% if k %}Children: {{ k | join(', ') if k is iterable and k is not string else k }}{% endif %}
            data:
              tag: daisy_care_times          # a new notification replaces the previous one
              url: /dashboard-daycare/calendar
              clickAction: /dashboard-daycare/calendar
```

**2. New message**

```yaml
alias: "Daisy: new message"
mode: queued
variables:
  phones: [notify.mobile_app_phone_1, notify.mobile_app_phone_2]
  message: sensor.daisy_family_janakkala_daisyfamily_fi_latest_message
triggers:
  - trigger: state
    entity_id: sensor.daisy_family_janakkala_daisyfamily_fi_latest_message
    attribute: sent                        # changes when a new message arrives
    not_from: [unavailable, unknown]
conditions:
  - condition: template
    value_template: "{{ state_attr(message, 'unread') }}"
actions:
  - repeat:
      for_each: "{{ phones }}"
      sequence:
        - action: "{{ repeat.item }}"
          data:
            title: "Daisy: {{ state_attr(message, 'sender') }}"
            message: >-
              {{ states(message) }} –
              {{ state_attr(message, 'preview') | default('') | truncate(120) }}
            data:
              tag: daisy_message
              url: /dashboard-daycare/messages
              clickAction: /dashboard-daycare/messages
```

**3. New bulletin**

```yaml
alias: "Daisy: new bulletin"
mode: queued
variables:
  phones: [notify.mobile_app_phone_1, notify.mobile_app_phone_2]
  bulletin: sensor.daisy_family_janakkala_daisyfamily_fi_latest_bulletin_board_post
triggers:
  - trigger: state
    entity_id: sensor.daisy_family_janakkala_daisyfamily_fi_latest_bulletin_board_post
    not_from: [unavailable, unknown]
    not_to: [unavailable, unknown]
actions:
  - repeat:
      for_each: "{{ phones }}"
      sequence:
        - action: "{{ repeat.item }}"
          data:
            title: "Daisy: new bulletin"
            message: >-
              {{ states(bulletin) }}
              {% set v = state_attr(bulletin, 'valid_until') %}
              {% if v %}(valid until {{ as_datetime(v).strftime('%-d.%-m.') }}){% endif %}
            data:
              tag: daisy_bulletin
              url: /dashboard-daycare/messages
              clickAction: /dashboard-daycare/messages
```

The message automation follows the send time of the newest message (`sent`), so it also triggers when the title is the same as in the previous message. The `unread` condition prevents notifications for messages that are already read. The bulletin automation triggers when the title changes. The `not_from: [unavailable, unknown]` condition prevents needless notifications when Home Assistant starts.

## Care time locking

Daisy locks care time reservations and absences up to the Sunday of the next week, and locked days can no longer be edited. For example, during the week of 26–30 October (and the following weekend) days up to Sunday 8 November are locked, and on Monday 2 November the limit moves to Sunday 15 November. The integration does not calculate the lock limit itself, but shows the per-day lock flag (`IsLockedDate`) from Daisy's API as is. It appears as the `locked` value of each reservation in the `reservations` attribute of the Care reservations sensor, as the `locked_dates` attribute that lists all locked days (also days without a reservation, such as absence days), and as a 🔒 icon in the reservation calendar card.

If you want a reminder before locking, build it from the "Care times not reported" sensor. It tells you when there is still something to report.

## Reservation calendar card

The integration ships with its own Lovelace card that shows care times day by day in the style of Daisy: on the left the date, weekday, week number and 🔒 for a locked day, on the right each child's profile picture, name and a bar for the care time. Holidays and public holidays appear as an orange date tile (the name of the public holiday as a banner) and absences as an orange "Absent" marker. Weeks are separated with a "Week N" divider. Clicking a day (anywhere on it) opens a day window showing everyone's care times, the daycare centre and the group, with arrows to browse days (view only, absences cannot be marked). Today is outlined in green.

The card loads automatically, and no separate resource needs to be added. After an update, restart Home Assistant and refresh the browser (Ctrl+F5).

1. Edit the dashboard → **Add card** → **Daisy Family – reservation calendar** (in Finnish: *varauskalenteri*).
2. In the editor, select the children (each child's "Care reservations" entity). The name and profile picture are fetched from the child's device.
3. Holidays, public holidays and absences are fetched automatically from the integration's sensors, and can be hidden in the editor.
4. Adjust the number of days shown, how many previous days are shown (`days_back`, default 7) and whether children without care on that day are shown.

For past days the card shows the actual care times (solid bar) with the reserved time below it as a lighter bar. The card cannot show more past days than the integration has fetched, so also raise the "days back" option of the integration if needed.

At the bottom of the card you can see when the data was last updated (orange if over an hour ago) and a refresh button that fetches the data from Daisy right away. The timestamp comes from the diagnostic "Last successful update" sensor. The bar can be hidden with `show_updated: false`.

The card may appear only after the integration has started. If the card is not in the list, clear the browser cache. The time axis is 6–18 by default and expands automatically if a care time exceeds it.

The card can scroll automatically to the current day (`scroll_to_today`). The card then gets its own scrollbar (`max_height`, default 600 px) and scrolls to today on the first render. Updates do not move the scroll position, but the card scrolls to the current day again whenever it becomes visible again (e.g. when switching views).

YAML configuration:

```yaml
type: custom:daisyfamily-calendar-card
title: Care times
days: 14
show_empty: true
days_back: 7           # how many previous days are shown (default 7; 0 = only today and upcoming)
scroll_to_today: true  # scroll to the current day
max_height: 600        # px, 0 = no limit (scrolling uses 600 by default)
scroll_peek: 90        # px of the previous day left visible when scrolling
show_updated: true     # update time and refresh button at the bottom of the card
show_holidays: true
show_absences: true
entities:
  - sensor.matti_care_reservations
  - sensor.maija_care_reservations
```

## Reservations with a markdown card

A simple list without the custom card:

```yaml
type: markdown
title: Care reservations
content: >
  {% for r in state_attr('sensor.matti_care_reservations', 'reservations') %}
  - {{ r.text }}
  {% endfor %}
```

Change the entity name to your own.

## Messages card

The integration also ships with a card for all messages: **Daisy Family – messages** (in Finnish: *viestit*). It lists message threads (title, sender, start of the text, time, number of messages and number of attachments), and unread ones are shown in bold. Clicking a thread opens a window with the full message, the recipients and all messages of the thread.

1. Edit the dashboard → **Add card** → **Daisy Family – messages**.
2. Select the **All messages** sensor and the number of messages to show.

Attachments are shown below the message with their file names, and the **Open** button opens the attachment in a new tab. The download goes through Home Assistant (`/api/daisyfamily/attachment/...`) with a signed, short-lived link, so credentials are not passed to the browser. The link also works in the Home Assistant mobile app.

The card shows as many messages as are selected in the integration options (**Configure**). The full text is fetched for every displayed thread.

```yaml
type: custom:daisyfamily-messages-card
entity: sensor.daisy_family_janakkala_daisyfamily_fi_all_messages
max: 10
```

## Bulletin board card

The **Daisy Family – bulletin board** (in Finnish: *ilmoitustaulu*) card (`custom:daisyfamily-bulletins-card`) lists the bulletin board posts. Clicking opens the whole post with its recipient, validity period and attachments, and the **Open** button of an attachment opens the file in the same way as in messages. When adding the card, select the **Bulletin board posts** sensor.

```yaml
type: custom:daisyfamily-bulletins-card
entity: sensor.daisy_family_janakkala_daisyfamily_fi_bulletin_board_posts
max: 10
```

### Marking a message as read

When you open an unread message in the messages card, the card marks the thread as read in Daisy too. The change shows in Daisy and in the unread count in Home Assistant as soon as the integration has refreshed its data. The feature can be turned off in the card settings (`mark_read: false`). The service can also be called manually or from an automation:

```yaml
action: daisyfamily.mark_thread_read
data:
  thread_id: "d4b7a2c1-8e35-4f6a-9c20-5b1e7a3f9d68"
```

`thread_id` can be found in the `messages` attribute of the All messages sensor.

## Example automation

```yaml
alias: "Child arrived at daycare"
triggers:
  - trigger: state
    entity_id: binary_sensor.matti_at_daycare   # change to your own entity
    to: "on"
actions:
  - action: notify.notify
    data:
      message: "Matti has been checked in at daycare."
```

## Troubleshooting

First look at the diagnostic entities (Connection problem and Last successful update) or download the diagnostics report from the integration menu.

An example automation that notifies you if the data has not been updated:

```yaml
alias: Daisy Family is not updating
triggers:
  - trigger: state
    entity_id: binary_sensor.daisy_family_janakkala_daisyfamily_fi_connection_problem   # check the entity name
    to: "on"
    for: "01:00:00"
actions:
  - action: notify.notify
    data:
      message: "Daisy Family data could not be fetched within an hour: {{ state_attr('binary_sensor.daisy_family_janakkala_daisyfamily_fi_connection_problem','last_error') }}"
```

Add to `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.daisyfamily: debug
```

- **Wrong username or password although the credentials work in the browser:** report this, because then the sign-in request differs from the one the browser uses.
- **Sign-in succeeds but data does not load (401 errors in the log):** the service uses the token differently than the integration assumes. See "Known limitations".

## Known limitations

- Messages are not sent from the integration. A message can be marked as read from the messages card (when the message is opened) or with the `daisyfamily.mark_thread_read` service.
- Absences or care times cannot be changed from Home Assistant.

## Support and development

- Bug reports and suggestions: GitHub **Issues**. Include the HA log (`custom_components.daisyfamily` at debug level) and the diagnostics report.
- **Do not include credentials, cookies, `Authorization` headers, children's names or message contents in an issue.** If you share a browser HAR recording, remove all identifying information from it first, or sign out of Daisy afterwards.
- Because the API is undocumented, fixes are often based on what Daisy's web app actually sends. Recordings help, but they must be sanitised.

## License

The code and documentation are released under the [MIT license](LICENSE) (© Olli Suominen): you may use, modify and distribute them freely as long as the license and copyright notice stay included. The software is provided as is, without warranty.

The icon in the `brand/` folder is original to this project and is covered by the same license. No Daisy Family logos or other material are included.
