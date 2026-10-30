"""Pure parsing of Daisy Family API payloads (no Home Assistant imports).

All datetimes are naive and in the municipality's local time, exactly as the
API returns them.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import html
import re
from datetime import date, datetime, timedelta
from typing import Any

PREVIEW_LENGTH = 200
BULLETIN_CONTENT_LENGTH = 4000
MAX_BULLETINS = 20  # default of the "max bulletins" option

MISSING_RESERVATIONS_TEXT = (
    "Hoitoaikoja tai poissaoloja ilmoittamatta lukkiutuvalle ajanjaksolle"
)

_BREAKS = re.compile(r"<br\s*/?>|</p>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _pick_placement(placements: list[dict[str, Any]], now: datetime) -> dict | None:
    """Placement covering `now`, otherwise the most recently started one."""
    if not placements:
        return None
    current = []
    for p in placements:
        start = parse_dt(p.get("Start"))
        end = parse_dt(p.get("End"))
        if (start is None or start <= now) and (end is None or now <= end):
            current.append(p)
    pool = current or placements
    return max(pool, key=lambda p: parse_dt(p.get("Start")) or datetime.min)


def _parse_fi_date(value: Any) -> str | None:
    """"01.08.2026" -> "2026-08-01"."""
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*", value)
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def _clean(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def parse_centres(payload: Any) -> list[dict[str, Any]]:
    """Flatten getcentreinfos into one record per (centre, group, child placement)."""
    records: list[dict[str, Any]] = []
    for centre in payload if isinstance(payload, list) else []:
        open_time = centre.get("OpenTime") or {}
        base = {
            "centre": _clean(centre.get("CentreName")),
            "address": _clean(centre.get("CentreAddress")),
            "phone": _clean(centre.get("CentrePhone")),
            "manager": _clean(centre.get("ManagerName")),
            "manager_phone": _clean(centre.get("ManagerPhone")),
            "open_type": _clean(open_time.get("CentreOpenType")),
            "open_times": _clean(open_time.get("OpenTimes")),
        }
        for group in centre.get("GroupInfoList") or []:
            gbase = {
                **base,
                "group": _clean(group.get("GroupName")),
                "group_phone": _clean(group.get("GroupPhone")),
                "group_open_times": [
                    t.strip() for t in group.get("GroupOpenTimeList") or [] if isinstance(t, str)
                ],
            }
            for kid in group.get("ChildPlInfoList") or []:
                records.append(
                    {
                        **gbase,
                        "child_id": kid.get("ChildId"),
                        "child_name": _clean(kid.get("ChildName")),
                        "placement_start": _parse_fi_date(kid.get("PlacementStart")),
                        "placement_end": _parse_fi_date(kid.get("PlacementEnd")),
                    }
                )
    return records


def _pick_centre_record(
    child: dict[str, Any], records: list[dict[str, Any]], today: str
) -> dict[str, Any] | None:
    """Find the centre record of a child: by id, else by name, else by centre and group."""
    mine = [r for r in records if r["child_id"] == child["id"]]
    if not mine and child.get("full_name"):
        name = child["full_name"].strip().casefold()
        mine = [r for r in records if (r["child_name"] or "").casefold() == name]
    if not mine and child.get("centre") and child.get("group"):
        mine = [
            r
            for r in records
            if r["centre"] == _clean(child["centre"]) and r["group"] == _clean(child["group"])
        ]
        if len(mine) != 1:  # several children in one group: cannot tell which is which
            return None
    if not mine:
        return None
    group = _clean(child.get("group"))
    in_group = [r for r in mine if group and r["group"] == group] or mine
    current = [
        r
        for r in in_group
        if (not r["placement_start"] or r["placement_start"] <= today)
        and (not r["placement_end"] or today <= r["placement_end"])
    ]
    return max(current or in_group, key=lambda r: r["placement_start"] or "")


def parse_children(
    children_payload: dict[str, Any],
    times_payload: dict[str, Any],
    now: datetime,
    centres: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build per-child data from getchildren + getnursingtimes (+ centre info) responses."""
    result: dict[str, dict[str, Any]] = {}
    for child in children_payload.get("ListChildren") or []:
        placement = _pick_placement(child.get("Placements") or [], now)
        first = (child.get("FirstName") or "").strip()
        result[child["Id"]] = {
            "id": child["Id"],
            "name": first.split(" ")[0] if first else (child.get("Name") or "?"),
            "full_name": child.get("Name") or first,
            "centre": placement.get("Centre") if placement else None,
            "group": placement.get("Group") if placement else None,
            "placement_start": parse_dt(placement.get("Start")) if placement else None,
            "placement_end": parse_dt(placement.get("End")) if placement else None,
            "centre_info": None,
            # filled in below
            "reservations": [],
            "absence_dates": [],
            "actuals": {},
            "arrived": None,
            "departed": None,
        }

    for child in result.values():
        child["centre_info"] = _pick_centre_record(child, centres or [], now.date().isoformat())

    today = now.date()
    for week in times_payload.get("WeekList") or []:
        for day in week.get("DayList") or []:
            day_date = parse_dt(day.get("Date"))
            if day_date is None:
                continue
            d = day_date.date()
            for item in day.get("NursingTimes") or []:
                child = result.get(item.get("PersonId"))
                start, end = parse_dt(item.get("Start")), parse_dt(item.get("End"))
                if child and start and end:
                    child["reservations"].append(
                        {"start": start, "end": end, "locked": bool(day.get("IsLockedDate"))}
                    )
            for status in day.get("Statuses") or []:
                child = result.get(status.get("PersonId"))
                if not child:
                    continue
                kind = status.get("Type")
                if kind in ("I", "O"):
                    # Actual arrival (I: Start) and departure (O: End) of any day
                    act = child["actuals"].setdefault(d, {"arrived": None, "departed": None})
                    if kind == "I":
                        t = parse_dt(status.get("Start"))
                        if t and (act["arrived"] is None or t < act["arrived"]):
                            act["arrived"] = t
                    else:
                        t = parse_dt(status.get("End"))
                        if t and (act["departed"] is None or t > act["departed"]):
                            act["departed"] = t
                if kind == "A":
                    if d not in child["absence_dates"]:
                        child["absence_dates"].append(d)
                elif d == today and kind == "I":
                    # Start holds the actual arrival time
                    arrived = parse_dt(status.get("Start"))
                    if arrived and (child["arrived"] is None or arrived > child["arrived"]):
                        child["arrived"] = arrived
                elif d == today and kind == "O":
                    # End holds the actual departure time
                    departed = parse_dt(status.get("End"))
                    if departed and (
                        child["departed"] is None or departed > child["departed"]
                    ):
                        child["departed"] = departed

    for child in result.values():
        child["reservations"].sort(key=lambda r: r["start"])
        child["absence_dates"].sort()
        _derive(child, now)
    return result


