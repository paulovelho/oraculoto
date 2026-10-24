# CGI test (throwaway)

Question: DreamHost shared hosting dropped Passenger, so is FastAPI + MySQL through **plain CGI** fast enough?
Apache starts Python once per request, so every request pays for startup + imports.
Delete this folder once the question is answered.

## Layout

```
cgi-test/
├── public/          <- the domain's web directory points HERE, and only here
│   ├── test.txt     <- static file: proves the domain points to the right folder
│   ├── .htaccess    <- enables CGI, sends everything else to index.cgi
│   └── index.cgi    <- shell wrapper: runs ../app.py with ../.venv/bin/python
├── app.py           <- FastAPI app (/ and /db), outside the web root
├── .env             <- database settings (created by setup.sh, never committed)
└── setup.sh         <- installs uv, Python 3.13, dependencies; fixes permissions
```

`app.py`, `.env` and the rest of the repo (plans, xlsx) sit outside `public/`, so the web can't reach them.

## Steps

1. **Clone** on the DreamHost server (over SSH):
   ```sh
   cd ~ && git clone https://github.com/paulovelho/oraculoto.git
   ```
2. **Point the domain** at `public/`: in the panel, **Websites → Manage Websites → oraculoto.platypusweb.com.br → Manage → Settings**, change the **web directory** to `oraculoto/cgi-test/public`.
   (The panel's wording may differ; it's the domain's "web directory" or "document root".)
3. **Check the folder**: open https://oraculoto.platypusweb.com.br/test.txt. You should see the wizard's message.
   If you get a 404 or another site, step 2 isn't right yet; stop there.
4. **Set up**:
   ```sh
   sh ~/oraculoto/cgi-test/setup.sh
   ```
   Then edit `~/oraculoto/cgi-test/.env` with the MySQL settings (panel → MySQL Databases: hostname, database, user, password).
5. **Check the app**:
   - https://oraculoto.platypusweb.com.br/ → JSON with `"message": "FastAPI is answering through CGI"`
   - https://oraculoto.platypusweb.com.br/db → JSON with `"mysql": "8.0.41-..."`
6. **Time it** (from your own machine, 5 times each):
   ```sh
   for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://oraculoto.platypusweb.com.br/; done
   for i in 1 2 3 4 5; do curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' https://oraculoto.platypusweb.com.br/db; done
   curl -s https://oraculoto.platypusweb.com.br/db
   ```
   For comparison, the static file: `curl -s -o /dev/null -w '%{time_total}s\n' https://oraculoto.platypusweb.com.br/test.txt`

## If something breaks

| symptom | likely cause |
|---|---|
| `test.txt` 404 | web directory not pointing at `cgi-test/public` |
| `/` downloads or shows the script's text | CGI not enabled for the folder; check `.htaccess` was cloned (it's a dotfile) |
| `/` gives 500 "Internal Server Error" (Apache's page) | permissions (run `setup.sh` again) or `.venv` missing; look in `~/logs/oraculoto.platypusweb.com.br/https/error.log` |
| `/` says `error: see cgi-test/cgi-error.log` | the app crashed; the traceback is in that file |
| `/db` gives `db_error` | wrong settings in `.env`, or the database user isn't allowed from this server |
