# Threads

After Instagram has an evening one-liner, `suresilly/threads.py` posts it to Threads too: the slide image, the line as the text, and the post's topic as the Threads topic tag. If Threads refuses it, the Instagram post is untouched and the "Posted!" message on Telegram says why.

It stays off until the two repo secrets below exist.

## Setup (once, about 20 minutes)

1. **Make the Threads profile.** In the Threads app, sign in with the @suresilly Instagram account.
2. **Add Threads to the Meta app.** In the Meta developer dashboard, open the app that posts to Instagram → Use cases → Add → "Access the Threads API". Tick `threads_basic` and `threads_content_publish`.
3. **Make yourself a tester.** App roles → Roles → Add People → Threads Tester → @suresilly. Accept the invite in the Threads app: Settings → Account → Website permissions → Invites.
4. **Get a token.** Threads use case → Settings → User Token Generator → Generate for @suresilly. If it says the token lasts 1 hour, swap it for a 60-day token:

   ```bash
   curl "https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=APP_SECRET&access_token=SHORT_TOKEN"
   ```

5. **Get the Threads user id:**

   ```bash
   curl "https://graph.threads.net/v1.0/me?fields=id,username&access_token=LONG_TOKEN"
   ```

6. **Save both as repo secrets.** Each command asks you to paste the value:

   ```bash
   gh secret set THREADS_USER_ID
   gh secret set THREADS_ACCESS_TOKEN
   ```

## Every 60 days

The token dies 60 days after it was made or last refreshed. When it does, the "Posted!" message says "the Threads token has expired". Refresh it before then (the token must be at least 1 day old), then save the new one with `gh secret set THREADS_ACCESS_TOKEN`:

```bash
curl "https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=CURRENT_TOKEN"
```

If it has already expired, repeat step 4.