def _history(child: dict[str, Any], today: date) -> list[dict[str, Any]]:
    """Reserved and actual care of the days up to and including today."""
    rows: dict[date, dict[str, Any]] = {}

    def row(d: date) -> dict[str, Any]:
        return rows.setdefault(
            d,
            {"date": d, "start": None, "end": None, "arrived": None, "departed": None, "absent": False},
        )

    for r in child["reservations"]:
        d = r["start"].date()
        if d <= today:
            entry = row(d)
            entry["start"], entry["end"] = r["start"], r["end"]
    for d, act in child["actuals"].items():
        if d <= today and (act["arrived"] or act["departed"]):
            entry = row(d)
            entry["arrived"], entry["departed"] = act["arrived"], act["departed"]
    for d in child["absence_dates"]:
        if d <= today:
            row(d)["absent"] = True
    return [rows[d] for d in sorted(rows)]


def _derive(child: dict[str, Any], now: datetime) -> None:
    today = now.date()
    child["history"] = _history(child, today)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    todays = [r for r in child["reservations"] if r["start"].date() == today]
    upcoming = [r for r in child["reservations"] if r["end"] > now]
    child["today_reservation"] = todays[0] if todays else None
    child["next_reservation"] = upcoming[0] if upcoming else None
    child["upcoming_reservations"] = upcoming[:10]
    child["upcoming_all"] = upcoming
    child["absent_today"] = today in child["absence_dates"]
    child["upcoming_absences"] = [d for d in child["absence_dates"] if d >= today]
    child["next_absence"] = child["upcoming_absences"][0] if child["upcoming_absences"] else None

    if child["arrived"] is None:
        child["at_daycare"] = False
    else:
        child["at_daycare"] = child["departed"] is None or child["departed"] < child["arrived"]

    seconds = sum(
        (r["end"] - r["start"]).total_seconds()
        for r in child["reservations"]
        if week_start <= r["start"].date() < week_end
    )
    child["reserved_hours_week"] = round(seconds / 3600, 2)


