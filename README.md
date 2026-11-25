# Auto uzraugs – plug-in 4x4 līdz 37 000 €

Skripts katru stundu pārbauda ss.com un mollerauto.lv un sūta paziņojumu telefonā, kad:

- parādās jauns plug-in hibrīds ar pilnpiedziņu līdz 37 000 €;
- kādam no tiem samazinās cena;
- auto, kas maksāja 37 001–40 000 €, cena nokrīt līdz 37 000 € vai zemāk.

Auto, kas dārgāki par 40 000 €, netiek skatīti vispār.

## Uzstādīšana (~10 min)

1. **Telefonā** uzstādi lietotni **ntfy** (App Store / Google Play). Nospied „+” un pieraksties tematam ar garu, neuzminamu nosaukumu, piemēram `madara-auto-7k2p9xq`.
2. **GitHub** izveido jaunu repozitoriju un augšupielādē visus šīs mapes failus (arī `.github` mapi).
3. Repozitorijā: **Settings → Secrets and variables → Actions → New repository secret**
   – nosaukums `NTFY_TOPIC`, vērtība – tavs temats no 1. soļa.
4. **Actions** cilnē atver „Auto uzraugs” → **Run workflow**. Pirmā palaišana pārskata visu ss.com (~15 min) un atsūta vienu kopsavilkumu ar visiem šobrīd atbilstošajiem auto. Turpmāk paziņojumi nāks tikai par jauniem auto un cenu kritumiem.

## Iestatījumi (nav obligāti)

Settings → Secrets and variables → Actions → **Variables**:

| Mainīgais | Noklusējums | Nozīme |
|---|---|---|
| `MAX_PRICE` | 37000 | Paziņojumi tikai par auto līdz šai cenai |
| `SCAN_MAX` | 40000 | Augšējā robeža klusajai uzraudzībai (cenu kritumiem) |
| `INCLUDE_EV` | 0 | 1 – iekļaut arī tīros elektroauto ar 4x4 |
| `DEBUG` | 0 | 1 – detalizēts žurnāls Actions logā |

Biežumu maina `.github/workflows/auto-uzraugs.yml` rindā `cron`.

## Kā tiek atpazīts plug-in 4x4

Pēc atslēgvārdiem sludinājuma tekstā: plug-in, PHEV, eHybrid, TFSI e, GTE, iV, Recharge, T8, 4xe, xDrive30e u. c. un pilnpiedziņa, 4x4, quattro, 4Motion, xDrive, 4Matic, AWD. Outlander PHEV, RAV4 plug-in, Volvo T8 u. c. tiek uzskatīti par 4x4 automātiski. Ja kāds auto paslīd garām vai pienāk lieks paziņojums – noteikumi ir `auto_monitor.py` sākumā (`PLUGIN_RE`, `AWD_RE`).
