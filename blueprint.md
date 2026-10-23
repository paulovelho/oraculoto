# Loterias Resultado guesser

This project aims to predict the next result on Loterias Caixa.
Easy.

## structure:
- api
- crawler
- web
- database

### API
Will run inside /api
It will access only internal database: it will guess the next result based on a series of functions I will send you

- token limitation access
- internal CORS access (will accept requests only from a certain)

### database
take a look at `files/Mega-Sena.xlsx`
this is the data that I need to store in a database

For starters: I will need to get queries such as:

- result of an specific game
- last time balls appeared together in a game (it can be one or n balls in a game)
- last time someone won with a ball (it can be one or n balls)
- ball that shows up more often

those are just query samples, for you to think about when building the database.
in short: we need to follow the balls, the frequency a ball shows up, the frequency some balls shows up together, the result of game x, and so on.

Right now, we will do it only for games on Mega Sena, but we might want to expand this project in the future for other games, such as Quina or LotoFácil

Database will also have a table of users, logged through Google auth (firebase, I don't want to handle auth)

### crawler
can also run inside the API. as Loterias doesn't have an API we will have to crawl their website for the results, in a crawler like:
```php
$c = curl_init();
$cookie_file = __DIR__.DIRECTORY_SEPARATOR.'megasena.txt';
curl_setopt_array($c, array(
    CURLOPT_URL => 'http://www.loterias.caixa.gov.br/wps/portal/loterias/landing/megasena',
    CURLOPT_REFERER => 'http://www.loterias.caixa.gov.br',
    CURLOPT_USERAGENT => 'Foo Spider',
    CURLOPT_HEADER => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CONNECTTIMEOUT => 6,
    CURLOPT_TIMEOUT => 6,
    CURLOPT_MAXREDIRS => 1,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_COOKIESESSION => true,
    CURLOPT_COOKIEFILE => $cookie_file,
    CURLOPT_COOKIEJAR => $cookie_file
));

try {
    $content = curl_exec($c);
    $data = curl_getinfo($c);
    $data['content'] = $content;
    unset($content);
    $data['errno'] = curl_errno($c);
    $data['errmsg'] = curl_error($c);
    if ((int)$data['errno'] !== 0 || (int)$data['http_code'] !== 200) {
        echo 'error number: '.$data['errno'];
        echo 'error message: '.$data['errmsg'];
        echo 'http status: '.$data['http_code'];
        //print_r($data);
        exit;
    }
} catch (HttpException $ex) {
    print_r($ex); exit;
}

curl_close($c); 

$doc = new DOMDocument();
@$doc->loadHTML($data['content']);
unset($data);
$tags = $doc->getElementsByTagName('ul');
$data = null;
foreach ($tags as $tag) {
    if ($tag->getAttribute('class') == 'numbers mega-sena') {
        $data = trim($tag->textContent);
        break;
    }
}
$arr = str_split($data, 2);
print_r($arr);
```
(from https://pt.stackoverflow.com/questions/47597/como-posso-pegar-os-resultados-das-loterias)

We will run this crawler in a cron and we won't run if the result is already in the database

### Web
Still in progress, it will be GoogleAuth limited.


## Result:

Let's start working on the database:
create schema.sql and a tool to import xlsx like that into the created schema.

then we will create plans for api, and crawler. and, lastly, after our api is settled, we will think on the web.

right now, your job will be only generate a plan.md file for each of the modules and think on the database.


## Decisions (2026-10-23)

- **Crawler source:** Caixa's JSON endpoint `https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/{contest}`, not HTML scraping. The page in the snippet above no longer contains the results.
  - It's open (no login or key) but unofficial and fragile.
  - It runs daily, fetches every missing contest and refreshes the last 3, instead of "skip if it's already in the database".
  - The xlsx importer stays as the fallback. Details: `crawler/plan.md`.
- **Access:**
  - A Firebase ID token is required on every endpoint, with no rate limits.
  - Access is invite-only: the `users` table is the invite list (emails added beforehand), and anyone else gets 403.
  - CORS is not access control. It's only needed if the web app and the API are served from different domains.
- **What gets stored:**
  - Users' tickets are stored and checked against results automatically.
  - Function guesses are not stored. Functions are judged by backtests run on demand, always next to a random baseline.
- **Deployment and stack:**
  - Deployment: Docker.
  - Stack: to be discussed (leaning towards Python). `schema.sql` and the importer wait for that decision.
- **Module plans:** `database/plan.md`, `crawler/plan.md`, `api/plan.md`, `web/plan.md` (on hold).