def _newest_content(models: list[dict[str, Any]] | None) -> str | None:
    """Full text of the newest message in a thread, if the API sent it."""
    if not models:
        return None
    newest = max(models, key=lambda m: parse_dt(m.get("Saved") or m.get("Sent")) or datetime.min)
    return newest.get("Content")


def parse_messages(payload: dict[str, Any], limit: int = 10) -> dict[str, Any]:
    """Summarise MessageData: unread count and the newest thread."""
    threads = (payload.get("ListMessage") or {}).get("listMessage") or []
    unread_threads = [t for t in threads if (t.get("CountNotReadMessages") or 0) > 0]
    newest = max(
        threads, key=lambda t: parse_dt(t.get("NewestSaved")) or datetime.min, default=None
    )
    # MessageThreads holds the full text, but the API only returns it for the
    # newest few threads. Older threads fall back to the preview.
    full: dict[str, list[dict[str, Any]]] = {}
    participants: dict[str, list[str]] = {}
    for thread in payload.get("MessageThreads") or []:
        models = thread.get("listMessageModels") or []
        if models:
            tid = models[0].get("ThreadId")
            full[tid] = models
            participants[tid] = [
                x.get("Name") or x.get("DisplayName")
                for x in thread.get("listThreadParticipants") or []
                if x.get("Name") or x.get("DisplayName")
            ]

    latest = None
    if newest:
        sender = newest.get("MessageSender") or {}
        latest = {
            "title": newest.get("Title"),
            "preview": (newest.get("PartContent") or "")[:PREVIEW_LENGTH],
            "content": _newest_content(full.get(newest.get("ThreadId"))),
            "sender": sender.get("DisplayName") or sender.get("Name"),
            "sent": parse_dt(newest.get("NewestSaved")),
            "unread": (newest.get("CountNotReadMessages") or 0) > 0,
        }
    unread_list = sorted(
        unread_threads,
        key=lambda t: parse_dt(t.get("NewestSaved")) or datetime.min,
        reverse=True,
    )[:5]
    all_threads = sorted(
        threads,
        key=lambda t: parse_dt(t.get("NewestSaved")) or datetime.min,
        reverse=True,
    )[: max(0, limit)]
    def _full(t: dict[str, Any]) -> dict[str, Any]:
        models = full.get(t.get("ThreadId"))
        if not models:
            return {"content": None, "parts": [], "participants": []}
        parts = [
            {
                "sender": (m.get("MessageSender") or {}).get("Name"),
                "sent": parse_dt(m.get("Saved") or m.get("Sent")),
                "content": m.get("Content"),
                "attachments": [
                    {
                        "id": a.get("Id"),
                        "name": a.get("FileName"),
                        "mime_type": a.get("MimeType"),
                    }
                    for a in m.get("ListAttachments") or []
                ],
            }
            for m in models
        ]
        parts.sort(key=lambda x: x["sent"] or datetime.min)
        return {
            "content": parts[-1]["content"],
            "parts": parts,
            "participants": participants.get(t.get("ThreadId"), []),
        }

    return {
        "unread_threads": payload.get("NotReadThreads", len(unread_threads)),
        "total_threads": len(threads),
        "latest": latest,
        "all": [
            {
                "thread_id": t.get("ThreadId"),
                "title": t.get("Title"),
                "preview": (t.get("PartContent") or "")[:PREVIEW_LENGTH],
                **_full(t),
                "sender": (t.get("MessageSender") or {}).get("DisplayName")
                or (t.get("MessageSender") or {}).get("Name"),
                "sent": parse_dt(t.get("NewestSaved")),
                "unread": (t.get("CountNotReadMessages") or 0) > 0,
                "unread_count": t.get("CountNotReadMessages") or 0,
                "messages": t.get("CountMessages") or 0,
                "attachments": t.get("CountAttachment") or 0,
            }
            for t in all_threads
        ],
        "recent_unread": [
            {
                "title": t.get("Title"),
                "sender": (t.get("MessageSender") or {}).get("Name"),
                "sent": t.get("NewestSaved"),
            }
            for t in unread_list
        ],
    }


