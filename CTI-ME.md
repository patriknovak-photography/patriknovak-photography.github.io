# Patrik Novák – fotografický web

Statický web: hotové stránky jsou ve složce `docs/`, nic dalšího k provozu nepotřebuje.
Stránky se ze složky `photos/` a souboru `site.toml` sestavují skriptem `build.py` (Python 3.11+ a Pillow).

## Co je kde

| Složka / soubor | K čemu je |
|---|---|
| `photos/` | Fotky po albech. Každá podsložka je jedno album. |
| `photos/<album>/album.toml` | Název alba (česky, anglicky), popisek, světlé/tmavé pozadí, titulní fotka. |
| `photos/_nezarazene/` | Odkladiště. Složky začínající `_` se na web nedostanou. |
| `site.toml` | Jméno, texty (O mně, Kontakt), úvodní fotky, klíč formuláře, adresa webu. |
| `docs/` | Hotový web. Needituj ručně, při sestavení se přepisuje. |
| `src/` | Vzhled (`style.css`), chování (`site.js`), písmo Lora. |
| `nahled.bat` | Sestaví web a otevře náhled v prohlížeči. |
| `sestavit.bat` | Jen sestaví web. |
| `zverejnit.bat` | Sestaví web a odešle změny na GitHub. |
| `ZMENY-FOTEK.md` | Která fotka je ve kterém albu a jak byla upravena. |

Když dvojklik na `.bat` nenajde Python, otevři ve složce PowerShell a spusť `python build.py --serve`.

## Běžné úpravy

**Přidat fotku:** zkopíruj JPEG do složky alba a spusť `nahled.bat`. Velikost neřeš, skript ji zmenší,
převede do sRGB a odstraní EXIF (včetně GPS).

**Pořadí fotek:** řídí se názvem souboru. Proto začínají čísly `01_`, `02_`… Přečísluj a sestav znovu.

**Odebrat fotku:** smaž ji ze složky alba (nebo přesuň do `photos/_nezarazene/`) a sestav znovu.

**Titulní fotka alba:** v `album.toml` řádek `cover = "název_souboru.jpg"`.

**Nové album:** vytvoř složku, např. `photos/07-portrety/`, zkopíruj do ní `album.toml` z jiného alba a uprav ho.
Číslo na začátku určuje pořadí alb, zbytek názvu adresu stránky (`/portrety/`).

**Světlé nebo tmavé pozadí alba:** v `album.toml` řádek `theme = "light"` nebo `theme = "dark"`.

**Texty:** v `site.toml`, oddíly `[cs]` a `[en]`. Odstavce v textu O mně odděl prázdným řádkem.

**Úvodní fotky:** v `site.toml` seznam `hero`. Zápis `"album/soubor.jpg | 70% 55%"` –
procenta říkají, který bod fotky má zůstat vidět, když se na úzkém displeji ořízne.

Po každé změně spusť `nahled.bat` (nebo `sestavit.bat`).

## Kontaktní formulář

1. Na https://web3forms.com zadej e-mail, na který mají zprávy chodit. Přístupový klíč přijde poštou.
2. Vlož ho do `site.toml`: `web3forms_key = "tvůj-klíč"`.
3. Sestav web a pošli si zkušební zprávu.

Klíč je veřejný záměrně, e-mailová adresa na webu vidět není. Bez klíče formulář jen oznámí, že není zapnutý.
Bezplatný tarif měl v listopadu 2026 limit 250 zpráv měsíčně; aktuální podmínky si ověř na webu služby.

## Zveřejnění na GitHub Pages (zdarma)

1. Založ účet na https://github.com a vytvoř **veřejný** repozitář, např. `foto`
   (bez README a bez .gitignore). Na bezplatném účtu funguje Pages jen u veřejných repozitářů.
2. V PowerShellu ve složce projektu (místo `UZIVATEL` a `foto` dosaď své):

   ```powershell
   git init
   git add -A
   git commit -m "První verze webu"
   git branch -M main
   git remote add origin https://github.com/UZIVATEL/foto.git
   git push -u origin main
   ```

   Při prvním `git push` se otevře okno prohlížeče pro přihlášení ke GitHubu.
   Pokud git chce jméno a e-mail, nastav je: `git config --global user.name "Patrik Novák"` a
   `git config --global user.email "tvuj@email"`.
3. Na GitHubu v repozitáři: **Settings → Pages → Source: Deploy from a branch → Branch: `main`, složka `/docs` → Save**.
4. Za pár minut web poběží na `https://UZIVATEL.github.io/foto/`.
5. Tuhle adresu vlož do `site.toml` jako `base_url` (bez lomítka na konci) a spusť `zverejnit.bat`.

Každá další aktualizace: uprav fotky nebo texty a spusť `zverejnit.bat`.

**Adresa bez `/foto/` na konci:** pojmenuj repozitář přesně `UZIVATEL.github.io`. Web pak poběží na
`https://UZIVATEL.github.io/`. Proto se vyplatí zvolit uživatelské jméno jako `patriknovak` nebo `patriknovak-foto`.

**Cloudflare Pages** (adresa `nazev.pages.dev`): propoj stejný repozitář, pole Build command nech prázdné
a jako výstupní složku zadej `docs`.

**Vlastní doména** (`.cz` stojí řádově stovky Kč ročně) se dá k oběma službám připojit později.

## Co se nezveřejňuje

Soubor `.gitignore` nechává fotky ze složky `photos/` jen na tvém disku. Na GitHub jde složka `docs/`
(webové velikosti do 2400 px, panoramata do 3000 px) a zdrojové soubory. Složku `photos/` si proto zálohuj sám.

## Písmo

Lora, licence SIL Open Font License 1.1 (`src/fonts/OFL.txt`). Písmo je uložené přímo na webu,
stránky nenačítají nic z cizích serverů kromě odeslání formuláře.
