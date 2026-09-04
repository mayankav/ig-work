# Reliable testing: save progress, bound service retries

The prior screen stopped after any service error and could not resume. The shared production client also names both HTTP 429 and HTTP 503 `RateLimited`; that exception name does not establish quota exhaustion. The new offline transport records the actual HTTP status and provider error. It does not change production error handling.

## Initial six-image screen

Use `scripts/resumable_image_screen.py` with the same output directory to continue an experiment. It uses one configured key, one exact model and the fixed visible-parts prompt. No key rotation or model fallback occurs. The first real image is also the availability check; there is no extra quota-consuming text probe.

- A completed answer is final. A missed fault, wrong rejection, malformed answer or unresolved visible detail stops the screen. Never rerun one to obtain a better answer.
- Temporary HTTP 429, 408, 500, 502, 503, 504 or network errors can receive bounded retries. Respect provider retry delays, add increasing waits and small jitter, and space requests by at least 40 seconds. A long delay pauses on disk.
- A stated daily quota limit or access/configuration error stops the experiment. Unknown limits are not assumed to be unlimited. No paid access is enabled.
- At most three requests per case and 18 across the six-image experiment, including failed calls. The default invocation makes at most three requests. Resume does not reset these limits. The experiment expires after 24 hours.
- Save the raw response before scoring. Replay it after interruption. An interrupted request whose response was not saved remains unknown and is not silently sent again. A file lock prevents two processes from running the same experiment at once.

Images, submitted JPEG hashes, prompts, settings and source-code hashes belong to the experiment. Changed inputs or code require a distinct experiment; old results remain preserved. A new experiment must not be used to hide failed attempts.

## What this does not solve

Free services can remain unavailable. After three failed attempts, report the service unavailable; do not keep looping. Accuracy and service availability are separate results. A screen pass is not production qualification.

The formal 23-image, three-repeat qualification remains separate, with its existing controls and 138-request limit. This initial-screen retry allowance does not increase that budget or relax any image check.

Local models enter a comparison only after installation and a working local server. Downloads are setup work, not an accuracy test, and should not hold the hosted comparison open.

Provider guidance: https://ai.google.dev/gemini-api/docs/troubleshooting
