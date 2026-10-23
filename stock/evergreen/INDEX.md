# Evergreen Reel scripts

30 scripts for @suresilly, first-job India, age 18 to 30. Nothing here is live. Each file is `<slug>.json`: `script` holds the fields `script.py` writes, `report` the hook, voice and shape. The `can_they` files also hold the `fact` the answer rests on.

- **20 for the employee** (10 contrast, 10 can_they), **10 for the manager** (mirror). A contrast also shows the manager the better text, but its reply is for the employee.
- **Status `reasoned` (20):** contrast and mirror. No source named, no number except a time.
- **Status `reported` (10):** the can_they scripts. Government sites could not be opened from the cloud session (network block), and no web page could be fetched at all. Nine facts come from `suresilly/facts.json` (your earlier research pass, secondary sources). One, `salary-by-7th`, comes from a web search summary of the Code on Wages text; the page itself was not opened. Every answer says "Reports say". None is `verified`: please check the source before you approve.
- `gratuity` says about 5 years (from `facts.json`). Search summaries say fixed-term staff may get it after 1 year. That is not used here.
- Every script passes `script.check` for its type, against all earlier ones. `python -m pytest -q`: 298 passed, 5 skipped.

Format: type · audience · cover line 1 · status · file · source

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
- can_they · employee · A bond in your first job. Can the amount be anything? · reported · `canthey-bond-amount.json` · source: Supreme Court, Vijaya Bank v. Narnaware
- can_they · employee · Your last day was Friday. The last salary has not come. · reported · `canthey-final-salary.json` · source: LiveLaw
- can_they · employee · You served for years and left. Where is the gratuity? · reported · `canthey-gratuity-wait.json` · source: LiveLaw
- can_they · employee · PF is cut from your salary. Does it reach your account? · reported · `canthey-late-pf.json` · source: EPFO (owner to confirm)
- can_they · employee · You resign, and your manager says a longer notice applies. · reported · `canthey-longer-notice.json` · source: Delhi Shops and Establishments Act
- can_they · employee · Midnight at the desk, again. Is there a limit? · reported · `canthey-midnight-desk.json` · source: Delhi, Maharashtra and Karnataka rules
- can_they · employee · 11 pm and your boss messages. Does any law cover this? · reported · `canthey-night-messages.json` · source: Private member's bill
- can_they · employee · Your first day is Monday. You still have no letter. · reported · `canthey-no-appointment-letter.json` · source: KPMG
- can_they · employee · Last month's salary has still not arrived. · reported · `canthey-salary-weeks-late.json` · source: Code on Wages 2019 (text on labour.gov.in, seen through search results; page not opened)
- can_they · employee · The variable part of your pay shrank. Nobody asked you. · reported · `canthey-variable-pay-cut.json` · source: Indian Contract Act, section 62
