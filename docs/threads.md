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

## Every 60 days: automatic

A Meta token dies 60 days after it was made or last renewed, and there is no token that lasts forever. So the 08:00 and 20:00 runs (`python -m suresilly.run tokens`) renew any Instagram or Threads token whose secret is more than a week old, and save the new one over the secret. If a renewal fails, Telegram says so; the old token keeps working until its own 60 days run out.

This needs one GitHub token, made once:

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Name: `suresilly token renewer`. Expiration: **No expiration**. Repository access: **Only select repositories** → `ig-work`.
3. Permissions → Repository permissions → **Secrets: Read and write**. Nothing else.
4. Generate, copy it, and save it:

   ```bash
   pbpaste | gh secret set SECRETS_PAT
   ```

It can change this repo's secrets and nothing else.

## If a token dies anyway

Repeat step 4 of the setup for Threads and save the result with `pbpaste | gh secret set THREADS_ACCESS_TOKEN`.
