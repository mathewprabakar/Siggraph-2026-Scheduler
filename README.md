# SIGGRAPH 2026 Scheduler

A lightweight personal schedule builder for SIGGRAPH 2026 in Los Angeles.

Use it here: https://mathewprabakar.github.io/Siggraph-2026-Scheduler/

This is an unofficial companion tool for browsing the public SIGGRAPH schedule,
building a personal "My Day" view, and sharing that schedule with another device.

## How to Use It

1. Open the app.
2. Browse or search for sessions you care about.
3. Use filters to narrow by day, program, room, interest area, keyword, or
   registration category.
4. Add sessions to My Day.
5. Use the My Day timeline to compare choices, set priority, check locations,
   export to your calendar, or share your schedule.

## What It Does

- Browse SIGGRAPH 2026 sessions by day, program, interest area, keyword,
  registration category, and room.
- Search session titles, rooms, and tracks.
- Add sessions to My Day and view them on a timeline.
- Set priority on saved sessions so your most important picks stand out.
- Open the original SIGGRAPH schedule page for a session.
- View LA Convention Center floor-plan locations when room data is available.
- Open Google Maps for off-site venues.
- Export your schedule to a calendar file.
- Share the app, or share your selected schedule, with a QR code or link.
- Hide registration badges if you have a full conference pass and do not need
  category hints.
- Switch between SIGGRAPH, light, and dark themes.

## Privacy

Your selected sessions are saved in your browser's local storage. There is no
account, server sync, or backend database.

When you choose to include your schedule in a share link, the selected sessions
are encoded into the URL so another device can restore them. After the app loads
that shared schedule, it returns the address bar to the normal app URL.

## Notes

The schedule data comes from the public SIGGRAPH 2026 conference schedule and is
refreshed into a local JSON catalog. The official SIGGRAPH website remains the
source of truth for session details, registration requirements, and last-minute
changes.

This project is not affiliated with or endorsed by SIGGRAPH, ACM SIGGRAPH, or
the conference organizers.

## Development

Developer setup, catalog refresh instructions, and smoke-test commands live in
[DEVELOPMENT.md](DEVELOPMENT.md).

## License

MIT. See [LICENSE](LICENSE).
