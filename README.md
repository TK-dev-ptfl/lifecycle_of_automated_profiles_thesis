# Plán projektu — Životný cyklus automatizovaných účtov na sociálnych sieťach

---

## Cieľ projektu

Cieľom práce je systematicky preskúmať životný cyklus automatizovaných účtov (botov) na sociálnych sieťach — od vytvorenia cez budovanie dôvery až po vykonávanie konkrétnych úloh. Výskum sa zameriava na porovnanie rôznych stratégií správania a interakcie so sieťou z hľadiska viacerých skúmaných vlastností, pričom poskytuje náhľad na spôsoby zneužitia siete automatizovanými nástrojmi.

Primárna platforma pre prvú fázu výskumu: **Reddit**

Dôvod: otvorené API, sandbox cez privátny subreddit, karma systém poskytuje merateľnú metriku dôveryhodnosti.

---

## Kalendár práce

---

### ✅ Hotové

| Úloha                                   | Od         | Do         |
| --------------------------------------- | ---------- | ---------- |
| prehľad literatúry a problematiky       | 15.03.2026 | 29.03.2026 |
| návrh testovacieho prostredia           | 03.04.2026 | 12.04.2026 |
| testovanie hlavných knižníc             | 13.04.2026 | 16.04.2026 |
| task – algorithm – method hierarchia    | 13.04.2026 | 18.04.2026 |
| sandbox setup                           | 28.04.2026 | 28.04.2026 |
| email servis                            | 28.04.2026 | 29.04.2026 |
| proxy servis                            | 28.04.2026 | 30.04.2026 |
| identity management                     | 30.04.2026 | 01.05.2026 |
| Reddit creation pipeline (manuálne)     | 01.04.2026 | 01.05.2026 |
| email creation + verifikácia (manuálne) | 01.04.2026 | 01.05.2026 |
| Reddit warm-up pipeline (manuálne)      | 01.05.2026 | 02.05.2026 |
| písanie kapitola 2                      | 05.05.2026 | 07.05.2026 |
| písanie kapitola 3                      | 07.05.2026 | 10.05.2026 |

---

### 🔲 Zostatok

| Úloha                            | Od         | Do         |
| -------------------------------- | ---------- | ---------- |
| monitoring                       | 01.06.2026 | 04.06.2026 |
| automatizácia krokov pipeline    | 04.06.2026 | 04.07.2026 |
| implementácia algoritmov         | 04.07.2026 | 04.08.2026 |
| návrh hypotéz [iter. 1]          | 04.08.2026 | 06.08.2026 |
| testovanie hypotéz [iter. 1]     | 06.08.2026 | 13.08.2026 |
| návrh hypotéz [iter. 2]          | 13.08.2026 | 15.08.2026 |
| testovanie hypotéz [iter. 2]     | 15.08.2026 | 22.08.2026 |
| návrh hypotéz [iter. 3]          | 22.08.2026 | 24.08.2026 |
| testovanie hypotéz [iter. 3]     | 24.08.2026 | 31.08.2026 |
| písanie kapitola 4 (metodológia) | 31.08.2026 | 03.09.2026 |
| písanie kapitola 5 (výsledky)    | 03.09.2026 | 06.09.2026 |
| písanie kapitola 6 (analýza)     | 06.09.2026 | 09.09.2026 |
| vyhodnotenie výstupov práce      | 09.09.2026 | 12.09.2026 |

---

> **Optimistický odhad dokončenia: 12.09.2026**

---

## Skúmané vlastnosti (os hodnotenia)

Pre každú kombináciu stratégie × komunikačnej metódy meriame:

| Vlastnosť           | Definícia                                         |
| ------------------- | ------------------------------------------------- |
| Cena                | Náklady na 1000 úspešných akcií (EUR)             |
| Náročnosť           | Čas a odbornosť potrebná na funkčnú implementáciu |
| Udržateľnosť        | Životnosť bez manuálneho zásahu                   |
| Kvalita výsledkov   | Miera dosiahnutia cieľa úlohy                     |
| Výpočtová náročnosť | Spotreba CPU/RAM na 1 bota                        |

