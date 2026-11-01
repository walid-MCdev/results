# HSC Result Search

Upload a board result PDF to `pdfs/` and GitHub Actions parses it, builds a searchable page, and publishes it with GitHub Pages.

## One-time setup
1. Create a new GitHub repo and push this folder to the `main` branch.
2. In the repo go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
3. Open the **Actions** tab, wait for the run to finish, and your site is live at
   `https://<your-username>.github.io/<repo-name>/`.

## Day-to-day use
- **New results:** add a PDF to `pdfs/` (Add file → Upload files on github.com) and commit. The site rebuilds automatically.
- **Names:** the board PDF has only roll numbers. Add `roll,name` lines to `names.csv` and commit to enable name search.
- Each PDF gets its own page at `/<pdf-file-name>/`, with a `results.json` next to it.

## Local run
```
pip install -r requirements.txt
python scripts/build_site.py   # output in site/
```

## Privacy
GitHub Pages sites are public. If you add student names, anyone with the link can see them. Consider keeping the repo private (Pages on private repos needs a paid plan) or leaving names out.
