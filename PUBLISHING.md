# Publishing YouTown Player on GitHub

This repo is set up so you can do everything from the GitHub website by dragging and dropping.

## 0. Before you start: keep your email private

Every commit records an email address. On GitHub, open **Settings → Emails**, tick **Keep my email addresses private**
and **Block command line pushes that expose my email**. Commits you make on the website will then use a
`…@users.noreply.github.com` address.

## 1. Create the repository and upload the code

1. On GitHub, click **New repository**. Name it, for example, `youtown-player`, make it **Public**, and create it
   (don't add a README; this folder already has one).
2. On the empty repo page, click **uploading an existing file**.
3. Drag **everything inside the `github-upload` folder** (not the folder itself) into the page:
   `youtown/`, `packaging/`, `assets/`, `docs/`, `run.py`, `requirements.txt`, `README.md`, `PUBLISHING.md`,
   `LICENSE`, `THIRD-PARTY-NOTICES.md`, `.gitignore`.
4. Click **Commit changes**.

> Tip: the browser upload accepts files up to 25 MB, so the installer **doesn't** go here. It goes in a
> release (step 2).

## 2. Publish the installer as a release

1. In the repo, open **Releases → Draft a new release** (or **Create a new release**).
2. Under **Choose a tag**, type `v2.0.0` and choose *Create new tag*.
3. Title: `YouTown Player 2.0.0`.
4. Drag **`YouTown-Player-Setup.exe`** into the *Attach binaries* box. Keep that exact file name, because the
   website's Download button points to it.
5. Leave **Set as a pre-release** unticked (the "latest" download link skips pre-releases), then click **Publish release**.

## 3. Turn on the website (GitHub Pages)

1. Open **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to *Deploy from a branch*, **Branch** to `main`, and the folder to
   **`/docs`**, then click **Save**.
3. After a minute your site is live at `https://YOUR-USERNAME.github.io/youtown-player/`.

The Download button finds your latest release automatically and shows its real version and size.
If you use a custom domain, open `docs/index.html` and fill in `OWNER` and `REPO` in the `CONFIG` line near the end.

## Releasing a new version later

1. Bump `VERSION` in `youtown/config.py` and `packaging/installer.nsi`.
2. Run `.venv\Scripts\python packaging\build.py`.
3. Create a new release (for example `v2.1.0`) and attach the new `dist\YouTown-Player-Setup.exe`.
   The website picks it up automatically.