def _clean_text(text: str | None, limit: int) -> str:
    """Strip any markup and collapse whitespace; plain text passes through."""
    text = _TAGS.sub("", _BREAKS.sub("\n", text or ""))
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    return text[:limit]


def parse_bulletins(
    payload: Any, now: datetime, limit: int = MAX_BULLETINS
) -> dict[str, Any]:
    """Active bulletin board posts, newest first."""
    items: list[dict[str, Any]] = []
    for post in payload if isinstance(payload, list) else []:
        end = parse_dt(post.get("End"))
        if end is not None and end.date() < now.date():
            continue
        items.append(
            {
                "id": post.get("Id"),
                "title": post.get("Title"),
                "content": _clean_text(post.get("Content"), BULLETIN_CONTENT_LENGTH),
                "date": parse_dt(post.get("Date")) or parse_dt(post.get("Start")),
                "end": end,
                "recipient": (post.get("Recipient") or {}).get("Name"),
                "attachments": [
                    a.get("FileName") for a in post.get("ListAttachments") or []
                ],
                "files": [
                    {
                        "id": a.get("Id"),
                        "name": a.get("FileName"),
                        "mime_type": a.get("MimeType"),
                    }
                    for a in post.get("ListAttachments") or []
                ],
            }
        )
    items.sort(key=lambda i: i["date"] or datetime.min, reverse=True)
    return {
        "count": len(items),
        "items": items[: max(0, limit)],
        "latest": items[0] if items else None,
    }


def _scalars(item: Any) -> dict[str, Any]:
    """Keep only plain values so the dict is safe as a state attribute."""
    if not isinstance(item, dict):
        return {"value": str(item)}
    return {
        k: v for k, v in item.items() if isinstance(v, str | int | float | bool | None)
    }


def parse_notices(
    main_stats: dict[str, Any] | None,
    vacation: dict[str, Any] | None,
    times_payload: dict[str, Any],
) -> dict[str, Any]:
    """Care time notices shown on the Daisy start page."""
    status = (main_stats or {}).get("NursingTimesStatus") or {}
    rows = [
        r for r in (vacation or {}).get("NotificationTextRows") or [] if isinstance(r, str)
    ]
    return {
        # AllDone is False when reservations/absences are missing for a period
        # that is about to lock.
        "reservations_missing": status.get("AllDone") is False,
        "reservations_missing_children": [
            _scalars(i) for i in status.get("listChildNursingTimeStatus") or []
        ],
        "lock_time": times_payload.get("ShortestLockTime"),
        "days_to_select": times_payload.get("DaysToBeSelected"),
        "locked_days_to_select": times_payload.get("LockedDaysToBeSelected"),
        "vacation_missing": bool((vacation or {}).get("ShowNotification")) and bool(rows),
        "vacation_rows": rows,
    }


_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
)


def _detect_image_type(data: bytes) -> str | None:
    for magic, content_type in _IMAGE_MAGIC:
        if data.startswith(magic):
            return content_type
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def parse_pictures(payload: Any) -> dict[str, dict[str, Any]]:
    """Decode getprofilepictures into {person_id: {bytes, content_type, digest}}.

    The API returns `base64,<data>` (a data URI without the `data:image/...;`
    part) or null for children without a picture.
    """
    result: dict[str, dict[str, Any]] = {}
    for item in payload if isinstance(payload, list) else []:
        person_id = item.get("PersonID") if isinstance(item, dict) else None
        raw = item.get("ImageBase64") if isinstance(item, dict) else None
        if not person_id or not isinstance(raw, str) or not raw:
            continue
        if "," in raw[:64]:  # strip "base64," / "data:image/jpeg;base64,"
            raw = raw.split(",", 1)[1]
        raw = re.sub(r"\s", "", raw)
        try:
            data = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=True)
        except (binascii.Error, ValueError):
            continue
        content_type = _detect_image_type(data)
        if content_type is None:
            continue
        result[person_id] = {
            "bytes": data,
            "content_type": content_type,
            "digest": hashlib.sha1(data).hexdigest(),  # noqa: S324 - change detection only
        }
    return result


