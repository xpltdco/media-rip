# media.rip() — Deployment Testing Prompt

Take this to a separate Claude session on a machine with Docker installed.

---

## Context

You're testing a freshly published Docker image for **media.rip()**, a self-hosted yt-dlp web frontend. The image is at `ghcr.io/xpltdco/media-rip:latest` (v1.0.1). Your job is to deploy it, exercise the features, and report back with findings.

The app is a FastAPI + Vue 3 web app that lets users paste video/audio URLs, pick quality, and download media. It has session isolation, real-time SSE progress, an admin panel, theme switching, and auto-purge.

## Step 1: Deploy (zero-config)

Create a directory and bring it up:

```bash
mkdir media-rip-test && cd media-rip-test

cat > docker-compose.yml << 'EOF'
services:
  mediarip:
    image: ghcr.io/xpltdco/media-rip:latest
    ports:
      - "8080:8000"
    volumes:
      - ./downloads:/downloads
      - mediarip-data:/data
    environment:
      - MEDIARIP__SESSION__MODE=isolated
    restart: unless-stopped

volumes:
  mediarip-data:
EOF

docker compose up -d
docker compose logs -f  # watch for startup, Ctrl+C when ready
```

Open http://localhost:8080 in a browser.

## Step 2: Test the core loop

Test each of these and note what happens:

1. **Paste a URL and download** — Try a YouTube video (e.g. `https://www.youtube.com/watch?v=jNQXAC9IVRw` — "Me at the zoo", 19 seconds). Does the format picker appear? Can you select quality? Does the download start and show real-time progress?

2. **Check the download file** — Look in `./downloads/` on the host. Is the file there? Is the filename sensible?

3. **Try a non-YouTube URL** — Try a SoundCloud track, Vimeo video, or any other URL. Does format extraction work?

4. **Try a playlist** — Paste a YouTube playlist URL. Do parent/child jobs appear? Can you collapse/expand them?

5. **Queue management** — Start multiple downloads. Can you cancel one mid-download? Does the queue show correct statuses?

6. **Page refresh** — Refresh the browser mid-download. Do your downloads reappear (SSE reconnect replay)?

7. **Session isolation** — Open a second browser (or incognito window). Does it have its own empty queue? Can it see the first browser's downloads? (It shouldn't in isolated mode.)

## Step 3: Test the admin panel

Bring the container down, enable admin, bring it back up:

```bash
docker compose down

# Generate a bcrypt hash for password "testpass123"
HASH=$(docker run --rm python:3.12-slim python -c "import bcrypt; print(bcrypt.hashpw(b'testpass123', bcrypt.gensalt()).decode())")

cat > docker-compose.yml << EOF
services:
  mediarip:
    image: ghcr.io/xpltdco/media-rip:latest
    ports:
      - "8080:8000"
    volumes:
      - ./downloads:/downloads
      - mediarip-data:/data
    environment:
      - MEDIARIP__SESSION__MODE=isolated
      - MEDIARIP__ADMIN__ENABLED=true
      - MEDIARIP__ADMIN__USERNAME=admin
      - MEDIARIP__ADMIN__PASSWORD_HASH=$HASH
    restart: unless-stopped

volumes:
  mediarip-data:
EOF

docker compose up -d
```

Test:
1. Does the admin panel appear in the UI? Can you log in with `admin` / `testpass123`?
2. Can you see active sessions, storage info, error logs?
3. Can you trigger a manual purge?
4. Do previous downloads (from step 2) still appear? (Data should persist across restarts via the named volume.)

## Step 4: Test persistence

```bash
docker compose restart mediarip
```

After restart:
1. Does the download history survive?
2. Does the admin login still work?
3. Are downloaded files still in `./downloads/`?

## Step 5: Test themes

1. Switch between Cyberpunk, Dark, and Light themes in the header. Do they all render correctly?
2. Check on mobile viewport (resize browser to <768px). Does the layout switch to mobile mode with bottom tabs?

## Step 6: Test auto-purge (optional)

```bash
docker compose down

# Enable purge with a very short max age for testing
cat > docker-compose.yml << 'EOF'
services:
  mediarip:
    image: ghcr.io/xpltdco/media-rip:latest
    ports:
      - "8080:8000"
    volumes:
      - ./downloads:/downloads
      - mediarip-data:/data
    environment:
      - MEDIARIP__SESSION__MODE=isolated
      - MEDIARIP__PURGE__ENABLED=true
      - MEDIARIP__PURGE__MAX_AGE_HOURS=0
      - MEDIARIP__PURGE__CRON=* * * * *
    restart: unless-stopped

volumes:
  mediarip-data:
EOF

docker compose up -d
docker compose logs -f  # watch for purge log messages
```

Do completed downloads get purged? Do files get removed from `./downloads/`?

## Step 7: Health check

```bash
curl http://localhost:8080/api/health | python -m json.tool
```

Does it return status, version, yt_dlp_version, uptime?

## Step 8: Container inspection

```bash
# Check image size
docker images ghcr.io/xpltdco/media-rip

# Check the container is running as non-root
docker compose exec mediarip whoami

# Check no outbound network requests
docker compose exec mediarip python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

# Check ffmpeg and deno are available
docker compose exec mediarip ffmpeg -version | head -1
docker compose exec mediarip deno --version
```

## What to report back

When you're done, bring the findings back to the original session. Structure your report as:

### Working
- List everything that worked as expected

### Broken / Bugs
- Exact steps to reproduce
- What you expected vs what happened
- Any error messages from `docker compose logs` or browser console

### UX Issues
- Anything confusing, ugly, slow, or unintuitive
- Mobile layout problems
- Theme rendering issues

### Missing / Gaps
- Features that felt absent
- Configuration that was hard to figure out
- Documentation gaps

### Container / Ops
- Image size
- Startup time
- Resource usage (`docker stats`)
- Any permission errors with volumes
- Health check behavior

### Raw logs
- Paste any interesting lines from `docker compose logs`
- Browser console errors (F12 → Console tab)

---

## Cleanup

```bash
docker compose down -v  # removes containers + named volumes
rm -rf media-rip-test
```