---

## Iteratívna implementácia algoritmov

```
[ Krok 1: Návrh zmeny na základe literatúry/dát ]
                   ↓
[ Krok 2: Implementácia úpravy v kóde ]
                   ↓
[ Krok 3: Spustenie testu v sandboxe ]
                   ↓
[ Krok 4: Vyhodnotenie metrík ] ── (Výsledok je HORŠÍ) ──> [ Zahodiť zmenu & Skúsiť iný prístup ]
                   ↓
           (Výsledok je LEPŠÍ)
                   ↓
[ Ponechať iteráciu ako baseline & Pokračovať ďalej ]
```

**Príklad:**

- _Krok 1:_ Z analýzy logov je vidno, že bot dostal ban po 50 príspevkoch. Návrh zmeny: „Pridať náhodné prestávky medzi akciami podľa Gaussovho rozdelenia."
- _Krok 2:_ Zapracovanie `numpy.random.normal` do plánovača úloh.
- _Krok 3:_ Otestovanie novej skupiny botov.
- _Krok 4:_ Porovnanie času do zablokovania a skóre detektora. Ak bot prežil 3× dlhšie, zmena sa stáva trvalou súčasťou algoritmu.

---

## Testovanie hypotéz

### Príklady testovaných hypotéz

| ID  | Hypotéza                                                                                                                               |
| --- | -------------------------------------------------------------------------------------------------------------------------------------- |
| H1  | Headless režim prehliadača (bez dodatočnej obfuskácie) je platformou detekovaný skôr ako plnohodnotný headful prehliadač.              |
| H2  | Obsah generovaný pokročilým LLM vykazuje nižšiu mieru lingvistickej detekcie ako obsah generovaný na základe pevných textových šablón. |

### Postup realizácie každého experimentu

1. Definovať hypotézu presne — jedna premenná sa mení, ostatné sú konštantné
2. Pripraviť botov — minimálne 3–5 botov na každú podmienku pre štatistickú vierohodnosť
3. Testovať v sandboxe po definovanú dobu
4. Pozorovať výsledky pomocou detekčných nástrojov
5. Zaznamenať výstup do štandardizovanej tabuľky
6. Navrhnúť ďalšiu hypotézu na základe zistení

---

## Etika a zodpovedné zverejňovanie

- Všetky experimenty prebiehajú výhradne v izolovaných sandbox kanáloch
- Žiadna interakcia s reálnymi používateľmi mimo experimentu
- Žiadne generovanie ani šírenie dezinformačného obsahu
- Všetky testovacie účty sú po ukončení výskumu zrušené
- Zistené zraniteľnosti sú platformám nahlásené pred zverejnením (responsible disclosure)

---

## Knižnice

| Knižnica             | Využitie                                        |
| :------------------- | :---------------------------------------------- |
| `praw`               | Komunikácia cez oficiálne Reddit API            |
| `playwright`         | Automatizácia prehliadača (headless aj headful) |
| `playwright-stealth` | Potlačenie stôp automatizácie v prehliadači     |
| `curl_cffi`          | Priame HTTP požiadavky a neoficiálne Reddit API |
| `fake-useragent`     | Generovanie realistických User-Agent reťazcov   |
| `Faker`              | Generovanie syntetických osobných identít       |

## Nástroje

| Nástroj          | Využitie                                              |
| :--------------- | :---------------------------------------------------- |
| BLOC             | Behaviorálna analýza sekvencie akcií účtu             |
| Pixelscan        | Testovanie konzistencie browser fingerprintu          |
| CreepJS          | Hĺbková analýza fingerprintu a detekcia automatizácie |
| BrowserLeaks TLS | Meranie JA3/JA4 TLS fingerprintu spojenia             |