_PERIOD_ROW = re.compile(
    r"(?P<name>[^:()]+?)\s*\(\s*"
    r"(?P<sd>\d{1,2})\.(?P<sm>\d{1,2})\.(?P<sy>\d{4})\s*[-\u2013]\s*"
    r"(?P<ed>\d{1,2})\.(?P<em>\d{1,2})\.(?P<ey>\d{4})\s*\)"
)
_DEADLINE = re.compile(r"tehtävä\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\s+mennessä")


def _to_date(value: Any) -> date | None:
    parsed = parse_dt(value)
    return parsed.date() if parsed else None


def _fi_date(day: str, month: str, year: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _vacation_names(
    vacation: dict[str, Any] | None,
) -> tuple[dict[tuple[date, date], str], date | None]:
    """Best effort: holiday period names and the reservation deadline.

    Only the `vacationstatus` text names a period, e.g. "...: Joululoma 2026
    (23.12.2026-6.1.2027)." and "Loma-ajan varaukset on tehtävä 22.11.2026
    mennessä."
    """
    names: dict[tuple[date, date], str] = {}
    deadline: date | None = None
    for row in (vacation or {}).get("NotificationTextRows") or []:
        if not isinstance(row, str):
            continue
        match = _PERIOD_ROW.search(row)
        if match:
            start = _fi_date(match["sd"], match["sm"], match["sy"])
            end = _fi_date(match["ed"], match["em"], match["ey"])
            name = match["name"].strip()
            if start and end and name:
                names[(start, end)] = name
        found = _DEADLINE.search(row)
        if found and deadline is None:
            deadline = _fi_date(found[1], found[2], found[3])
    return names, deadline


def _group_ranges(days: list[date]) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    for day in days:
        if ranges and (day - ranges[-1][1]).days == 1:
            ranges[-1] = (ranges[-1][0], day)
        else:
            ranges.append((day, day))
    return ranges


def parse_calendar(
    payload: Any, vacation: dict[str, Any] | None, today: date
) -> dict[str, Any] | None:
    """Holiday periods and public holidays from getnursingtimesquick.

    `VacationPeriodList` lists every day of the municipality's holiday periods,
    `HolidayList` the public holidays with their names. Periods that have not
    ended yet are returned (an ongoing one first, with `ongoing` set).
    """
    if not isinstance(payload, dict):
        return None
    days = sorted(
        {d for d in (_to_date(x) for x in payload.get("VacationPeriodList") or []) if d}
    )
    names, deadline = _vacation_names(vacation)
    periods: list[dict[str, Any]] = []
    deadline_used = False
    for start, end in _group_ranges(days):
        if end < today:
            continue
        name = names.get((start, end))
        period = {
            "name": name,
            "start": start,
            "end": end,
            "days": (end - start).days + 1,
            "ongoing": start <= today,
            "days_until_start": max(0, (start - today).days),
            "reservation_deadline": None,
        }
        if name and deadline and not deadline_used:
            period["reservation_deadline"] = deadline
            deadline_used = True
        periods.append(period)

    holidays: list[dict[str, Any]] = []
    for item in payload.get("HolidayList") or []:
        if not isinstance(item, dict):
            continue
        day = _to_date(item.get("Date"))
        if day and day >= today and item.get("Name"):
            holidays.append(
                {
                    "date": day,
                    "name": item["Name"],
                    "eve_compensation": bool(item.get("EveCompensation")),
                    "days_until": (day - today).days,
                }
            )
    holidays.sort(key=lambda h: h["date"])
    return {
        "vacations": periods,
        "next_vacation": periods[0] if periods else None,
        "holidays": holidays[:40],
        "next_holiday": holidays[0] if holidays else None,
    }
