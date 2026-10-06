# Evergreen Reel scripts

30 scripts for @suresilly, first-job India, age 18 to 30. Nothing here is live. Each file is `<slug>.json`: `script` holds the fields `script.py` writes, `report` the hook, voice and shape.

- **Status: all 30 are reasoned.** The official sites in `suresilly/sources.json` could not be opened from the cloud session (the network policy refused them), so no script names a source or uses a number except a time. Nothing about law, pay, PF, notice or leave is stated.
- Audience: 20 for the employee (contrast, can_they), 10 for the manager (mirror). A contrast also shows a manager the better text, but its reply is for the employee.
- Every script passes `script.check` for its type, in order against the ones before it (no repeats), and `python -m pytest -q` passes (298 passed, 5 skipped).
- The `can_they` answers say what the outcome may depend on and what to ask, since no official page could be read. If you want a verified answer, open the page first and turn it into a FACT.

Format: type · audience · hook (cover line 1) · status · file

- contrast · employee · Tomorrow, a client call. Nobody told you your part. · reasoned · `contrast-client-call-tomorrow.json`
- contrast · employee · The senior leaders clap. Whose name did they hear? · reasoned · `contrast-credit-leaders.json`
- contrast · employee · A day off asked before a deadline. Which reply is fair? · reasoned · `contrast-day-off-deadline.json`
- contrast · employee · A meeting is called tonight for tomorrow. Which text respects the evening? · reasoned · `contrast-early-meeting.json`
- contrast · employee · More work lands on an already full week. Which ask is fair? · reasoned · `contrast-extra-task.json`
- contrast · employee · 10:40 pm and the phone lights up. Which text is fair? · reasoned · `contrast-late-night-call.json`
- contrast · employee · One mistake in a report. One text goes to the whole group. · reasoned · `contrast-public-mistake.json`
- contrast · employee · Please do the needful. What does that mean at your desk? · reasoned · `contrast-the-needful.json`
- contrast · employee · Why does your manager ask for updates every hour? · reasoned · `contrast-update-pings.json`
- contrast · employee · Same Monday report. Which text would you want to get? · reasoned · `contrast-weekend-report.json`
- mirror · manager · Are you online? One question that keeps a junior awake. · reasoned · `mirror-are-you-online.json`
- mirror · manager · A short call to the cabin can ruin a junior's afternoon. · reasoned · `mirror-come-to-cabin.json`
- mirror · manager · Comparing a junior with everyone else feels like pushing. · reasoned · `mirror-everyone-else-manages.json`
- mirror · manager · The manager says the work is not good. What to fix? · reasoned · `mirror-expected-better.json`
- mirror · manager · Do you want to grow or not? Said to motivate. · reasoned · `mirror-grow-or-not.json`
- mirror · manager · A junior leaves at 6 pm and hears a joke. · reasoned · `mirror-leaving-on-time.json`
- mirror · manager · Okay, will see. The junior waits all day for more. · reasoned · `mirror-okay-will-see.json`
- mirror · manager · Asking a junior if they are serious about the job can backfire. · reasoned · `mirror-serious-job.json`
- mirror · manager · A small thing, said quickly, can fill a whole evening. · reasoned · `mirror-small-thing.json`
- mirror · manager · One short question from a manager, and the junior goes quiet. · reasoned · `mirror-why-pending.json`
- can_they · employee · Camera on for every single call? Your manager insists. · reasoned · `canthey-camera-on.json`
- can_they · employee · You finish the slides. The brief changes. Again. Is that normal? · reasoned · `canthey-changing-brief.json`
- can_they · employee · A colleague's tasks appear on your board. Nobody told you. · reasoned · `canthey-colleagues-work.json`
- can_they · employee · The little green dot beside your name. Who is watching it? · reasoned · `canthey-green-dot.json`
- can_they · employee · Your idea, in your manager's voice. Can they do that? · reasoned · `canthey-idea-as-theirs.json`
- can_they · employee · 11 pm and the work chat is still buzzing. Is that fair? · reasoned · `canthey-late-work-chat.json`
- can_they · employee · A meeting is fixed right on your lunch break. Fair? · reasoned · `canthey-lunch-meeting.json`
- can_they · employee · Your manager wants your personal number. Must you give it? · reasoned · `canthey-personal-number.json`
- can_they · employee · Shouted at in front of the whole team. Is that normal? · reasoned · `canthey-shouting-in-meeting.json`
- can_they · employee · Hired for one job, handed another. Is that how it works? · reasoned · `canthey-work-outside-role.json`
